#!/usr/bin/env python3
"""Where is the oscillation, which axis owns it, and is the controller driving it?

rate_response.py says whether a loop is under-damped at its closed-loop peak, below ~10 Hz.
This is for the other case: a band above that -- 15-40 Hz on a small quad -- that shows up
as a hump in the gyro and in the controller output. It reads the RATE/PIDR/PIDP/PIDY
streams (at whatever rate they were logged; the fast-rate thread gives ~1 kHz) and, for a
chosen band, prints:

  * rate, output and demand RMS in the band per axis, and at the dominant peak
  * whether P or D is carrying the output there (PIDx.P against PIDx.D in-band RMS)
  * coherence and phase rate -> output, axis -> axis, and rate -> demand at the peak
  * the band second by second: a steady tone or bursts
  * with --vs, the same for a second log/window and the deltas -- the A/B

The two mechanisms that live in this band look alike in a PSD and need opposite fixes:

  loop mode -- the rate loop's own crossover with thin phase margin
      one axis dominates; rate -> output coherence ~1 with output lagging 130-150 deg
      (that is P + D.s through FLTD); D term > P term in the band; broad (Q ~ 5), bursty,
      no harmonics; and the frequency MOVES when the gain changes. Fix: lower that axis's
      D (and P with it, to hold the P/D corner) or buy phase (INS_GYRO_FILTER, FLTD up).
      A notch here just moves the crossover and costs phase below it.
  structural / vibration
      sharp line at the same frequency on roll, pitch and yaw, in phase across axes,
      present pre-filter on every IMU (batch_fft.py), often with a harmonic; the frequency
      does not move with gain. Fix: static notch (INS_HNTC2) or mechanical.

An A/B of a gain change needs three numbers that move in different directions if the
change is wrong: in-band rate and output RMS from here, the closed-loop damping at the
low-frequency peak from rate_response.py (must not fall), and the rate error RMS it
prints (must not rise). On 2026-08-21 a roll P/D cut on an FPV quad took the 25 Hz roll
band down 44% at the peak and 29% across 15-40 Hz with the 9 Hz damping unchanged
(zeta 0.45 -> 0.44) and the peak moved 26 -> 24 Hz: a loop mode. ANG_P and P-only cuts
barely touch a D-dominated band -- read the P-against-D split before choosing the knob.

Traps:
  * RATE.*Des shares the gyro with RATE.* (see rate_response.py). Rate -> demand coherence
    here says how much of the band leaks into the angle loop, not that the demand causes it.
  * The per-second trend is the band-passed signal. A bursty band has a worst second
    several times the window RMS, and the worst second is what the pilot feels.
  * Time is on the same clock as log_extract.py (first message of the log is zero). Check
    the covered span it prints against the window you asked for.

Usage:
    rate_band.py <log.bin> --from-time S --to-time S [--band 15 40]
                 [--vs <log2.bin> --vs-from S --vs-to S] [--png out.png]
"""
import argparse
import sys

import numpy as np

try:
    from scipy import signal
except ImportError:
    sys.exit('rate_band.py needs scipy (pip install scipy)')

from pymavlink import mavutil

_trapz = getattr(np, 'trapezoid', None) or np.trapz

AXES = (('roll', 'R', 'ROut', 'RDes', 'PIDR'),
        ('pitch', 'P', 'POut', 'PDes', 'PIDP'),
        ('yaw', 'Y', 'YOut', 'YDes', 'PIDY'))
SUBBANDS = ((0.2, 3), (3, 10), (10, 20), (20, 30), (30, 45), (45, 80), (80, 200))


def time_base(path):
    """log_extract.get_time_base() takes the very first message of any type (the first FMT);
    match it so --from-time/--to-time mean the same thing in every tool."""
    mlog = mavutil.mavlink_connection(path)
    m = mlog.recv_msg()
    return m._timestamp if m is not None else 0.0


def collect(path, t0, t1):
    base = time_base(path)
    mlog = mavutil.mavlink_connection(path)
    rate = {k: [] for k in ('t', 'R', 'P', 'Y', 'ROut', 'POut', 'YOut', 'RDes', 'PDes', 'YDes')}
    pid = {n: {'t': [], 'P': [], 'D': []} for n in ('PIDR', 'PIDP', 'PIDY')}
    while True:
        m = mlog.recv_match(type=['RATE', 'PIDR', 'PIDP', 'PIDY'])
        if m is None:
            break
        t = m._timestamp - base
        if t < t0:
            continue
        if t > t1:
            break
        ty = m.get_type()
        if ty == 'RATE':
            rate['t'].append(t)
            for k in rate:
                if k != 't':
                    rate[k].append(getattr(m, k))
        else:
            pid[ty]['t'].append(t)
            pid[ty]['P'].append(m.P)
            pid[ty]['D'].append(m.D)
    rate = {k: np.asarray(v, dtype=float) for k, v in rate.items()}
    pid = {n: {k: np.asarray(v, dtype=float) for k, v in d.items()} for n, d in pid.items()}
    return rate, pid


def welch(x, fs, nperseg):
    return signal.welch(x - x.mean(), fs=fs, nperseg=nperseg, noverlap=nperseg // 2)


def band_rms(f, p, lo, hi):
    sel = (f >= lo) & (f <= hi)
    if sel.sum() < 2:
        return 0.0
    return float(np.sqrt(_trapz(p[sel], f[sel])))


def top_peaks(f, p, lo, hi, n=4):
    sel = (f >= lo) & (f <= hi)
    fi, pi = f[sel], p[sel]
    if len(fi) < 3:
        return []
    idx, _ = signal.find_peaks(pi)
    idx = idx[np.argsort(pi[idx])[::-1]][:n]
    return sorted((float(fi[i]), float(pi[i])) for i in idx)


def analyse(path, t0, t1, lo, hi, nperseg):
    rate, pid = collect(path, t0, t1)
    t = rate['t']
    if len(t) < nperseg * 2:
        sys.exit(f'{path}: only {len(t)} RATE samples in {t0}-{t1} s, need at least {nperseg * 2}. '
                 'Widen the window or check the vehicle was armed.')
    fs = 1.0 / np.median(np.diff(t))
    res = {'path': path, 't0': t0, 't1': t1, 'lo': lo, 'hi': hi, 'fs': fs, 'n': len(t),
           'span': (float(t[0]), float(t[-1])), 'rate': rate, 'pid': pid, 'nperseg': nperseg}
    spec = {}
    for k in ('R', 'P', 'Y', 'ROut', 'POut', 'YOut', 'RDes', 'PDes', 'YDes'):
        spec[k] = welch(rate[k], fs, nperseg)
    for n, d in pid.items():
        if len(d['t']) >= nperseg * 2:
            pfs = 1.0 / np.median(np.diff(d['t']))
            spec[n + '.P'] = welch(d['P'], pfs, nperseg)
            spec[n + '.D'] = welch(d['D'], pfs, nperseg)
    res['spec'] = spec

    f = spec['R'][0]
    total = spec['R'][1] + spec['P'][1] + spec['Y'][1]
    sel = (f >= lo) & (f <= hi)
    fpk = float(f[sel][np.argmax(total[sel])])
    res['fpk'] = fpk

    per_axis = {}
    for name, r, o, d, pidn in AXES:
        fr, pr = spec[r]
        a = {'band': band_rms(fr, pr, lo, hi), 'peak_f': float(fr[sel][np.argmax(pr[sel])]),
             'at_peak': band_rms(fr, pr, fpk - 1.5, fpk + 1.5),
             'out_band': band_rms(*spec[o], lo, hi), 'out_at_peak': band_rms(*spec[o], fpk - 1.5, fpk + 1.5),
             'des_band': band_rms(*spec[d], lo, hi),
             'peaks': top_peaks(fr, pr, lo, hi), 'out_peaks': top_peaks(*spec[o], lo, hi)}
        if pidn + '.P' in spec:
            a['pid_p'] = band_rms(*spec[pidn + '.P'], lo, hi)
            a['pid_d'] = band_rms(*spec[pidn + '.D'], lo, hi)
        per_axis[name] = a
    res['axis'] = per_axis

    pairs = (('R', 'ROut'), ('P', 'POut'), ('Y', 'YOut'), ('R', 'P'), ('R', 'Y'), ('P', 'Y'),
             ('ROut', 'POut'), ('R', 'RDes'), ('P', 'PDes'), ('Y', 'YDes'))
    coh = {}
    for a, b in pairs:
        xa, xb = rate[a] - rate[a].mean(), rate[b] - rate[b].mean()
        fc, c = signal.coherence(xa, xb, fs=fs, nperseg=nperseg)
        _, pxy = signal.csd(xa, xb, fs=fs, nperseg=nperseg)
        i = int(np.argmin(np.abs(fc - fpk)))
        coh[(a, b)] = (float(c[i]), float(np.degrees(np.angle(pxy[i]))))
    res['coh'] = coh

    blo, bhi = max(0.5, fpk - 2.0), min(fs / 2 - 1.0, fpk + 2.0)
    sos = signal.butter(4, [blo, bhi], btype='band', fs=fs, output='sos')
    bp = {k: signal.sosfiltfilt(sos, rate[k] - rate[k].mean()) for k in ('R', 'P', 'Y', 'ROut', 'POut')}
    trend = []
    for ws in np.arange(np.floor(t0), np.ceil(t1), 1.0):
        s = (t >= ws) & (t < ws + 1)
        if s.sum() < fs * 0.5:
            continue
        trend.append((float(ws),) + tuple(float(np.sqrt(np.mean(bp[k][s] ** 2)))
                                          for k in ('R', 'P', 'Y', 'ROut', 'POut')))
    res['trend'] = trend
    res['trend_band'] = (blo, bhi)
    return res


def fmt_peaks(pk):
    return ', '.join(f'{pf:.1f}' for pf, _ in pk) + ' Hz' if pk else '-'


def report(res):
    lo, hi, fpk = res['lo'], res['hi'], res['fpk']
    print(f"{res['n']} RATE samples at {res['fs']:.0f} Hz, asked {res['t0']}-{res['t1']} s, "
          f"covered {res['span'][0]:.1f}-{res['span'][1]:.1f} s")
    print('\n=== sub-band RMS (rates in dps, outputs as fraction of full authority) ===')
    cols = ' '.join(f'{lo_:g}-{hi_:g}'.rjust(9) for lo_, hi_ in SUBBANDS)
    cols += f'   [{lo:g}-{hi:g}]'.rjust(11)
    print(f"  {'':6s}{cols}")
    for k in ('R', 'P', 'Y', 'ROut', 'POut', 'YOut', 'RDes', 'PDes'):
        f, p = res['spec'][k]
        vals = [band_rms(f, p, a, b) for a, b in SUBBANDS] + [band_rms(f, p, lo, hi)]
        fmt = '{:9.3f}' if k in ('R', 'P', 'Y', 'RDes', 'PDes') else '{:9.4f}'
        print(f'  {k:6s}' + ' '.join(fmt.format(v) for v in vals[:-1]) + '  ' + fmt.format(vals[-1]))

    print(f'\n=== {lo:g}-{hi:g} Hz band: dominant peak {fpk:.1f} Hz (sum of the three rate spectra) ===')
    print(f"  {'axis':6s} {'rate band':>10s} {'rate@peak':>10s} {'peak Hz':>8s} {'out band':>9s} "
          f"{'out@peak':>9s} {'des band':>9s} {'PID P':>8s} {'PID D':>8s} {'D/P':>5s}   rate peaks")
    for name, *_ in AXES:
        a = res['axis'][name]
        pd = ''
        if 'pid_p' in a:
            ratio = a['pid_d'] / a['pid_p'] if a['pid_p'] > 0 else float('inf')
            pd = f"{a['pid_p']:8.4f} {a['pid_d']:8.4f} {ratio:5.1f}"
        else:
            pd = f"{'-':>8s} {'-':>8s} {'-':>5s}"
        print(f"  {name:6s} {a['band']:10.3f} {a['at_peak']:10.3f} {a['peak_f']:8.1f} {a['out_band']:9.4f} "
              f"{a['out_at_peak']:9.4f} {a['des_band']:9.3f} {pd}   {fmt_peaks(a['peaks'])}")

    print(f'\n=== coherence / phase at {fpk:.1f} Hz (phase of second relative to first) ===')
    labels = {('R', 'ROut'): 'roll rate -> roll out', ('P', 'POut'): 'pitch rate -> pitch out',
              ('Y', 'YOut'): 'yaw rate -> yaw out', ('R', 'P'): 'roll rate -> pitch rate',
              ('R', 'Y'): 'roll rate -> yaw rate', ('P', 'Y'): 'pitch rate -> yaw rate',
              ('ROut', 'POut'): 'roll out -> pitch out', ('R', 'RDes'): 'roll rate -> roll demand',
              ('P', 'PDes'): 'pitch rate -> pitch demand', ('Y', 'YDes'): 'yaw rate -> yaw demand'}
    for k, (c, ph) in res['coh'].items():
        print(f'  {labels[k]:28s} coh {c:.2f}  phase {ph:7.1f} deg')

    blo, bhi = res['trend_band']
    tr = res['trend']
    print(f'\n=== per-second RMS in {blo:.0f}-{bhi:.0f} Hz: roll, pitch, yaw rate (dps); roll, pitch out ===')
    for ws, r, p, y, ro, po in tr:
        print(f'  {ws:6.1f}s  R {r:6.3f}  P {p:6.3f}  Y {y:6.3f}  ROut {ro:7.4f}  POut {po:7.4f}')
    if tr:
        arr = np.array(tr)
        for i, nm in ((1, 'roll'), (2, 'pitch')):
            print(f'  {nm}: worst second {arr[:, i].max():.3f} dps, median {np.median(arr[:, i]):.3f} dps '
                  f'(ratio {arr[:, i].max() / max(np.median(arr[:, i]), 1e-9):.1f}: above ~2 is bursty)')

    # signature
    bands = {name: res['axis'][name]['at_peak'] for name, *_ in AXES}
    dom = max(bands, key=bands.get)
    others = sorted((v for k, v in bands.items() if k != dom), reverse=True)
    ratio = bands[dom] / max(others[0], 1e-9)
    dom_axis = [a for a in AXES if a[0] == dom][0]
    rc, rph = res['coh'][(dom_axis[1], dom_axis[2])]
    cross = max(res['coh'][('R', 'P')][0], res['coh'][('R', 'Y')][0], res['coh'][('P', 'Y')][0])
    a = res['axis'][dom]
    dp = f", D/P {a['pid_d'] / a['pid_p']:.1f}" if 'pid_p' in a and a['pid_p'] > 0 else ''
    print(f'\n=== signature at {fpk:.1f} Hz ===')
    print(f'  dominant axis {dom} ({bands[dom]:.3f} dps at the peak, {ratio:.1f}x the next axis); '
          f'rate -> out coh {rc:.2f} phase {rph:.0f} deg{dp}; best cross-axis coh {cross:.2f}')
    if cross >= 0.7:
        print('  reads as common-mode across axes: structural/vibration candidate. Confirm pre-filter on '
              'every IMU with batch_fft.py before notching; a loop mode does not appear on all axes.')
    elif ratio >= 1.5 and rc >= 0.8:
        print(f'  reads as a single-axis, controller-engaged band: loop-mode candidate on {dom}. Change that '
              'axis\'s D (and P with it) and re-measure: a loop mode moves in frequency, a structural line does not.')
    else:
        print('  mixed evidence: neither clearly single-axis nor clearly common-mode. Read the table, and check '
              'batch_fft.py pre-filter before deciding.')


def ab_report(a, b):
    print(f"\n=== A/B: A = {a['path'].split('/')[-1]} {a['t0']}-{a['t1']} s,"
          f" B = {b['path'].split('/')[-1]} {b['t0']}-{b['t1']} s ===")

    def delta(x, y):
        return f'{x:.3f} -> {y:.3f} ({(y / x - 1) * 100:+.0f}%)' if x > 0 else f'{x:.3f} -> {y:.3f}'

    def delta4(x, y):
        return f'{x:.4f} -> {y:.4f} ({(y / x - 1) * 100:+.0f}%)' if x > 0 else f'{x:.4f} -> {y:.4f}'

    print(f"  dominant peak {a['fpk']:.1f} -> {b['fpk']:.1f} Hz (rate@peak is +-1.5 Hz around each run's own peak)")
    for name, *_ in AXES:
        xa, xb = a['axis'][name], b['axis'][name]
        pd = ''
        if 'pid_p' in xa and 'pid_p' in xb and xa['pid_p'] > 0 and xb['pid_p'] > 0:
            pd = f"  D/P {xa['pid_d'] / xa['pid_p']:.1f} -> {xb['pid_d'] / xb['pid_p']:.1f}"
        print(f"  {name:6s} band {delta(xa['band'], xb['band'])}  peak {xa['peak_f']:.1f} -> {xb['peak_f']:.1f} Hz  "
              f"rate@peak {delta(xa['at_peak'], xb['at_peak'])}  out band {delta4(xa['out_band'], xb['out_band'])}{pd}")
    print('  sub-bands (A -> B):')
    for k in ('R', 'P', 'Y', 'ROut', 'POut', 'YOut'):
        fa, pa = a['spec'][k]
        fb, pb = b['spec'][k]
        fmt = '{:.3f}' if k in ('R', 'P', 'Y') else '{:.4f}'
        cells = []
        for lo_, hi_ in SUBBANDS:
            cells.append(f'{lo_:g}-{hi_:g}: ' + fmt.format(band_rms(fa, pa, lo_, hi_)) + '->'
                         + fmt.format(band_rms(fb, pb, lo_, hi_)))
        print(f'    {k:5s} ' + '  '.join(cells))


def plot(runs, out):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('matplotlib not available; skipping --png')
        return
    fig, ax = plt.subplots(2, 2, figsize=(12, 7), sharex=True)
    fmax = max(80.0, runs[0]['hi'] * 2.0)
    for r in runs:
        name = r['path'].split('/')[-1]
        lab = f"{name if len(name) <= 40 else '...' + name[-37:]} {r['t0']:g}-{r['t1']:g}s"
        for i, (k, title) in enumerate((('R', 'roll rate (dps)'), ('P', 'pitch rate (dps)'),
                                        ('ROut', 'roll output'), ('POut', 'pitch output'))):
            f, p = r['spec'][k]
            a = ax[i // 2][i % 2]
            a.semilogy(f, np.sqrt(p), lw=1, label=lab)
            a.set_title(title)
            a.set_xlim(0, fmax)
            a.grid(True, alpha=.3)
    for a in ax[1]:
        a.set_xlabel('Hz')
    ax[0][0].legend(fontsize=7, loc='upper right')
    ax[0][0].set_ylabel('ASD')
    ax[1][0].set_ylabel('ASD')
    fig.tight_layout()
    fig.savefig(out, dpi=110)
    print(f'wrote {out}')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--from-time', type=float, required=True)
    ap.add_argument('--to-time', type=float, required=True)
    ap.add_argument('--band', type=float, nargs=2, default=(15.0, 40.0), metavar=('LO', 'HI'))
    ap.add_argument('--vs', help='second log for an A/B')
    ap.add_argument('--vs-from', type=float)
    ap.add_argument('--vs-to', type=float)
    ap.add_argument('--png', help='overlay ASD plot of rate and output')
    ap.add_argument('--nperseg', type=int, default=2048)
    args = ap.parse_args()

    lo, hi = args.band
    runs = [analyse(args.log, args.from_time, args.to_time, lo, hi, args.nperseg)]
    print(f'=== A: {args.log} ===')
    report(runs[0])
    if args.vs:
        if args.vs_from is None or args.vs_to is None:
            sys.exit('--vs needs --vs-from and --vs-to')
        runs.append(analyse(args.vs, args.vs_from, args.vs_to, lo, hi, args.nperseg))
        print(f'\n=== B: {args.vs} ===')
        report(runs[1])
        ab_report(runs[0], runs[1])
    if args.png:
        plot(runs, args.png)


if __name__ == '__main__':
    main()
