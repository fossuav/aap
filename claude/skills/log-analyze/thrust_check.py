#!/usr/bin/env python3
"""What the vehicle's thrust map ACTUALLY is, against what the applet's ThrustCal claimed.

Specific force along body -z IS thrust: there is no gravity in an accelerometer reading, and
no need to differentiate anything or know the attitude. So `IMU.AccZ / -g` is thrust in g at
whatever throttle `CTUN.ThO` was commanding, at any attitude, throughout the flight.

Two filters make that honest, and both matter:

  * Reject any sample with a motor at MOT_SPIN_MAX. The mixer has clipped, so the commanded
    throttle is not what was flown, and including those makes a healthy map look short.
  * Report the buckets with their sample counts. Hover has thousands of samples and the high
    end has a handful, so a naive least-squares is dominated by hover -- which is the end
    that matters least, since the arcs live at 0.4-0.8.

Use it to answer "is the calibration wrong, or is the vehicle not delivering?" -- a question
this project got backwards once. On 2026-07-19 the map's SLOPE was accurate to +-0.14 g right
across 0.4-0.6 of throttle, and the crash flight's shortfall (5.85 g of a predicted 6.65,
motor pegged) was a failing battery, not a bad fit. What genuinely scattered was g0, read in
free fall where the descent's drag adds to apparent thrust: 0.36 g against 0.20 g on the same
airframe three hours apart.

The HOVER row is the anchor to judge a calibration by: a hovering vehicle makes 1.00 g by
definition, so whatever the map predicts there is its low-end error.

Usage:
    thrust_check.py <log.bin> [--spin-max-pwm 1950] [--hover-window S] [--from S --to S]
"""
import argparse
import math
import re
import sys

from pymavlink import mavutil

G = 9.81


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--spin-max-pwm", type=int, default=1950,
                    help="reject samples with any motor at or above this (default 1950, "
                         "= MOT_PWM_MIN 1000 + MOT_SPIN_MAX 0.95)")
    ap.add_argument("--from", dest="t0", type=float, default=-1e9)
    ap.add_argument("--to", dest="t1", type=float, default=1e9)
    a = ap.parse_args()

    mlog = mavutil.mavlink_connection(a.log)
    thr, acc, rcou, msgs = [], [], [], []
    while True:
        m = mlog.recv_match(type=["CTUN", "IMU", "RCOU", "MSG"])
        if m is None:
            break
        t = getattr(m, "TimeUS", None)
        if t is None:
            continue
        t /= 1e6
        ty = m.get_type()
        if ty == "CTUN":
            thr.append((t, m.ThO))
        elif ty == "IMU" and m.I == 0:
            acc.append((t, -m.AccZ / G))
        elif ty == "RCOU":
            rcou.append((t, max(m.C1, m.C2, m.C3, m.C4)))
        elif ty == "MSG":
            msgs.append((t, m.Message))
    if not thr or not acc:
        sys.exit("need CTUN and IMU in the log")

    g0 = kt = None
    for _, text in msgs:
        hit = re.search(r"ThrustCal: idle ([\d.]+)g ([\d.]+) g/thr", text)
        if hit:
            g0, kt = float(hit.group(1)), float(hit.group(2))
    print(f"{a.log}")
    if kt:
        print(f"  ThrustCal claimed: g0={g0:.2f} g  k={kt:.1f} g/thr  "
              f"max {g0 + kt:.2f} g  (implies hover at {(1.0 - g0) / kt:.3f})")
    else:
        print("  no ThrustCal line in log -- measuring only")
        g0 = kt = 0.0

    near = lambda s, t: min(s, key=lambda r: abs(r[0] - t))
    pts, clipped = [], 0
    for t, th in thr:
        if th < 0.02 or not (a.t0 <= t <= a.t1):
            continue
        g = near(acc, t)
        if abs(g[0] - t) > 0.05:
            continue
        if rcou and near(rcou, t)[1] >= a.spin_max_pwm:
            clipped += 1
            continue
        pts.append((th, g[1]))
    if not pts:
        sys.exit("no usable samples")

    buckets = {}
    for th, g in pts:
        buckets.setdefault(round(th, 1), []).append(g)

    print(f"  {len(pts)} samples used, {clipped} rejected for mixer clip\n")
    print(f"  {'throttle':>9} {'n':>6} {'measured':>9} {'cal says':>9} {'err':>7}")
    for b in sorted(buckets):
        v = buckets[b]
        if len(v) < 3:
            continue
        mean = sum(v) / len(v)
        pred = g0 + kt * b
        tag = "  <-- HOVER (truth is 1.00 g)" if abs(mean - 1.0) < 0.06 and b < 0.2 else ""
        print(f"  {b:9.1f} {len(v):6d} {mean:8.2f} g {pred:8.2f} g "
              f"{mean - pred:+7.2f}{tag}")

    hi = [(th, g) for th, g in pts if th >= 0.25]
    if len(hi) >= 10:
        n = len(hi)
        sx = sum(p[0] for p in hi)
        sy = sum(p[1] for p in hi)
        sxx = sum(p[0] * p[0] for p in hi)
        sxy = sum(p[0] * p[1] for p in hi)
        den = n * sxx - sx * sx
        if abs(den) > 1e-9:
            k = (n * sxy - sx * sy) / den
            i = (sy - k * sx) / n
            print(f"\n  fit over throttle>=0.25 (n={n}): g0={i:.2f} k={k:.2f} "
                  f"max={i + k:.2f} g")
            print("  (sparse at the high end and contaminated by drag during manoeuvres --"
                  "\n   read the per-bucket errors above in preference to this line)")


if __name__ == "__main__":
    main()
