#!/usr/bin/env python3
"""
flow_cal_check.py - verify optical-flow scale/orientation against GPS truth.

Compares the gyro-compensated optical-flow rate to the flow rate implied by GPS
velocity, per body axis, over fast-motion samples. Reports a per-axis scale ratio
(maps directly to FLOW_FXSCALER / FLOW_FYSCALER), the correlation and effective
SNR on each axis (so a one-directional flight is flagged, not silently trusted),
and a cross-coupling number that catches a flow-frame rotation or a yaw/compass
error - which a per-axis scale cal cannot fix and must be ruled out first.

Requires a flight with GPS (outdoors), flow logged (OF or ROFH), ATT and RFND.
Flow may be the nav source or not; GPS is used only as the truth reference.

Flow model (matches AP_NavEKF3 FuseOptFlow):
    comp_flow.x = body_vel.y / range          (responds to sideways motion -> FXSCALER)
    comp_flow.y = -body_vel.x / range          (responds to forward  motion -> FYSCALER)
with body_vel from GPS NED velocity rotated by ATT.Yaw.

Usage:
    python3 flow_cal_check.py <log.bin> [--speed-min 1.5] [--qual-min 50]
"""
import sys
import math
import bisect
import argparse
from pymavlink import mavutil


def interp(t, series, idx):
    ts = [s[0] for s in series]
    k = bisect.bisect_left(ts, t)
    if 0 < k < len(series):
        a, b = series[k - 1], series[k]
        f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return a[idx] + f * (b[idx] - a[idx])
    return None


def lstsq2(rows, ys):
    # solve [p q] minimising sum (y - (p*x0 + q*x1))^2 ; rows are (x0, x1)
    sxx = sum(r[0] * r[0] for r in rows)
    sxy = sum(r[0] * r[1] for r in rows)
    syy = sum(r[1] * r[1] for r in rows)
    bx = sum(ys[i] * rows[i][0] for i in range(len(rows)))
    by = sum(ys[i] * rows[i][1] for i in range(len(rows)))
    det = sxx * syy - sxy * sxy
    if abs(det) < 1e-12:
        return 0.0, 0.0
    return (bx * syy - by * sxy) / det, (by * sxx - bx * sxy) / det


def fit_through_origin(x, y):
    sxx = sum(v * v for v in x)
    if sxx < 1e-12:
        return 0.0, 0.0
    slope = sum(x[i] * y[i] for i in range(len(x))) / sxx
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    sx = (sum((v - mx) ** 2 for v in x)) ** 0.5
    sy = (sum((v - my) ** 2 for v in y)) ** 0.5
    if sx * sy < 1e-12:
        return slope, 0.0
    corr = sum((x[i] - mx) * (y[i] - my) for i in range(len(x))) / (sx * sy)
    return slope, corr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--speed-min", type=float, default=1.5, help="min GPS speed (m/s) to include")
    ap.add_argument("--qual-min", type=float, default=50, help="min flow quality to include")
    args = ap.parse_args()

    m = mavutil.mavlink_connection(args.log)
    flow = []   # (t, cfx, cfy, qual)  gyro-compensated flow
    gps = []    # (t, vn, ve)
    att = []    # (t, yaw_rad)
    rng = []    # (t, dist)
    cur = {"FLOW_FXSCALER": 0.0, "FLOW_FYSCALER": 0.0}
    while True:
        msg = m.recv_match(type=["ROFH", "OF", "GPS", "ATT", "RFND", "PARM"], blocking=False)
        if msg is None:
            break
        ty = msg.get_type()
        t = msg._timestamp
        if ty == "ROFH":
            flow.append((t, msg.FX - msg.GX, msg.FY - msg.GY, msg.Qual))
        elif ty == "OF":
            flow.append((t, msg.flowX - msg.bodyX, msg.flowY - msg.bodyY, msg.Qual))
        elif ty == "GPS":
            c = math.radians(msg.GCrs)
            gps.append((t, msg.Spd * math.cos(c), msg.Spd * math.sin(c)))
        elif ty == "ATT":
            att.append((t, math.radians(msg.Yaw)))
        elif ty == "RFND" and getattr(msg, "Stat", 4) == 4 and 0.2 < msg.Dist < 8:
            rng.append((t, msg.Dist))
        elif ty == "PARM" and msg.Name in cur:
            cur[msg.Name] = msg.Value

    # ROFH and OF can both be present; prefer ROFH (dedup by keeping the larger set)
    if not flow or not gps or not att or not rng:
        print("missing data: flow=%d gps=%d att=%d rng=%d (need all)" %
              (len(flow), len(gps), len(att), len(rng)))
        return 1

    # build per-sample (measured cf) and (expected cf from GPS), in body axes
    mx, my, ex, ey, hgts = [], [], [], [], []
    for (t, cfx, cfy, q) in flow:
        if q < args.qual_min:
            continue
        r = interp(t, rng, 1)
        yaw = interp(t, att, 1)
        vn = interp(t, gps, 1)
        ve = interp(t, gps, 2)
        if None in (r, yaw, vn, ve):
            continue
        spd = math.hypot(vn, ve)
        if spd < args.speed_min:
            continue
        # body velocity from GPS NED + yaw
        bvx = vn * math.cos(yaw) + ve * math.sin(yaw)   # forward
        bvy = -vn * math.sin(yaw) + ve * math.cos(yaw)  # right
        ex.append(bvy / r)       # expected comp_flow.x
        ey.append(-bvx / r)      # expected comp_flow.y
        mx.append(cfx)
        my.append(cfy)
        hgts.append(r)

    n = len(mx)
    print("=== Flow calibration check ===")
    print("log: %s" % args.log)
    print("samples (Qual>=%g, speed>=%.1f m/s, valid rng): %d" % (args.qual_min, args.speed_min, n))
    if n < 30:
        print("NOT ENOUGH fast-motion samples - fly faster / longer runs.")
        return 1
    print("mean height: %.2f m   current FLOW_FXSCALER=%d FLOW_FYSCALER=%d\n" %
          (sum(hgts) / n, int(cur["FLOW_FXSCALER"]), int(cur["FLOW_FYSCALER"])))

    reliable = {}

    def report(label, param, exp, meas, cur_scaler):
        slope, corr = fit_through_origin(exp, meas)
        ratio = abs(slope)                              # scale magnitude (sign = log convention, irrelevant here)
        snr = (sum(v * v for v in exp) / n) ** 0.5      # rms of expected flow = how much that axis was exercised
        cur_sf = 1.0 + 0.001 * cur_scaler
        ok = snr >= 0.08 and abs(corr) >= 0.8
        reliable[param] = ok
        note = "reliable" if ok else "LOW-SNR/UNRELIABLE - exercise this axis more (move along it, faster)"
        sign = "" if slope >= 0 else "  (axis inverted vs model - check FLOW_ORIENT, not scaler)"
        new_scaler = ""
        if ok and ratio > 0.1:
            new_sf = cur_sf / ratio
            new_scaler = "  ->  set %s=%d" % (param, int(round((new_sf - 1.0) * 1000.0)))
        print("  %-22s n=%d  corr=%+.2f  exercise(rms)=%.2f  flow/ideal=%.2f%s%s  [%s]" %
              (label, n, corr, snr, ratio, sign, new_scaler, note))

    print("Per-axis flow scale (compensated flow vs GPS-implied):")
    report("X (sideways/FXSCALER)", "FLOW_FXSCALER", ex, mx, cur["FLOW_FXSCALER"])
    report("Y (forward/FYSCALER)", "FLOW_FYSCALER", ey, my, cur["FLOW_FYSCALER"])

    # cross-coupling: only meaningful if BOTH axes were exercised
    print("\nCross-coupling (flow rotation / yaw-error) check:")
    if reliable.get("FLOW_FXSCALER") and reliable.get("FLOW_FYSCALER"):
        a, b = lstsq2(list(zip(ex, ey)), mx)   # cfx = a*ex + b*ey
        c, d = lstsq2(list(zip(ex, ey)), my)   # cfy = c*ex + d*ey
        diag = (abs(a) + abs(d)) / 2.0
        offd = (abs(b) + abs(c)) / 2.0
        pct = 100.0 * offd / diag if diag > 1e-6 else 0.0
        verdict = "OK, axes aligned" if pct < 15 else "HIGH - flow rotated or yaw/compass wrong; fix orientation FIRST"
        print("  off-diagonal/diagonal = %.0f%%   [%s]" % (pct, verdict))
    else:
        print("  not assessable - both axes must be exercised (fly forward+back AND left+right at speed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
