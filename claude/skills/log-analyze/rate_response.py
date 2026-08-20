#!/usr/bin/env python3
"""Closed-loop rate response: how well each axis actually follows its rate demand, and how
much damping it has.

`stats` on RATE tells you the rate error is large. It cannot tell you WHY, because a large
error has three different causes with three different fixes: too little gain (the loop never
gets there), too little damping (it gets there and rings), or saturation (no authority left).
Those look identical in a standard deviation and completely different in the frequency domain.

So this transforms RATE.*Des -> RATE.* into a transfer function per axis and reads:

  * |H| ~ 0 dB across the control band  -> the loop is following. Good.
  * A peak above 0 dB                   -> UNDER-DAMPED. The damping ratio is printed; the
                                           fix is D (or less P), not more P.
  * |H| below 0 dB from the lowest       -> UNDER-GAINED. The loop never catches up; more P.
    frequency up, with no peak
  * Output RMS concentrated above 10 Hz  -> noise reaching the motors; filter, do not tune.

THE TRAP THAT MAKES THIS EASY TO MISREAD: above roughly 10 Hz the estimate is garbage, and
garbage with high coherence, which is what makes it convincing. RATE.*Des is produced by the
angle controller from the AHRS attitude, and that attitude is integrated from the same
filtered gyro that produces RATE.*. Demand and response therefore share a noise source, and
where both are noise the coherence goes high and |H| reports whatever ratio the two noise
floors happen to have. On 2026-08-04 that manufactured +15 to +29 dB "resonances" at 34-37 Hz
on all three axes of a quad with no structural mode anywhere near there. The peak search is
deliberately capped at --peak-fmax (default 10 Hz) for this reason. If you want to believe a
peak above that, corroborate it in gyro_fft.py's post-filter spectrum, where there is no
shared-source problem -- a real mode carries real energy there.

Damping ratio comes from the resonant peak height, Mp = 1 / (2 zeta sqrt(1 - zeta^2)):
zeta ~0.2 is ringy, ~0.5 is a good target, and above ~0.7 is sluggish.

Usage:
    rate_response.py <log.bin> --from-time S --to-time S [--peak-fmax 10] [--npz out.npz]
"""
import argparse
import sys

import numpy as np

try:
    from scipy import signal
except ImportError:
    sys.exit('rate_response.py needs scipy (pip install scipy)')

from pymavlink import mavutil

# RATE field triples per axis: demanded, actual, controller output
AXES = (('roll', 'RDes', 'R', 'ROut'),
        ('pitch', 'PDes', 'P', 'POut'),
        ('yaw', 'YDes', 'Y', 'YOut'))

REPORT_HZ = (0.5, 1, 1.5, 2, 3, 4, 5, 7, 10, 15, 20)


def time_base(path):
    """Match log_extract.py's normalisation so time windows mean the same in both tools.

    log_extract.get_time_base() takes the very first message of any type (the first FMT),
    whose timestamp is the log's clock origin, so its time_s is effectively TimeUS/1e6.
    Skipping the metadata messages here put the origin at the first data message instead
    (~25-30 s later on an arm-triggered log) and silently shifted every window."""
    mlog = mavutil.mavlink_connection(path)
    m = mlog.recv_msg()
    return m._timestamp if m is not None else 0.0


def collect(path, t0, t1):
    base = time_base(path)
    mlog = mavutil.mavlink_connection(path)
    fields = [f for a in AXES for f in a[1:]]
    cols = {f: [] for f in fields}
    ts = []
    while True:
        m = mlog.recv_match(type=['RATE'])
        if m is None:
            break
        t = m._timestamp - base
        if t < t0:
            continue
        if t > t1:
            break
        ts.append(t)
        for f in fields:
            cols[f].append(getattr(m, f))
    return np.asarray(ts), {k: np.asarray(v) for k, v in cols.items()}


def damping_from_peak(gain_db):
    """Invert Mp = 1 / (2 zeta sqrt(1 - zeta^2)) for the lightly-damped root."""
    mp = 10 ** (gain_db / 20.0)
    if mp <= 1.0:
        return None
    return float(np.sqrt((1 - np.sqrt(max(0.0, 1 - 1 / mp ** 2))) / 2))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--from-time', type=float, required=True)
    ap.add_argument('--to-time', type=float, required=True)
    ap.add_argument('--peak-fmax', type=float, default=10.0,
                    help='upper limit of the trustworthy band (default 10 Hz)')
    ap.add_argument('--min-coh', type=float, default=0.5)
    ap.add_argument('--nperseg', type=int, default=2048)
    ap.add_argument('--npz')
    args = ap.parse_args()

    ts, c = collect(args.log, args.from_time, args.to_time)
    if len(ts) < args.nperseg * 2:
        sys.exit(f'only {len(ts)} RATE samples in that window; need at least '
                 f'{args.nperseg * 2}. Widen the window or check the vehicle was armed.')
    fs = (len(ts) - 1) / (ts[-1] - ts[0])
    print(f'{len(ts)} RATE samples at {fs:.1f} Hz over '
          f'{args.from_time:.0f}-{args.to_time:.0f} s')
    print(f'conclusions restricted to <= {args.peak_fmax:.0f} Hz with coherence >= '
          f'{args.min_coh:.2f} (see the docstring: demand and response share a gyro)')

    npr, ovl = args.nperseg, args.nperseg // 2
    saved = {}
    for name, fd, fa, fo in AXES:
        des = c[fd] - c[fd].mean()
        act = c[fa] - c[fa].mean()
        out = c[fo] - c[fo].mean()

        f, Pdd = signal.welch(des, fs, nperseg=npr, noverlap=ovl)
        _, Paa = signal.welch(act, fs, nperseg=npr, noverlap=ovl)
        _, Poo = signal.welch(out, fs, nperseg=npr, noverlap=ovl)
        _, Pda = signal.csd(des, act, fs, nperseg=npr, noverlap=ovl)
        _, coh = signal.coherence(des, act, fs, nperseg=npr, noverlap=ovl)

        H = Pda / np.maximum(Pdd, 1e-30)
        gain = 20 * np.log10(np.abs(H) + 1e-12)
        phase = np.degrees(np.angle(H))

        print(f'\n=== {name} ===')
        print(f'  {"f Hz":>6} {"|H| dB":>8} {"phase":>8} {"coh":>6} '
              f'{"des ASD":>9} {"act ASD":>9} {"out ASD":>9}')
        for target in REPORT_HZ:
            i = int(np.argmin(np.abs(f - target)))
            flag = '' if coh[i] >= args.min_coh and f[i] <= args.peak_fmax else '  (noisy)'
            print(f'  {f[i]:6.2f} {gain[i]:8.2f} {phase[i]:8.1f} {coh[i]:6.2f} '
                  f'{np.sqrt(Pdd[i]):9.4f} {np.sqrt(Paa[i]):9.4f} '
                  f'{np.sqrt(Poo[i]):9.5f}{flag}')

        band = (f > 0.3) & (f <= args.peak_fmax) & (coh >= args.min_coh)
        if band.any():
            k = int(np.argmax(gain[band]))
            pk_db, pk_hz, pk_coh = gain[band][k], f[band][k], coh[band][k]
            zeta = damping_from_peak(pk_db)
            if zeta is not None:
                verdict = (f'UNDER-DAMPED, damping ratio ~{zeta:.2f} '
                           f'(~0.5 is the target; add D or reduce P)')
            elif gain[band].max() < -3.0:
                verdict = ('UNDER-GAINED: never reaches 0 dB and has no peak, so the loop '
                           'is not keeping up rather than ringing (raise P)')
            else:
                verdict = 'flat, no resonant peak -- this axis is behaving'
            print(f'  peak |H| in the trustworthy band: {pk_db:+.2f} dB at {pk_hz:.2f} Hz '
                  f'(coh {pk_coh:.2f})')
            print(f'  -> {verdict}')
        else:
            print('  no frequency in the trustworthy band reached the coherence floor; '
                  'the axis was probably not excited enough in this window')

        def rms(P, lo, hi):
            m = (f >= lo) & (f < hi)
            return float(np.sqrt(np.sum(P[m]) * (f[1] - f[0])))

        print(f'  actual rate RMS  0.2-3Hz {rms(Paa, .2, 3):7.3f}  3-10Hz '
              f'{rms(Paa, 3, 10):7.3f}  10-40Hz {rms(Paa, 10, 40):7.3f}  '
              f'40Hz+ {rms(Paa, 40, fs / 2):7.3f}  (dps)')
        print(f'  output RMS       0.2-3Hz {rms(Poo, .2, 3):7.4f}  3-10Hz '
              f'{rms(Poo, 3, 10):7.4f}  10-40Hz {rms(Poo, 10, 40):7.4f}  '
              f'40Hz+ {rms(Poo, 40, fs / 2):7.4f}  (of full authority)')
        print(f'  rate error RMS {np.std(act - des):.3f} dps against demand RMS '
              f'{np.std(des):.3f} dps')

        for key, val in (('f', f), ('gain', gain), ('phase', phase), ('coh', coh),
                         ('des', np.sqrt(Pdd)), ('act', np.sqrt(Paa)),
                         ('out', np.sqrt(Poo))):
            saved[f'{name}_{key}'] = val

    if args.npz:
        np.savez(args.npz, **saved)
        print(f'\nsaved -> {args.npz}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
