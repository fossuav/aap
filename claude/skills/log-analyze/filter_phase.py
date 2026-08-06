#!/usr/bin/env python3
"""What the configured filter chain costs in phase, and what a proposed change would buy.

Filtering is not free: every notch and every low-pass spends phase margin in the control
band, and phase margin is what damping is made of. Tuners reach for lower cutoffs to quiet an
axis and then cannot work out why it will not damp. This prices that trade before you fly it.

The chain is rebuilt from the log's own parameters using ArduPilot's exact coefficient
formulas -- DigitalBiquadFilter::compute_params for the 2-pole gyro low-pass,
NotchFilter::calculate_A_and_Q plus init_with_A_and_Q for each notch, and the
LowPassFilterFloat EMA for the rate-loop FLTD/FLTT/FLTE. Nothing is hand-transcribed, so the
answer is for the aircraft that flew rather than for the parameters someone believed.

Two properties of the harmonic notch drive most surprises here, and both are modelled:

  * The notch is CONSTANT-Q, not constant-Hz. Q is computed once from INS_HNTCH_FREQ/_BW and
    reused at every tracked frequency (set_center_frequency -> init_with_A_and_Q), so the
    absolute -3 dB span scales with the centre: span(f) = f / Q. BW=10 at a 40 Hz base is
    ~55 Hz wide once it tracks up to 220 Hz. Do not read a small BW as "too narrow" without
    scaling it first.
  * A tracking mode with a zero reference does not track. AP_Vehicle::update_dynamic_notch
    returns early when INS_HNTCH_REF (or _HNTC2_REF) is zero, leaving a FIXED notch at FREQ
    whatever the mode says. Pass --at-freq for where the fundamental really is and the gain
    column will show whether the notch is even near it.

Validate before trusting: run gyro_fft.py on the same window and compare its measured
per-band attenuation to the gain column here. On 2026-08-04 the model gave -24.8 dB at
41.6 Hz against -25.8 dB measured, which is what earned the phase numbers their credibility.

Usage:
    filter_phase.py <log.bin> [--at-freq 41.6] [--set INS_GYRO_FILTER=40 --set ...]
                              [--from-time S --to-time S]

--set applies overrides on top of the log's values and prints both chains side by side, so
"what does moving INS_GYRO_FILTER to 40 and disabling INS_HNTC2 buy me at 4 Hz?" is one run.
"""
import argparse
import sys

import numpy as np
from pymavlink import mavutil

GRID = np.array([1., 2., 3., 4., 5., 7., 10., 15., 20., 30., 50., 80.])

PARAMS = ('INS_GYRO_FILTER', 'INS_GYRO_RATE', 'SCHED_LOOP_RATE',
          'ATC_RAT_RLL_FLTD', 'ATC_RAT_RLL_FLTT', 'ATC_RAT_RLL_FLTE',
          'ATC_RAT_PIT_FLTD', 'ATC_RAT_PIT_FLTT', 'ATC_RAT_PIT_FLTE',
          'ATC_RAT_YAW_FLTD', 'ATC_RAT_YAW_FLTT', 'ATC_RAT_YAW_FLTE')
for _p in ('INS_HNTCH', 'INS_HNTC2', 'INS_HNTC3', 'INS_HNTC4'):
    PARAMS += tuple(f'{_p}_{s}' for s in
                    ('ENABLE', 'MODE', 'FREQ', 'BW', 'HMNCS', 'OPTS', 'REF', 'ATT'))

GYRO_RATE_HZ = {0: 1000.0, 1: 2000.0, 2: 4000.0, 3: 8000.0}


# --- ArduPilot filter forms -------------------------------------------------

def lpf2p(fs, fc):
    """DigitalBiquadFilter<T>::compute_params (LowPassFilter2p.cpp)."""
    ohm = np.tan(np.pi * fc / fs)
    c = 1.0 + 2.0 * np.cos(np.pi / 4.0) * ohm + ohm * ohm
    b0 = ohm * ohm / c
    return (np.array([b0, 2 * b0, b0]),
            np.array([1.0, 2.0 * (ohm * ohm - 1.0) / c,
                      (1.0 - 2.0 * np.cos(np.pi / 4.0) * ohm + ohm * ohm) / c]))


def notch_A_Q(freq, bw, att_db):
    """NotchFilter<T>::calculate_A_and_Q."""
    A = 10 ** (-att_db / 40.0)
    if freq <= 0.5 * bw:
        return A, 0.0
    octaves = np.log2(freq / (freq - bw / 2.0)) * 2.0
    return A, np.sqrt(2 ** octaves) / (2 ** octaves - 1.0)


def notch(fs, fc, A, Q):
    """NotchFilter<T>::init_with_A_and_Q."""
    omega = 2.0 * np.pi * fc / fs
    alpha = np.sin(omega) / (2 * Q)
    inv = 1.0 / (1.0 + alpha)
    return (np.array([1.0 + alpha * A * A, -2.0 * np.cos(omega),
                      1.0 - alpha * A * A]) * inv,
            np.array([1.0, -2.0 * np.cos(omega) * inv, (1.0 - alpha) * inv]))


def lpf1p(fs, fc):
    """LowPassFilterFloat: alpha = dt / (dt + 1/(2 pi fc))."""
    dt = 1.0 / fs
    alpha = dt / (dt + 1.0 / (2 * np.pi * fc))
    return np.array([alpha, 0.0, 0.0]), np.array([1.0, -(1.0 - alpha), 0.0])


def response(stages, f):
    h = np.ones_like(f, dtype=complex)
    for b, a, fs in stages:
        z = np.exp(-2j * np.pi * f / fs)
        h *= (sum(b[i] * z ** i for i in range(len(b))) /
              sum(a[i] * z ** i for i in range(len(a))))
    return h


# --- chain assembly ---------------------------------------------------------

def gyro_chain(p, fs_gyro, fund, motors):
    stages, notes = [], []
    for pre in ('INS_HNTCH', 'INS_HNTC2', 'INS_HNTC3', 'INS_HNTC4'):
        if not p.get(f'{pre}_ENABLE'):
            continue
        freq = p.get(f'{pre}_FREQ', 0.0)
        bw = p.get(f'{pre}_BW', 0.0)
        att = p.get(f'{pre}_ATT', 40.0)
        mode = int(p.get(f'{pre}_MODE', 0))
        ref = p.get(f'{pre}_REF', 1.0)
        harmonics = [n + 1 for n in range(8) if int(p.get(f'{pre}_HMNCS', 0)) & (1 << n)]
        dynamic_harmonic = bool(int(p.get(f'{pre}_OPTS', 0)) & 2)
        A, Q = notch_A_Q(freq, bw, att)
        if Q <= 0:
            notes.append(f'{pre}: BW >= 2x FREQ, notch never initialises')
            continue
        # A zero reference short-circuits update_dynamic_notch, so the notch is fixed at FREQ.
        tracking = mode != 0 and abs(ref) > 1e-6
        if tracking and fund:
            centres = ([fund * (1 + 0.02 * (m - (motors - 1) / 2)) for m in range(motors)]
                       if dynamic_harmonic else [fund])
        else:
            centres = [freq]
            if mode != 0:
                notes.append(f'{pre}: REF=0 so it does not track -- fixed at {freq:.0f} Hz')
        for cf in centres:
            for hn in harmonics:
                fc = cf * hn
                if 0 < fc < 0.4 * fs_gyro:
                    stages.append((*notch(fs_gyro, fc, A, Q), fs_gyro))
    gf = p.get('INS_GYRO_FILTER', 0.0)
    if gf and gf > 0:
        stages.append((*lpf2p(fs_gyro, gf), fs_gyro))
    return stages, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--at-freq', type=float,
                    help='motor fundamental Hz; default is measured from ESC/RPM')
    ap.add_argument('--from-time', type=float, default=0.0)
    ap.add_argument('--to-time', type=float, default=float('inf'))
    ap.add_argument('--motors', type=int, default=4)
    ap.add_argument('--axis', default='RLL', choices=['RLL', 'PIT', 'YAW'])
    ap.add_argument('--set', action='append', default=[], metavar='NAME=VALUE',
                    help='override a parameter; repeatable, prints a comparison')
    args = ap.parse_args()

    mlog = mavutil.mavlink_connection(args.log)
    p, rpm, base = {}, [], None
    while True:
        m = mlog.recv_match(type=['PARM', 'ESC', 'RPM'])
        if m is None:
            break
        if m.get_type() == 'PARM':
            if m.Name in PARAMS:
                p[m.Name] = m.Value
            continue
        if base is None:
            base = m._timestamp
        t = m._timestamp - base
        if t < args.from_time:
            continue
        if t > args.to_time:
            break
        if m.get_type() == 'ESC':
            rpm.append(m.RPM)

    if not p:
        sys.exit('no filter parameters found in the log')

    fund = args.at_freq
    if fund is None and rpm:
        fund = float(np.mean(rpm)) / 60.0
    if fund:
        print(f'motor fundamental {fund:.2f} Hz'
              + ('' if args.at_freq else f' (measured from {len(rpm)} ESC samples)'))
    else:
        print('no fundamental available; tracking notches modelled at their FREQ')

    fs_gyro = GYRO_RATE_HZ.get(int(p.get('INS_GYRO_RATE', 0)), 1000.0)
    fs_loop = p.get('SCHED_LOOP_RATE', 400.0)
    print(f'gyro rate {fs_gyro:.0f} Hz, loop rate {fs_loop:.0f} Hz')

    variants = [('as flown', dict(p))]
    if args.set:
        mod = dict(p)
        for kv in args.set:
            if '=' not in kv:
                sys.exit(f'--set expects NAME=VALUE, got {kv!r}')
            k, v = kv.split('=', 1)
            mod[k.strip()] = float(v)
        variants.append(('proposed', mod))

    fltd_name = f'ATC_RAT_{args.axis}_FLTD'
    results = {}
    for label, pp in variants:
        stages, notes = gyro_chain(pp, fs_gyro, fund, args.motors)
        h_gyro = response(stages, GRID)
        fltd = pp.get(fltd_name, 0.0)
        h_d = (response([(*lpf1p(fs_loop, fltd), fs_loop)], GRID)
               if fltd > 0 else np.ones_like(GRID, dtype=complex))
        results[label] = (h_gyro, h_d, notes, len(stages), fltd)

    for label, (_, _, notes, nst, fltd) in results.items():
        print(f'\n[{label}] {nst} notch/LPF stages on the gyro, '
              f'{fltd_name}={fltd:.0f} Hz')
        for n in notes:
            print(f'  !! {n}')

    print('\n=== gyro (feedback) path ===')
    hdr = f'  {"f Hz":>6}'
    for label in results:
        hdr += f' | {label + " dB":>13} {"phase":>8}'
    print(hdr)
    for i, fr in enumerate(GRID):
        row = f'  {fr:6.1f}'
        for label in results:
            h = results[label][0]
            row += f' | {20 * np.log10(abs(h[i])):13.2f} {np.degrees(np.angle(h[i])):7.1f}'
        print(row)

    print(f'\n=== D-term path ({fltd_name}, adds to the above) ===')
    print(hdr)
    for i, fr in enumerate(GRID):
        if fr > 20:
            break
        row = f'  {fr:6.1f}'
        for label in results:
            h = results[label][1]
            row += f' | {20 * np.log10(abs(h[i])):13.2f} {np.degrees(np.angle(h[i])):7.1f}'
        print(row)

    if len(results) == 2:
        a, b = (results[k] for k in results)
        print('\n=== what the change buys (positive = phase recovered) ===')
        print(f'  {"f Hz":>6} {"gyro path":>12} {"D path":>10} {"combined":>10}')
        for i, fr in enumerate(GRID):
            if fr > 20:
                break
            dg = np.degrees(np.angle(b[0][i])) - np.degrees(np.angle(a[0][i]))
            dd = np.degrees(np.angle(b[1][i])) - np.degrees(np.angle(a[1][i]))
            print(f'  {fr:6.1f} {dg:11.1f}d {dd:9.1f}d {dg + dd:9.1f}d')
    return 0


if __name__ == '__main__':
    sys.exit(main())
