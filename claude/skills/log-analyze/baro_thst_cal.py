#!/usr/bin/env python3
"""Fit BARO1_THST_SCALE from a log of the vehicle held still while the throttle is ramped.

AP_Baro subtracts BARO1_THST_SCALE * lpf(throttle_out, BARO_THST_FILT) from the raw pressure
(AP_Baro.cpp, thrust_pressure_correction). If the airframe is physically fixed -- clamped,
or held nose-down so the wash goes sideways and nothing lifts -- then every Pascal the baro
moves after the throttle comes up is the thrust effect and nothing else, and SCALE is just
the slope of (BARO.Press - P0) against the filtered MOTB.ThrOut. No altitude truth needed.

  * BARO.Press is the RAW pressure (AP_Baro_Logging.cpp logs get_pressure(); CPress is the
    compensated one), so the fit is the total scale to set, whatever the log already had.
  * MOTB.ThrOut is motors->get_throttle_out(), the exact input the firmware filters. CTUN.ThO
    is the attitude controller's request and differs under mixer limiting.
  * The filter is replicated with ArduPilot's alpha = dt / (dt + 1/(2*pi*fc)) and run at the
    log rate. A cutoff scan shows which BARO_THST_FILT the pressure actually follows; on
    2026-08-20 a 4" quad's baro tracked throttle with ~0.1 s delay, so 1-1.5 Hz was best and
    the 1 Hz default was left alone.
  * The slope is fitted through the origin on SETTLED samples (|ThrOut - lpf(ThrOut)| small):
    mid-step the model error is filter lag, not scale information. The cutoff scan uses all
    samples because the steps are what identify the lag.
  * Read the per-bucket column. The response is usually mildly convex (the same quad went
    from -180 Pa/thr at idle to -300 at 0.28), and a linear parameter cannot follow that, so
    the number to set is the one that zeroes the error in the hover band, not the global
    least-squares line. The hover-band residual is printed for the recommended value.

Traps:

  * A real hover looks the same to the accelerometer as a clamped vehicle (|acc| = g in both),
    so the script cannot prove the vehicle was fixed. It prints attitude, |acc| and gyro for
    each run and flags a throttle history that looks like a hover; the operator has to know
    how the run was flown.
  * The baseline P0 is taken armed, just before throttle-up, in the run's own orientation. A
    pre-arm baseline in a different attitude can be off by ~1 Pa (0.1 m) from port sensitivity.
  * Ambient drift aliases into the slope because a ramp is monotonic in time. Keep runs under
    a minute; the armed pre-throttle window's std is printed as a drift check.
  * Only sensor 0 has a THST_SCALE parameter. BARO2 is fitted and printed for interest only.

Usage:
    baro_thst_cal.py <log.bin> [--filt HZ] [--thr-min 0.01] [--settle 0.02]
                     [--from S --to S] [--plot out.png]
"""
import argparse
import math
import sys

import numpy as np
from pymavlink import mavutil

EV_ARMED = 10
EV_DISARMED = 11
FC_SCAN = (0.0, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0)
BUCKET = 0.04
PARAMS = ('BARO1_THST_SCALE', 'BARO_THST_FILT', 'BARO_PRIMARY', 'MOT_THST_HOVER',
          'MOT_SPIN_MIN')


def lpf(x, t, fc):
    """ArduPilot LowPassFilterFloat::apply(sample, dt) run over the series."""
    y = np.empty_like(x)
    y[0] = x[0]
    if fc <= 0:
        return x.copy()
    rc = 1.0 / (2.0 * math.pi * fc)
    for i in range(1, len(x)):
        dt = t[i] - t[i - 1]
        a = dt / (dt + rc)
        y[i] = y[i - 1] + a * (x[i] - y[i - 1])
    return y


def fit_origin(x, y):
    d = np.sum(x * x)
    return np.sum(x * y) / d if d > 0 else float('nan')


def fit_line(x, y):
    if len(x) < 3:
        return float('nan'), float('nan')
    k, c = np.polyfit(x, y, 1)
    return k, c


def load(path):
    mlog = mavutil.mavlink_connection(path)
    baro = {}
    motb, imu, ang, ev = [], [], [], []
    params = {}
    while True:
        m = mlog.recv_match(type=['BARO', 'MOTB', 'IMU', 'ANG', 'EV', 'PARM'])
        if m is None:
            break
        ty = m.get_type()
        if ty == 'PARM':
            if m.Name in PARAMS:
                params[m.Name] = m.Value
            continue
        t = m.TimeUS * 1e-6
        if ty == 'BARO':
            baro.setdefault(m.I, []).append((t, m.Press, m.Alt))
        elif ty == 'MOTB':
            motb.append((t, m.ThrOut))
        elif ty == 'IMU' and m.I == 0:
            imu.append((t, math.sqrt(m.AccX ** 2 + m.AccY ** 2 + m.AccZ ** 2),
                        math.degrees(math.sqrt(m.GyrX ** 2 + m.GyrY ** 2 + m.GyrZ ** 2))))
        elif ty == 'ANG':
            ang.append((t, m.Roll, m.Pitch))
        elif ty == 'EV':
            ev.append((t, m.Id))
    if 0 not in baro or not motb:
        sys.exit('need BARO (instance 0) and MOTB in the log')
    return ({i: np.array(v) for i, v in baro.items()}, np.array(motb),
            np.array(imu) if imu else None, np.array(ang) if ang else None, ev, params)


def segments(ev, t0, t1, tmin, tmax):
    """Armed intervals, or the single --from/--to window if given."""
    if t0 is not None or t1 is not None:
        return [(t0 if t0 is not None else tmin, t1 if t1 is not None else tmax, True)]
    out = []
    arm = None
    for t, i in ev:
        if i == EV_ARMED:
            arm = t
        elif i == EV_DISARMED and arm is not None:
            out.append((arm, t, False))
            arm = None
    if arm is not None:
        out.append((arm, tmax, False))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--filt', type=float,
                    help='BARO_THST_FILT to fit at (default: value in the log, else 1 Hz)')
    ap.add_argument('--thr-min', type=float, default=0.01,
                    help='ThrOut above this counts as throttle-up (default 0.01)')
    ap.add_argument('--settle', type=float, default=0.02,
                    help='skip samples with |ThrOut - lpf(ThrOut)| above this in the slope fit')
    ap.add_argument('--from', dest='t0', type=float, help='analyse only this window (s, TimeUS)')
    ap.add_argument('--to', dest='t1', type=float)
    ap.add_argument('--plot', help='save a dP-vs-throttle and before/after plot here (.png)')
    a = ap.parse_args()

    baro, motb, imu, ang, ev, params = load(a.log)
    b0 = baro[0]
    t = b0[:, 0]
    P = b0[:, 1]
    alt = b0[:, 2]
    thr = np.interp(t, motb[:, 0], motb[:, 1], left=0.0, right=0.0)
    P2 = np.interp(t, baro[1][:, 0], baro[1][:, 1]) if 1 in baro else None
    accn = np.interp(t, imu[:, 0], imu[:, 1]) if imu is not None else None
    gyrn = np.interp(t, imu[:, 0], imu[:, 2]) if imu is not None else None
    roll = np.interp(t, ang[:, 0], ang[:, 1]) if ang is not None else None
    pitch = np.interp(t, ang[:, 0], ang[:, 2]) if ang is not None else None

    fc = a.filt if a.filt is not None else params.get('BARO_THST_FILT', 1.0)
    hover = params.get('MOT_THST_HOVER')
    print(a.log)
    print('  log: BARO1_THST_SCALE=%s  BARO_THST_FILT=%s  BARO_PRIMARY=%s  MOT_THST_HOVER=%s'
          % tuple(params.get(k, '?') for k in ('BARO1_THST_SCALE', 'BARO_THST_FILT',
                                               'BARO_PRIMARY', 'MOT_THST_HOVER')))
    print('  fitting at BARO_THST_FILT = %.2f Hz; throttle source MOTB.ThrOut; '
          'pressure source BARO.Press (raw)' % fc)
    thr_f = lpf(thr, t, fc)
    settled = np.abs(thr - thr_f) <= a.settle

    runs = []
    plots = []
    for seg_i, (ta, td, manual) in enumerate(segments(ev, a.t0, a.t1, t[0], t[-1])):
        up = np.where((t >= ta) & (t < td) & (thr > a.thr_min))[0]
        if len(up) == 0:
            continue
        ts = t[up[0]]
        run = (t >= ts) & (t < td)
        if run.sum() < 20:
            continue
        # baseline: armed, motors at spin-arm, same orientation as the run
        base = (t >= max(ta, ts - 3.0)) & (t < ts - 0.2)
        note = ''
        if base.sum() < 5:
            base = (t >= ts - 3.0) & (t < ts - 0.2)
            note = '  (baseline is PRE-ARM: less than 1 s armed before throttle-up)'
        if base.sum() < 5:
            print('\n=== run %d: no baseline before throttle-up at %.1f s, skipped'
                  % (seg_i + 1, ts))
            continue
        P0 = np.median(P[base])
        dP = P - P0
        # local Pa/m from the log's own altitude conversion
        k_alt = np.polyfit(P[run], alt[run], 1)[0]
        pa_per_m = -1.0 / k_alt if k_alt != 0 else float('nan')

        print('\n=== run %d: %s %.1f s, throttle-up %.1f s, end %.1f s (%.1f s of data) ==='
              % (seg_i + 1, 'window' if manual else 'armed', ta, ts, td, td - ts))
        print('  baseline P0 %.1f Pa over %.1f s, std %.2f Pa%s'
              % (P0, t[base][-1] - t[base][0], np.std(P[base]), note))
        if pitch is not None:
            print('  attitude during run: roll %+.0f deg, pitch %+.0f deg (mean)'
                  % (np.mean(roll[run]), np.mean(pitch[run])))
        if accn is not None:
            print('  |acc| %.2f +- %.2f m/s2, |gyro| %.1f deg/s mean -- consistent with a fixed '
                  'vehicle only if you know it was fixed; a free hover reads the same'
                  % (np.mean(accn[run]), np.std(accn[run]), np.mean(gyrn[run])))
        if hover is not None:
            near_hover = np.mean(np.abs(thr[run] - hover) < 0.03)
            if near_hover > 0.5 and pitch is not None and abs(np.mean(pitch[run])) < 20:
                print('  WARNING: %.0f%% of the run sits within 0.03 of MOT_THST_HOVER with the '
                      'vehicle level -- this looks like a hover, not a bench ramp. The fit is '
                      'only valid if the airframe was physically restrained.'
                      % (100 * near_hover))
        print('  ThrOut %.3f..%.3f, dP %+.1f..%+.1f Pa, BARO.Alt excursion %+.2f m '
              '(%.2f Pa/m locally)'
              % (thr[run].min(), thr[run].max(), dP[run].min(), dP[run].max(),
                 alt[run].max() - np.median(alt[base]), pa_per_m))

        sel = run & settled
        k = fit_origin(thr_f[sel], dP[sel])
        k_l, c_l = fit_line(thr_f[sel], dP[sel])
        res = dP[sel] - k * thr_f[sel]
        print('  slope at %.2f Hz on %d settled samples (%d dropped mid-step): '
              'k = %.1f Pa/thr, resid std %.2f Pa (%.2f m)'
              % (fc, sel.sum(), run.sum() - sel.sum(), k, np.std(res),
                 np.std(res) / pa_per_m))
        print('  with intercept: k = %.1f, c = %+.1f Pa (intercept is not a firmware option; '
              'a large one means the response is not proportional)' % (k_l, c_l))
        if P2 is not None:
            k2 = fit_origin(thr_f[sel], (P2 - np.median(P2[base]))[sel])
            print('  BARO2 slope %.1f Pa/thr (no parameter for it; info only)' % k2)

        print('  cutoff scan, through-origin fit on all run samples:')
        best = None
        for f in FC_SCAN:
            tf = thr_f if f == fc else lpf(thr, t, f)
            kk = fit_origin(tf[run], dP[run])
            sd = np.std(dP[run] - kk * tf[run])
            print('    fc %4.1f Hz: k %7.1f  resid %.2f Pa%s'
                  % (f, kk, sd, '  (no filter)' if f == 0 else ''))
            if best is None or sd < best[1]:
                best = (f, sd)
        print('    best %.1f Hz (BARO_THST_FILT=%.1f in use)' % (best[0], fc))

        print('  per bucket of filtered ThrOut:')
        print('    %10s %5s %9s %9s %9s %10s' % ('thr', 'n', 'dP Pa', 'err m', 'dP/thr', 'resid@k'))
        lo = 0.0
        while lo < thr_f[run].max():
            bm = sel & (thr_f >= lo) & (thr_f < lo + BUCKET)
            if bm.sum() >= 5:
                mdp = np.mean(dP[bm])
                mtf = np.mean(thr_f[bm])
                tag = ''
                if hover is not None and lo <= hover < lo + BUCKET:
                    tag = '  <-- hover'
                print('    %4.2f-%4.2f %5d %+9.1f %+9.2f %9.1f %+10.1f%s'
                      % (lo, lo + BUCKET, bm.sum(), mdp, -mdp / pa_per_m, mdp / mtf,
                         mdp - k * mtf, tag))
            lo += BUCKET
        runs.append((seg_i + 1, k, sel, run, dP))
        plots.append((seg_i + 1, run, sel, dP, thr_f, alt, k, pa_per_m, P2,
                      np.median(P2[base]) if P2 is not None else None))

    if not runs:
        sys.exit('no armed run with a throttle ramp and a baseline found')

    # combined fit and the hover-band check for the candidate value
    sel_all = np.zeros_like(t, dtype=bool)
    dp_all = np.zeros_like(t)
    for _, _, sel, run, dP in runs:
        sel_all |= sel
        dp_all[run] = dP[run]
    k_all = fit_origin(thr_f[sel_all], dp_all[sel_all])
    rec = 5.0 * round(k_all / 5.0)
    print('\n=== combined over %d run(s): global slope k = %.1f Pa/thr ===' % (len(runs), k_all))
    if hover is not None:
        hb = sel_all & (np.abs(thr_f - hover) < 0.03)
        if hb.sum() >= 10:
            k_h = fit_origin(thr_f[hb], dp_all[hb])
            rec = 5.0 * round(k_h / 5.0)
            r = dp_all[hb] - rec * thr_f[hb]
            print('  hover band (%.2f +- 0.03, n=%d) slope %.1f Pa/thr -- used for the '
                  'recommendation since a linear parameter cannot follow a bent bucket column'
                  % (hover, hb.sum(), k_h))
            print('  hover band residual with SCALE=%.0f: %+.1f Pa' % (rec, np.mean(r)))
        else:
            print('  no samples in the hover band (%.2f +- 0.03); recommendation is the global '
                  'slope' % hover)
    cur = params.get('BARO1_THST_SCALE')
    print('\n  recommend BARO1_THST_SCALE = %.0f  (replaces the logged %s; BARO.Press is '
          'uncompensated so the fit is the total)' % (rec, cur if cur is not None else '?'))
    if abs(rec) > 300:
        print('  NOTE: |value| exceeds the parameter metadata range of 300 Pa')
    if hover is not None:
        print('  uncompensated error at hover throttle would be ~%.1f m'
              % (-rec * hover / pa_per_m))

    if a.plot:
        try:
            import matplotlib
            matplotlib.use('Agg')
            import matplotlib.pyplot as plt
        except ImportError:
            sys.exit('--plot needs matplotlib')
        n = len(plots)
        fig, axes = plt.subplots(n, 2, figsize=(14, 4.5 * n), squeeze=False)
        for row, (ri, run, sel, dP, tf, al, k, ppm, p2, p20) in zip(axes, plots):
            ax = row[0]
            ax.scatter(tf[run], dP[run], s=4, alpha=0.4, label='BARO1 all')
            ax.scatter(tf[sel], dP[sel], s=6, label='BARO1 settled')
            if p2 is not None:
                ax.scatter(tf[run], (p2 - p20)[run], s=4, alpha=0.4, label='BARO2')
            xx = np.linspace(0, tf[run].max(), 10)
            ax.plot(xx, k * xx, 'r-', label='fit k=%.0f' % k)
            ax.plot(xx, rec * xx, 'k--', label='SCALE=%.0f' % rec)
            ax.set_xlabel('lpf(ThrOut, %.1f Hz)' % fc)
            ax.set_ylabel('P_raw - P0 [Pa]')
            ax.set_title('run %d: pressure change vs filtered throttle' % ri)
            ax.grid(True)
            ax.legend()
            ax = row[1]
            base_alt = al[run][0]
            ax.plot(t[run], al[run] - base_alt, label='BARO.Alt raw')
            ax.plot(t[run], al[run] - base_alt + rec * tf[run] / ppm,
                    label='compensated with %.0f' % rec)
            ax.plot(t[run], thr[run] * 10, alpha=0.6, label='ThrOut x10')
            ax.set_xlabel('t [s]')
            ax.set_ylabel('m')
            ax.set_title('run %d: baro altitude before/after' % ri)
            ax.grid(True)
            ax.legend()
        plt.tight_layout()
        plt.savefig(a.plot, dpi=90)
        print('  plot saved to %s' % a.plot)


if __name__ == '__main__':
    main()
