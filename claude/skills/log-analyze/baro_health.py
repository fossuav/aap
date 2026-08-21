#!/usr/bin/env python3
"""Is the barometer usable for altitude control on this airframe, and is the vertical
chain (accel, EKF height, throttle loop) in a state to use it?

VIBE and CTUN plots tell you an altitude hold was rough. They do not tell you whether the
baro sits in prop wash, whether the accelerometer is clipping, whether the EKF is leaning
on GPS vertical velocity to survive, or whether the vertical controller has been detuned
to hide all that. This reads the flight(s) out of a log and prints, per armed segment:

  * spool-up table: throttle against baro-minus-EKF while still landed, then the first
    seconds airborne. A baro that falls metres while the vehicle has not moved is ground
    effect / prop recirculation on the static port; it snaps back on lift-off. This is
    NOT what BARO1_THST_SCALE compensates (that is a free-air, thrust-proportional error)
    and applying it makes free-air altitude wrong by the same metres.
  * hover block: baro-minus-EKF mean/std/min/max, baro high-pass noise, baro climb-rate
    std, EKF height test ratio, height source, GPS fix and VZ noise, VIBE and clip count,
    accel Z std, throttle mean/std against the learned hover throttle, and the vertical
    controller's position/velocity/accel tracking and PID contributions (PSCD/PIDA).
  * end-of-segment note if the segment ends in a motor e-stop or with clipping spikes.

How to read it (numbers from real airframes):
  * Baro-EKF swinging -5..-10 m on the ground at hover throttle, back to ~0 within 2 s of
    lift-off, and dips of 1-3 m whenever below ~2 m AGL: the port is in the wash. Fix is
    shielding / relocation / a downward rangefinder for the last metres, not a parameter.
    ALT_HOLD will cut or add throttle on every bounce near the ground; that is how a
    landing turns into an e-stop and a 4 g impact.
  * Baro-EKF mean offset that scales with throttle in FREE air: that is BARO1_THST_SCALE
    territory; baro_thst_cal.py fits it from a fixed-vehicle ramp.
  * VIBE above ~30 m/s2 or a rising clip count with PIDA Act std >> Tar std: the accel
    feedback is noise and someone will have strangled PSC_D_ACC_P/I to keep the throttle
    quiet (rule of thumb P ~ MOT_THST_HOVER, I ~ 2x). Fix vibration first; there is
    nothing to tune vertically until then.
  * XKF4.SH climbing / height source flipping: the EKF is rejecting the baro; look at
    what it falls back on (GPS VZ aiding hides a lot outdoors and nothing indoors).

Segments are taken from EV ARMED/DISARMED plus NOT_LANDED / LAND_COMPLETE; --from/--to
overrides them with one explicit window. Time is the same clock as log_extract.py.

Usage:
    baro_health.py <log.bin> [--from-time S --to-time S] [--table] [--hover-from S --hover-to S]
"""
import argparse
import sys

import numpy as np

from pymavlink import mavutil

EV_ARMED, EV_DISARMED, EV_NOT_LANDED, EV_LAND_COMPLETE = 10, 11, 28, 18
EV_MOTORS_EMERGENCY_STOPPED = 54
PARAMS = ('BARO1_THST_SCALE', 'BARO_THST_FILT', 'BARO1_WCF_ENABLE', 'GND_EFFECT_COMP', 'TKOFF_GNDEFF_ALT',
          'TKOFF_GNDEFF_TMO', 'EK3_SRC1_POSZ', 'EK3_SRC1_VELZ', 'EK3_RNG_USE_HGT', 'EK3_ALT_M_NSE',
          'EK3_GND_EFF_DZ', 'RNGFND1_TYPE', 'MOT_THST_HOVER', 'MOT_HOVER_LEARN', 'PSC_D_ACC_P', 'PSC_D_ACC_I',
          'PSC_ACCZ_P', 'PSC_ACCZ_I', 'PSC_D_VEL_P', 'PSC_POSZ_P', 'PSC_D_POS_P', 'INS_ACCEL_FILTER',
          'INS_ACC_VRFB_Z', 'ACC_ZBIAS_LEARN', 'PILOT_SPD_UP', 'PILOT_SPD_DN', 'PILOT_ACC_Z')


def time_base(path):
    """log_extract.get_time_base() takes the very first message of any type; match it."""
    mlog = mavutil.mavlink_connection(path)
    m = mlog.recv_msg()
    return m._timestamp if m is not None else 0.0


def collect(path):
    base = time_base(path)
    mlog = mavutil.mavlink_connection(path)
    D = {k: [] for k in ('CTUN', 'BARO', 'GPS', 'IMU', 'VIBE', 'XKF4', 'XKFR', 'PSCD', 'PIDA',
                         'EV', 'ESC', 'RCIN')}
    parms = {}
    while True:
        x = mlog.recv_match(type=list(D.keys()) + ['PARM'])
        if x is None:
            break
        ty = x.get_type()
        if ty == 'PARM':
            parms[x.Name] = x.Value
            continue
        t = x._timestamp - base
        if ty == 'CTUN':
            D[ty].append((t, x.ThI, x.ThO, x.ThH, x.Alt, x.BAlt, x.DAlt, x.CRt, x.DCRt))
        elif ty == 'BARO' and x.I == 0:
            D[ty].append((t, x.Alt, x.CRt, x.Press, x.Temp))
        elif ty == 'GPS' and x.I == 0:
            D[ty].append((t, x.Status, x.NSats, x.HDop, x.VZ))
        elif ty == 'IMU' and x.I == 0:
            D[ty].append((t, x.AccX, x.AccY, x.AccZ))
        elif ty == 'VIBE' and x.IMU == 0:
            D[ty].append((t, x.VibeX, x.VibeY, x.VibeZ, x.Clip))
        elif ty == 'XKF4' and x.C == 0:
            D[ty].append((t, x.SH, x.SV, x.SP))
        elif ty == 'XKFR' and x.C == 0:
            D[ty].append((t, x.HSrc, x.ZSrc))
        elif ty == 'PSCD':
            D[ty].append((t, x.TPD, x.PD, x.TVD, x.VD, x.TAD, x.AD))
        elif ty == 'PIDA':
            D[ty].append((t, x.Tar, x.Act, x.P, x.I, x.D, x.FF))
        elif ty == 'EV':
            D[ty].append((t, x.Id))
        elif ty == 'ESC':
            D[ty].append((t, x.Instance, x.RPM))
    return {k: np.asarray(v, dtype=float) for k, v in D.items()}, parms


def win(a, t0, t1):
    if len(a) == 0:
        return a
    return a[(a[:, 0] >= t0) & (a[:, 0] <= t1)]


def segments(D):
    """one segment per flight: (t_arm, t_end_of_arming, t_notlanded, t_landed, t_estop).

    Flights are NOT_LANDED..LAND_COMPLETE pairs; several can share one arming. A log that
    starts already armed (rotated mid-flight) gets t_arm = first CTUN time."""
    ev = D['EV']
    t_first = D['CTUN'][0, 0] if len(D['CTUN']) else 0.0
    t_last = D['CTUN'][-1, 0] if len(D['CTUN']) else 0.0
    segs, armed_t, cur = [], None, None
    for t, i in ev:
        i = int(i)
        if i == EV_ARMED:
            armed_t = t
        elif i == EV_NOT_LANDED and cur is None:
            cur = [armed_t if armed_t is not None else t_first, None, t, None, None]
        elif cur is not None and i == EV_MOTORS_EMERGENCY_STOPPED and cur[4] is None:
            cur[4] = t
        elif cur is not None and i in (EV_LAND_COMPLETE, EV_DISARMED):
            cur[3] = t
            cur[1] = t
            segs.append(tuple(cur))
            cur = None
            if i == EV_DISARMED:
                armed_t = None
    if cur is not None:
        cur[1] = cur[3] = t_last
        segs.append(tuple(cur))
    return segs


def hover_window(D, t_to, t_end):
    """Quietest 20 s (lowest CTUN.ThO std) of the airborne part, at least 5 s after lift-off."""
    c = win(D['CTUN'], t_to + 5, t_end)
    if len(c) < 50:
        return (t_to + 5, t_end)
    best, best_std = None, 1e9
    for ws in np.arange(c[0, 0], max(c[0, 0], c[-1, 0] - 20) + 0.1, 2.0):
        s = c[(c[:, 0] >= ws) & (c[:, 0] < ws + 20)]
        if len(s) < 50:
            continue
        sd = s[:, 2].std() + 0.02 * np.abs(s[:, 7]).mean()
        if sd < best_std:
            best_std, best = sd, ws
    return (best, best + 20) if best is not None else (c[0, 0], c[-1, 0])


def spoolup_table(D, t_arm, t_to, t_end):
    print('  spool-up / lift-off, 1 s bins (ThO against baro-minus-EKF; EKF alt; ESC rpm; VibeZ):')
    t0 = max(t_arm, t_to - 20)
    for ws in np.arange(np.floor(t0), min(t_to + 8, t_end), 1.0):
        c = win(D['CTUN'], ws, ws + 1)
        if len(c) < 1:
            continue
        e = win(D['ESC'], ws, ws + 1)
        v = win(D['VIBE'], ws, ws + 1)
        tag = 'landed' if ws < t_to else 'AIR'
        rpm = e[:, 2].mean() if len(e) else 0
        vz = v[:, 3].mean() if len(v) else 0
        print(f'    {ws:7.0f}s {tag:6s} ThO {c[:, 2].mean():.3f}  EKF {c[:, 4].mean():6.2f} m  '
              f'baro {c[:, 5].mean():6.2f} m  B-E {c[:, 5].mean() - c[:, 4].mean():+6.2f} m  '
              f'rpm {rpm:5.0f}  VibeZ {vz:5.1f}')


def hover_block(D, parms, h0, h1):
    c, b, g, i, v, k, r = (win(D[x], h0, h1)
                           for x in ('CTUN', 'BARO', 'GPS', 'IMU', 'VIBE', 'XKF4', 'XKFR'))
    if len(c) < 10:
        print('  hover: not enough CTUN data')
        return
    be = c[:, 5] - c[:, 4]
    print(f'  hover {h0:.0f}-{h1:.0f} s:')
    print(f'    ThO mean {c[:, 2].mean():.3f} std {c[:, 2].std():.4f} | learned hover {c[:, 3].mean():.3f} '
          f'| EKF alt {c[:, 4].mean():.2f} m')
    print(f'    baro-EKF mean {be.mean():+.2f} std {be.std():.2f} min {be.min():+.2f} max {be.max():+.2f} m')
    if len(b) > 20:
        hp = b[:, 1] - np.convolve(b[:, 1], np.ones(10) / 10, 'same')
        print(f'    baro hp noise std {hp[5:-5].std():.3f} m | baro CRt std {b[:, 2].std():.2f} m/s '
              f'| baro temp {b[:, 4].mean():.1f} C')
    if len(k):
        print(f'    EKF height test ratio SH mean {k[:, 1].mean():.2f} max {k[:, 1].max():.2f} '
              f'| SV {k[:, 2].mean():.2f} SP {k[:, 3].mean():.2f}')
    if len(r):
        hsrc = sorted(set(int(v) for v in r[:, 1]))
        zsrc = sorted(set(int(v) for v in r[:, 2]))
        print(f'    XKFR height source {hsrc} (1 baro 2 rng 3 gps 4 beacon 6 extnav) '
              f'vertical vel source {zsrc}')
    if len(g):
        gps_note = ('   <- EK3_SRC1_VELZ is GPS: vertical velocity leans on GPS'
                    if int(parms.get('EK3_SRC1_VELZ', 0)) == 3 else '')
        print(f'    GPS status {g[:, 1].min():.0f}-{g[:, 1].max():.0f} sats {g[:, 2].mean():.1f} '
              f'hdop {g[:, 3].mean():.2f} VZ std {g[:, 4].std():.2f} m/s{gps_note}')
    if len(v):
        clips = v[-1, 4] - v[0, 4]
        vib_note = ('   <- above ~30 / clipping: accel feedback is noise'
                    if v[:, 3].mean() > 30 or clips > 0 else '')
        print(f'    VIBE X {v[:, 1].mean():.1f} Y {v[:, 2].mean():.1f} Z {v[:, 3].mean():.1f} m/s2 '
              f'| clips in window {clips:.0f} (total {v[-1, 4]:.0f}){vib_note}')
    if len(i):
        print(f'    IMU accel Z mean {i[:, 3].mean():.2f} std {i[:, 3].std():.2f} m/s2 '
              f'| X {i[:, 1].mean():+.2f} Y {i[:, 2].mean():+.2f}')
    p, a = win(D['PSCD'], h0, h1), win(D['PIDA'], h0, h1)
    if len(p) > 10:
        pe, ve = p[:, 1] - p[:, 2], p[:, 3] - p[:, 4]
        print(f'    PSCD tracking: pos err mean {pe.mean():+.3f} std {pe.std():.3f} m '
              f'| vel err std {ve.std():.3f} m/s | accel target std {p[:, 5].std():.2f} '
              f'vs measured std {p[:, 6].std():.2f} m/s2')
    if len(a) > 10 and a[:, 1].std() == 0 and a[:, 2].std() == 0:
        print('    PIDA: inactive (manual-throttle mode), vertical controller not judged')
    elif len(a) > 10:
        print(f'    PIDA: Tar std {a[:, 1].std():.2f} Act std {a[:, 2].std():.2f} | P std {a[:, 3].std():.4f} '
              f'I mean {a[:, 4].mean():+.4f} D std {a[:, 5].std():.4f} FF mean {a[:, 6].mean():+.4f}')
        accp = parms.get('PSC_D_ACC_P', parms.get('PSC_ACCZ_P'))
        if accp is not None and parms.get('MOT_THST_HOVER'):
            note = '   <- strangled' if accp < 0.3 * parms['MOT_THST_HOVER'] else ''
            print(f'    PSC accel P {accp:.3f} against hover-throttle rule of thumb '
                  f'~{parms["MOT_THST_HOVER"]:.3f}{note}')


def table(D, t0, t1):
    print(f"  {'t':>7s} {'ThO':>6s} {'EKF':>7s} {'baro':>7s} {'B-E':>6s} {'DAlt':>7s} {'CRt':>6s} "
          f"{'DCRt':>6s} {'SH':>5s} {'VibeZ':>6s} {'clip':>5s}")
    for ws in np.arange(np.floor(t0), t1, 1.0):
        c = win(D['CTUN'], ws, ws + 1)
        if len(c) < 1:
            continue
        k, v = win(D['XKF4'], ws, ws + 1), win(D['VIBE'], ws, ws + 1)
        sh = k[:, 1].mean() if len(k) else 0
        vz, clip = (v[:, 3].mean(), v[-1, 4]) if len(v) else (0, 0)
        print(f'  {ws:7.0f} {c[:, 2].mean():6.3f} {c[:, 4].mean():7.2f} {c[:, 5].mean():7.2f} '
              f'{c[:, 5].mean() - c[:, 4].mean():+6.2f} {c[:, 6].mean():7.2f} {c[:, 7].mean():6.2f} '
              f'{c[:, 8].mean():6.2f} {sh:5.2f} {vz:6.1f} {clip:5.0f}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--from-time', type=float)
    ap.add_argument('--to-time', type=float)
    ap.add_argument('--hover-from', type=float, help='override the auto-picked hover window')
    ap.add_argument('--hover-to', type=float)
    ap.add_argument('--table', action='store_true',
                    help='1 s table over each segment (or the window)')
    args = ap.parse_args()

    D, parms = collect(args.log)
    if len(D['CTUN']) == 0:
        sys.exit('no CTUN in this log (copter only)')
    print(f'{args.log}')
    print('  ' + '  '.join(f'{k}={parms[k]:g}' for k in PARAMS if k in parms))

    if args.from_time is not None and args.to_time is not None:
        segs = [(args.from_time, args.to_time, args.from_time, None, None)]
    else:
        segs = segments(D)
        if not segs:
            sys.exit('no armed+airborne segment found; use --from-time/--to-time')
    for n, (t_arm, t_dis, t_to, t_land, t_estop) in enumerate(segs, 1):
        t_end = t_land if t_land else t_dis
        estop = (f', MOTOR E-STOP at {t_estop:.1f} s'
                 if t_estop and t_estop <= t_end + 1.0 else '')
        print(f'\n=== segment {n}: armed {t_arm:.1f} s, airborne {t_to:.1f}-{t_end:.1f} s'
              f'{estop}')
        if args.from_time is None:
            spoolup_table(D, t_arm, t_to, t_end)
        if args.hover_from is not None and args.hover_to is not None:
            h0, h1 = args.hover_from, args.hover_to
        else:
            h0, h1 = hover_window(D, t_to, t_end)
        hover_block(D, parms, h0, h1)
        v = win(D['VIBE'], t_arm, t_dis)
        if len(v) and v[-1, 4] - v[0, 4] > 0:
            print(f'  clips over the segment: {v[-1, 4] - v[0, 4]:.0f}')
        if args.table:
            t0 = t_arm if args.from_time is None else args.from_time
            t1 = t_dis if args.from_time is None else args.to_time
            table(D, t0, t1)


if __name__ == '__main__':
    main()
