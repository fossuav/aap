#!/usr/bin/env python3
"""Gyro or accel spectrum from the ISBH/ISBD batch sampler, per IMU, pre- and post-filter.

gyro_fft.py is the better tool when INS_RAW_LOG_OPT bit 3 is set (GYR then carries every raw
and filtered sample). Most logs do not have that; they have INS_LOG_BAT_MASK batch blocks,
and this reads those. It assembles each block, averages a Hann-windowed PSD per instance,
and prints per-band RMS and the top peaks per axis in physical units: ISBH.mul is the int16
scale factor the sampler applied (INT16_MAX/radians(2000) = 938 for gyro; for accel
INT16_MAX/(16 g) = 209 unless the backend set its own for a wider range, e.g. 104 on a 32 g
part), so sample/mul is rad/s or m/s^2. It is not a MULT-table index.

Instance numbering (BatchSampler::Write_ISBH): pre-filter blocks are instance 0..N-1; when
INS_LOG_BAT_OPT has pre+post (4), or post (2) together with sensor-rate (1), post-filter
blocks of the same IMUs are written as instance N..2N-1. With post (2) alone every block is
post-filter and numbered 0..N-1. When both pre and post are present for an IMU it also
prints per-band attenuation. The blocks are not simultaneous (the sampler rotates through
instances), so that attenuation is statistical: compare over a steady window, not across a
manoeuvre.

What it is for:
  * the motor fundamental and harmonics at the sensor rate (the 400 Hz IMU message cannot
    see them) and whether the notch covers them on EVERY IMU the loop might use --
    INS_HNTCH_OPTS without EnableOnAllIMUs (8) notches the primary only, and the other IMUs'
    post-filter spectra still carry the motor line
  * confirming a band found in RATE by rate_band.py is physical: present pre-filter, on more
    than one IMU, and not an artefact of the filtered path

Traps:
  * At the default INS_LOG_BAT_CNT/LGIN a 20 s window holds only 2-4 blocks per instance:
    resolution is one block (~2 Hz at 4 kHz/2048) and a narrow band's amplitude varies block
    to block. Widen the window, or lower INS_LOG_BAT_LGIN, before quoting small differences.
  * If only instances 0..N-1 appear with no post bit set, you have pre-filter only: there is
    no residual to measure. Re-fly with INS_LOG_BAT_OPT=4.
  * Time is the same clock as log_extract.py (first message of the log is zero); blocks are
    selected by their ISBH time, and a block straddling --to-time is kept.

Usage:
    batch_fft.py <log.bin> --from-time S --to-time S [--type gyro|accel] [--fmax 1000]
                 [--band 15 40] [--npeaks 6]
"""
import argparse
import sys

import numpy as np

try:
    from scipy import signal
except ImportError:
    sys.exit('batch_fft.py needs scipy (pip install scipy)')

from pymavlink import mavutil

_trapz = getattr(np, 'trapezoid', None) or np.trapz

BANDS = ((0, 10), (10, 20), (20, 30), (30, 45), (45, 80), (80, 150), (150, 250), (250, 400), (400, 1000))
SENSOR_TYPE = {'accel': 0, 'gyro': 1}
ID_PARAMS = {'gyro': ('INS_GYR_ID', 'INS_GYR2_ID', 'INS_GYR3_ID', 'INS4_GYR_ID', 'INS5_GYR_ID'),
             'accel': ('INS_ACC_ID', 'INS_ACC2_ID', 'INS_ACC3_ID', 'INS4_ACC_ID', 'INS5_ACC_ID')}


def time_base(path):
    """log_extract.get_time_base() takes the very first message of any type (the first FMT);
    match it so --from-time/--to-time mean the same thing in every tool."""
    mlog = mavutil.mavlink_connection(path)
    m = mlog.recv_msg()
    return m._timestamp if m is not None else 0.0


def collect(path, t0, t1, want):
    base = time_base(path)
    mlog = mavutil.mavlink_connection(path)
    parms, blocks, rpm, types_seen = {}, {}, [], set()
    cur = None
    while True:
        m = mlog.recv_match(type=['ISBH', 'ISBD', 'PARM', 'ESC'])
        if m is None:
            break
        ty = m.get_type()
        if ty == 'PARM':
            parms[m.Name] = m.Value
            continue
        t = m._timestamp - base
        if ty == 'ESC':
            if t0 <= t <= t1 and m.RPM > 0:
                rpm.append(m.RPM)
            continue
        if ty == 'ISBH':
            types_seen.add(m.type)
            if m.type != want:
                cur = None
                continue
            cur = dict(N=m.N, inst=m.instance, t=t, rate=m.smp_rate, cnt=m.smp_cnt, mul=m.mul,
                       x=[], y=[], z=[])
            if t0 <= t <= t1:
                blocks.setdefault(m.instance, []).append(cur)
            continue
        if cur is None or m.N != cur['N']:
            continue
        cur['x'].extend(m.x)
        cur['y'].extend(m.y)
        cur['z'].extend(m.z)
    return parms, blocks, rpm, types_seen


def roles(parms, blocks, kind):
    """instance -> (imu index, 'pre'|'post')"""
    opt = int(parms.get('INS_LOG_BAT_OPT', 0))
    n = sum(1 for k in ID_PARAMS[kind] if parms.get(k, 0))
    pre_post = bool(opt & 4)
    post = bool(opt & 2)
    offset = pre_post or (post and bool(opt & 1))
    if n == 0:
        n = (max(blocks) + 1) // 2 if offset else max(blocks) + 1
    out = {}
    for inst in blocks:
        if offset and inst >= n:
            out[inst] = (inst - n, 'post')
        elif post and not pre_post:
            out[inst] = (inst, 'post')
        else:
            out[inst] = (inst, 'pre')
    return out, opt, n


def spectrum(bl, scale):
    """Average one-sided PSD over complete blocks; returns f, {axis: psd} in (unit^2/Hz)."""
    acc = {}
    f = None
    for b in bl:
        for ax in 'xyz':
            x = np.asarray(b[ax][:b['cnt']], dtype=float) * scale
            fb, p = signal.welch(x - x.mean(), fs=b['rate'], nperseg=len(x))
            if f is None:
                f = fb
            if len(p) != len(f):
                continue
            acc[ax] = acc.get(ax, 0) + p
    return f, {k: v / len(bl) for k, v in acc.items()}


def band_rms(f, p, lo, hi):
    sel = (f >= lo) & (f < hi)
    if sel.sum() < 2:
        return 0.0
    return float(np.sqrt(_trapz(p[sel], f[sel])))


def top_peaks(f, p, lo, hi, n):
    sel = (f >= lo) & (f <= hi)
    fi, pi = f[sel], p[sel]
    if len(fi) < 3:
        return []
    idx, _ = signal.find_peaks(pi)
    idx = idx[np.argsort(pi[idx])[::-1]][:n]
    return sorted((float(fi[i]), float(np.sqrt(pi[i]))) for i in idx)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('log')
    ap.add_argument('--from-time', type=float, required=True)
    ap.add_argument('--to-time', type=float, required=True)
    ap.add_argument('--type', default='gyro', choices=('gyro', 'accel'))
    ap.add_argument('--fmax', type=float, default=1000.0)
    ap.add_argument('--band', type=float, nargs=2, default=(15.0, 40.0), metavar=('LO', 'HI'),
                    help='band to report peaks and RMS for separately (default 15 40)')
    ap.add_argument('--npeaks', type=int, default=6)
    args = ap.parse_args()

    want = SENSOR_TYPE[args.type]
    parms, blocks, rpm, types_seen = collect(args.log, args.from_time, args.to_time, want)
    if not blocks:
        names = {0: 'accel', 1: 'gyro'}
        have = ', '.join(names.get(t, str(t)) for t in sorted(types_seen)) or 'none'
        sys.exit(f'no {args.type} ISBH/ISBD blocks in {args.from_time}-{args.to_time} s '
                 f'(types present in the log: {have}). Needs INS_LOG_BAT_MASK and an armed window.')
    role, opt, n_imu = roles(parms, blocks, args.type)
    unit = 'dps' if args.type == 'gyro' else 'm/s^2'
    to_unit = np.degrees(1.0) if args.type == 'gyro' else 1.0

    print(f"INS_LOG_BAT_MASK={int(parms.get('INS_LOG_BAT_MASK', 0))} INS_LOG_BAT_OPT={opt} "
          f"INS_LOG_BAT_CNT={int(parms.get('INS_LOG_BAT_CNT', 0))} "
          f"INS_LOG_BAT_LGIN={int(parms.get('INS_LOG_BAT_LGIN', 0))}  ({n_imu} {args.type} IMUs)")
    if rpm:
        print(f'ESC RPM mean {np.mean(rpm):.0f} -> motor fundamental ~{np.mean(rpm) / 60:.0f} Hz')
    if not any(r == 'post' for _, r in role.values()):
        print('pre-filter blocks only: the notch residual cannot be measured from this log '
              '(set INS_LOG_BAT_OPT=4 for pre+post)')

    lo, hi = args.band
    spectra = {}
    for inst in sorted(blocks):
        bl = [b for b in blocks[inst] if len(b['x']) >= b['cnt']]
        imu, r = role[inst]
        if not bl:
            print(f'\n=== IMU{imu} {r}-filter (instance {inst}): no complete block in window')
            continue
        mul = bl[0]['mul']
        scale = to_unit / mul
        f, ps = spectrum(bl, scale)
        spectra[(imu, r)] = (f, ps)
        fs = np.mean([b['rate'] for b in bl])
        print(f'\n=== IMU{imu} {r}-filter (instance {inst}): {len(bl)} blocks of {bl[0]["cnt"]} at {fs:.0f} Hz, '
              f'mul={mul} -> {unit}, resolution {f[1] - f[0]:.2f} Hz ===')
        hdr = ' '.join(f'{a}-{b}'.rjust(9) for a, b in BANDS if a < args.fmax)
        print(f"  {'axis':5s}{hdr}   [{lo:g}-{hi:g}]")
        for ax in 'xyz':
            p = ps[ax]
            cells = ' '.join(f'{band_rms(f, p, a, b):9.3f}' for a, b in BANDS if a < args.fmax)
            print(f'  {ax:5s}{cells}   {band_rms(f, p, lo, hi):.3f}')
        for ax in 'xyz':
            p = ps[ax]
            pk = top_peaks(f, p, 5.0, args.fmax, args.npeaks)
            pkb = top_peaks(f, p, lo, hi, 3)
            print(f'  {ax} peaks 5-{args.fmax:.0f} Hz: ' + ', '.join(f'{pf:.0f} Hz ({pa:.3f})' for pf, pa in pk)
                  + f'   in [{lo:g}-{hi:g}]: ' + ', '.join(f'{pf:.1f} Hz ({pa:.3f})' for pf, pa in pkb))

    pairs = sorted({imu for imu, r in spectra if (imu, 'pre') in spectra and (imu, 'post') in spectra})
    if pairs:
        print('\n=== attenuation pre -> post per band, dB (blocks are not simultaneous: read trends, not tenths; '
              'below 10 Hz is vehicle motion and is skipped) ===')
        hdr = ' '.join(f'{a}-{b}'.rjust(9) for a, b in BANDS if a < args.fmax)
        print(f"  {'':10s}{hdr}   [{lo:g}-{hi:g}]")
        for imu in pairs:
            fa, pa = spectra[(imu, 'pre')]
            fb, pb = spectra[(imu, 'post')]
            for ax in 'xyz':
                cells = []
                for a, b in BANDS:
                    if a >= args.fmax:
                        continue
                    x, y = band_rms(fa, pa[ax], a, b), band_rms(fb, pb[ax], a, b)
                    cells.append(f'{20 * np.log10(y / x):9.1f}' if b > 10 and x > 0 and y > 0 else f"{'-':>9s}")
                x, y = band_rms(fa, pa[ax], lo, hi), band_rms(fb, pb[ax], lo, hi)
                tail = f'{20 * np.log10(y / x):.1f}' if x > 0 and y > 0 else '-'
                print(f'  IMU{imu} {ax:4s} ' + ' '.join(cells) + f'   {tail}')
    posts = sorted({imu for imu, r in spectra if r == 'post'})
    if len(posts) > 1:
        print('\n=== post-filter band RMS per IMU (a motor band that is clean on one IMU and not the others '
              'means the notch is not on all IMUs) ===')
        for imu in posts:
            f, ps = spectra[(imu, 'post')]
            cells = ' '.join(f'{band_rms(f, ps["x"], a, b):9.3f}' for a, b in BANDS if a < args.fmax)
            print(f'  IMU{imu} x ' + cells)


if __name__ == '__main__':
    main()
