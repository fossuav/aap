#!/usr/bin/env python3
"""What the gyro filter chain ACTUALLY removed, measured pre- against post-filter.

`INS_RAW_LOG_OPT` bit 3 (PRE_AND_POST_FILTER, value 8) makes the backend log every raw gyro
sample at instance I and the filtered sample at instance I + gyro_count
(AP_InertialSensor_Backend.cpp, log_gyro_raw). Two spectra from the same samples, so the
difference between them is the filter chain and nothing else -- no modelling, no assumptions
about what the notch was tracking.

This is the measurement that tells you whether a noise problem is real. VIBE gives magnitude;
this gives frequency, and more importantly it gives ATTENUATION PER BAND, which is what
decides whether the answer is "filter harder" or "stop filtering".

Traps this exists to avoid:

  * The 0-10 Hz band is the vehicle actually moving. It SHOULD pass through unattenuated.
    Reading a low attenuation there as a filter failure is the standard misread; judge the
    filters on the motor bands only.
  * A harmonic notch that skips the fundamental leaves the fundamental as the WORST-filtered
    band while the harmonics look superb. On 2026-08-04 a spray quad showed -51 to -64 dB on
    the 2nd and 4th harmonics and only -20 dB on the fundamental, because INS_HNTCH_HMNCS was
    10 (0b1010 = 2nd and 4th only) and the notch meant to cover the fundamental was pinned
    static by INS_HNTC2_REF=0. Per-band attenuation is what made that visible.
  * A static notch covers the fundamental only at the throttle where it happens to sit. Fly a
    window at hover and a window under load and compare -- if the attenuation falls off in the
    loaded window, the notch is not tracking, whatever INS_HNTCH_MODE claims.
  * The peak table reports PRE-filter peaks with their post-filter value. Sorting on
    post-filter magnitude finds only what the filters already killed.

Needs INS_RAW_LOG_OPT bit 3 set (e.g. 9 = primary gyro, pre and post). Without it there is no
post-filter spectrum to compare against and the script says so rather than guessing.

Usage:
    gyro_fft.py <log.bin> --from-time S --to-time S [--axis roll|pitch|yaw|all] [--fmax 400]
"""
import argparse
import sys

import numpy as np

try:
    from scipy import signal
except ImportError:
    sys.exit('gyro_fft.py needs scipy (pip install scipy)')

from pymavlink import mavutil

AXES = (('GyrX', 'roll'), ('GyrY', 'pitch'), ('GyrZ', 'yaw'))

# Bands chosen so the motor fundamental and its low harmonics land in their own rows.
# The first two are the control band and are expected to pass through.
BANDS = ((0, 10), (10, 25), (25, 35), (35, 50), (50, 70), (70, 95),
         (95, 140), (140, 200), (200, 400))

PARAMS_OF_INTEREST = (
    'INS_RAW_LOG_OPT', 'INS_GYRO_FILTER', 'INS_GYRO_RATE', 'SCHED_LOOP_RATE',
    'INS_HNTCH_ENABLE', 'INS_HNTCH_MODE', 'INS_HNTCH_FREQ', 'INS_HNTCH_BW',
    'INS_HNTCH_HMNCS', 'INS_HNTCH_OPTS', 'INS_HNTCH_REF', 'INS_HNTCH_ATT',
    'INS_HNTC2_ENABLE', 'INS_HNTC2_MODE', 'INS_HNTC2_FREQ', 'INS_HNTC2_BW',
    'INS_HNTC2_HMNCS', 'INS_HNTC2_OPTS', 'INS_HNTC2_REF', 'INS_HNTC2_ATT',
)


def time_base(path):
    """log_extract.get_time_base() takes the very first message of any type (the first FMT),
    whose timestamp is the log's clock origin; match it exactly so --from-time/--to-time mean
    the same thing in both tools. Skipping metadata here put the origin at the first data
    message (~25-30 s later on an arm-triggered log) and silently shifted every window."""
    mlog = mavutil.mavlink_connection(path)
    m = mlog.recv_msg()
    return m._timestamp if m is not None else 0.0


def collect(path, t0, t1):
    base = time_base(path)
    mlog = mavutil.mavlink_connection(path)
    gyr, rpm, thr, parms = {}, {}, [], {}
    while True:
        m = mlog.recv_match(type=['GYR', 'ESC', 'CTUN', 'PARM'])
        if m is None:
            break
        if m.get_type() == 'PARM':
            if m.Name in PARAMS_OF_INTEREST:
                parms[m.Name] = m.Value
            continue
        t = m._timestamp - base
        if t < t0:
            continue
        if t > t1:
            break
        if m.get_type() == 'GYR':
            d = gyr.setdefault(m.I, {'t': [], 'GyrX': [], 'GyrY': [], 'GyrZ': []})
            d['t'].append(m.SampleUS / 1e6)
            for f, _ in AXES:
                d[f].append(getattr(m, f))
        elif m.get_type() == 'ESC':
            rpm.setdefault(m.Instance, []).append(m.RPM)
        elif m.get_type() == 'CTUN':
            thr.append(m.ThO)
    return gyr, rpm, thr, parms


def asd(d, field):
    """Amplitude spectral density in deg/s per root-Hz."""
    t = np.asarray(d['t'])
    v = np.degrees(np.asarray(d[field]))
    if len(t) < 4096 or t[-1] <= t[0]:
        return None, None, None
    fs = (len(t) - 1) / (t[-1] - t[0])
    f, p = signal.welch(v - v.mean(), fs=fs, nperseg=4096, noverlap=3072, window='hann')
    return f, np.sqrt(p), fs


def band_rms(f, a, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(np.sqrt(np.sum(a[m] ** 2) * (f[1] - f[0]))) if m.any() else 0.0


def notch_span(freq, bw):
    """The -3 dB span of an ArduPilot notch at its configured centre. Q is computed once from
    FREQ/BW (NotchFilter::calculate_A_and_Q) and reused at every tracked frequency, so the
    absolute span scales with the centre: span(f) = f / Q."""
    if freq <= 0.5 * bw:
        return None
    octaves = np.log2(freq / (freq - bw / 2.0)) * 2.0
    q = np.sqrt(2 ** octaves) / (2 ** octaves - 1.0)
    return q, freq / q


def describe_notches(p, fund):
    if not p:
        return
    print('\n=== configured filters ===')
    gf = p.get('INS_GYRO_FILTER')
    if gf is not None:
        print(f'  INS_GYRO_FILTER {gf:.0f} Hz (2-pole)')
    for pre in ('INS_HNTCH', 'INS_HNTC2'):
        if not p.get(f'{pre}_ENABLE'):
            continue
        mode = int(p.get(f'{pre}_MODE', 0))
        freq = p.get(f'{pre}_FREQ', 0.0)
        bw = p.get(f'{pre}_BW', 0.0)
        hm = int(p.get(f'{pre}_HMNCS', 0))
        ref = p.get(f'{pre}_REF', None)
        harmonics = [n + 1 for n in range(8) if hm & (1 << n)]
        modes = {0: 'fixed', 1: 'throttle', 2: 'RPM1', 3: 'ESC telem',
                 4: 'FFT', 5: 'RPM2'}
        nq = notch_span(freq, bw)
        span = f', -3 dB span {nq[1]:.1f} Hz at {freq:.0f} Hz (Q {nq[0]:.2f})' if nq else ''
        print(f'  {pre}: mode {mode} ({modes.get(mode, "?")}), FREQ {freq:.0f}, '
              f'BW {bw:.0f}, harmonics {harmonics}{span}')
        # AP_Vehicle::update_dynamic_notch returns early on a zero reference, so a
        # tracking mode with REF=0 is silently a fixed notch at FREQ.
        if ref is not None and abs(ref) < 1e-6 and mode != 0:
            print(f'    !! {pre}_REF is 0, so this notch does NOT track. '
                  f'AP_Vehicle.cpp update_dynamic_notch() returns early on a zero '
                  f'reference: it is a FIXED notch at {freq:.0f} Hz.')
        if fund and 1 not in harmonics:
            print(f'    !! harmonics {harmonics} skip the fundamental '
                  f'({fund:.1f} Hz measured)')
        is_fixed = mode == 0 or (ref is not None and abs(ref) < 1e-6)
        if fund and nq and is_fixed and 1 in harmonics:
            lo, hi = freq - nq[1] / 2, freq + nq[1] / 2
            if not lo <= fund <= hi:
                print(f'    !! fundamental {fund:.1f} Hz is outside this fixed notch '
                      f'({lo:.1f}-{hi:.1f} Hz)')


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--from-time', type=float, required=True)
    ap.add_argument('--to-time', type=float, required=True)
    ap.add_argument('--axis', default='all', choices=['roll', 'pitch', 'yaw', 'all'])
    ap.add_argument('--fmax', type=float, default=400.0)
    ap.add_argument('--npeaks', type=int, default=8)
    ap.add_argument('--npz', help='save spectra here for plotting')
    args = ap.parse_args()

    gyr, rpm, thr, parms = collect(args.log, args.from_time, args.to_time)
    if not gyr:
        sys.exit('no GYR messages in that window -- raw gyro logging is off. '
                 'Set INS_RAW_LOG_OPT=9 (primary gyro, pre and post filter) and the '
                 'matching LOG_BITMASK bit, then re-fly.')

    insts = sorted(gyr)
    # Pre-filter instances are logged at I, post-filter at I + gyro_count. The count is not
    # in the log, so infer it from the gap: with one primary gyro logged we see {0, N}.
    half = len(insts) // 2
    if len(insts) >= 2 and half and insts[half] - insts[0] >= 1:
        pre_i, post_i = insts[0], insts[half]
    else:
        pre_i, post_i = insts[0], None

    fund = None
    if rpm:
        means = [float(np.mean(v)) for v in rpm.values()]
        fund = float(np.mean(means)) / 60.0
        print('=== ESC RPM in window ===')
        for inst in sorted(rpm):
            a = np.array(rpm[inst])
            print(f'  ESC{inst}: mean {a.mean():8.1f} rpm ({a.mean()/60:6.2f} Hz)  '
                  f'p5 {np.percentile(a, 5):7.1f}  p95 {np.percentile(a, 95):7.1f}')
        print(f'  mean fundamental {fund:.2f} Hz   harmonics ' +
              ' '.join(f'{fund * n:.0f}' for n in range(2, 7)))
    if thr:
        print(f'  CTUN.ThO mean {np.mean(thr):.3f}')

    describe_notches(parms, fund)

    if post_i is None:
        print('\n!! only one set of GYR instances is present, so this log has either '
              'pre- OR post-filter data, not both. Per-band attenuation needs '
              'INS_RAW_LOG_OPT bit 3 (value 8). Spectra below are that single set.')

    saved = {}
    for field, label in AXES:
        if args.axis not in ('all', label):
            continue
        fp, ap_pre, fs = asd(gyr[pre_i], field)
        if fp is None:
            print(f'\n{label}: too few samples in window')
            continue
        if post_i is not None:
            fq, ap_post, _ = asd(gyr[post_i], field)
        else:
            fq = ap_post = None

        print(f'\n=== {label} ({field})  {fs:.0f} Hz, GYR instance {pre_i}'
              + (f' vs {post_i}' if post_i is not None else '') + ' ===')
        if ap_post is not None:
            print(f'  {"band":>14} {"pre dps":>9} {"post dps":>9} {"atten":>9}')
            for lo, hi in BANDS:
                rp = band_rms(fp, ap_pre, lo, hi)
                rq = band_rms(fq, ap_post, lo, hi)
                att = 20 * np.log10(rq / rp) if rp > 0 and rq > 0 else float('nan')
                note = '  <- vehicle motion, should pass' if hi <= 10 else ''
                print(f'  {lo:5.0f}-{hi:5.0f} Hz {rp:9.3f} {rq:9.3f} {att:8.1f}dB{note}')
            rp = band_rms(fp, ap_pre, 5, args.fmax)
            rq = band_rms(fq, ap_post, 5, args.fmax)
            att = 20 * np.log10(rq / rp) if rp > 0 and rq > 0 else float('nan')
            print(f'  {5:5.0f}-{args.fmax:5.0f} Hz {rp:9.3f} {rq:9.3f} {att:8.1f}dB'
                  f'  <- TOTAL above the control band')

        sel = (fp >= 5) & (fp <= args.fmax)
        idx = signal.find_peaks(ap_pre[sel], distance=6)[0]
        top = idx[np.argsort(ap_pre[sel][idx])[::-1]][:args.npeaks]
        print('  strongest pre-filter peaks:')
        for i in sorted(top, key=lambda j: fp[sel][j]):
            fhz, pv = fp[sel][i], ap_pre[sel][i]
            if ap_post is not None:
                qv = float(np.interp(fhz, fq, ap_post))
                a = f'{20 * np.log10(qv / pv):7.1f}dB' if pv > 0 else '      -'
                post_s = f' {qv:8.4f} {a}'
            else:
                post_s = ''
            hint = ''
            if fund:
                n = fhz / fund
                if abs(n - round(n)) < 0.12 and round(n) >= 1:
                    hint = f'   <- {round(n)}x motor'
            print(f'    {fhz:7.1f} Hz {pv:8.4f}{post_s}{hint}')

        saved[f'{label}_f'] = fp
        saved[f'{label}_pre'] = ap_pre
        if ap_post is not None:
            saved[f'{label}_post'] = np.interp(fp, fq, ap_post)

    if args.npz and saved:
        saved['fundamental'] = np.array([fund or 0.0])
        np.savez(args.npz, **saved)
        print(f'\nsaved spectra -> {args.npz}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
