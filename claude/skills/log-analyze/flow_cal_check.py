#!/usr/bin/env python3
"""
flow_cal_check.py - verify optical-flow scale/orientation against GPS truth.

Compares the gyro-compensated optical-flow rate to the flow rate implied by GPS
velocity, per body axis, over fast-motion samples. Reports a per-axis scale ratio
(maps directly to FLOW_FXSCALER / FLOW_FYSCALER), the correlation and effective
SNR on each axis (so a one-directional flight is flagged, not silently trusted),
and a cross-coupling number that catches a flow-frame rotation or a yaw/compass
error - which a per-axis scale cal cannot fix and must be ruled out first.

It also cross-checks the flow sensor's reported body rate against the flight-
controller IMU gyro. A sensor that clocks its whole output at the wrong rate (e.g.
a DroneCAN flow node reporting integration_interval 2x off) under-reports flow AND
its own gyro by the same factor. That is invisible to the onboard FlowCal (which
fits flow against the sensor's own gyro) and to a flowX-vs-bodyX eyeball check, and
a FLOW_*SCALER cannot fix it (the scaler scales flowRate but not bodyRate). The IMU
is the only external witness, so when the sensor/IMU gyro slope is not ~1.0 the
scaler suggestion is suppressed.

Requires a flight with GPS (outdoors), flow logged (OF or ROFH), ATT and RFND or
XKF6. The IMU gyro check additionally needs the IMU message.
Flow may be the nav source or not; GPS is used only as the truth reference.

Flow model (matches AP_NavEKF3 FuseOptFlow):
    comp_flow.x = body_vel.y / range          (responds to sideways motion -> FXSCALER)
    comp_flow.y = -body_vel.x / range          (responds to forward  motion -> FYSCALER)
with body_vel from GPS NED velocity rotated by ATT.Yaw.

Usage:
    python3 flow_cal_check.py <log.bin> [--speed-min 1.0] [--qual-min 50]
                              [--height auto|aglkf|rfnd]
"""
import sys
import math
import bisect
import argparse
from pymavlink import mavutil


# Longest gap in the height series that may be bridged. A rangefinder that
# is out of range logs nothing valid, so without a bound the height is
# interpolated straight across the gap: field log 356 flew at 14-53m against
# a 15m sensor and every sample in between was handed a ~14m height, which
# inflated the expected flow about threefold and reported flow/ideal 0.37 as
# [reliable]. Truncation biases a fit without scattering it, so the
# correlation stays high and nothing looks wrong.
RANGE_MAX_GAP = 0.5


def interp(t, series, idx, max_gap=None):
    ts = [s[0] for s in series]
    k = bisect.bisect_left(ts, t)
    if 0 < k < len(series):
        a, b = series[k - 1], series[k]
        if max_gap is not None and (b[0] - a[0]) > max_gap:
            return None
        f = (t - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
        return a[idx] + f * (b[idx] - a[idx])
    return None


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


def sensor_rate_slope(srate, imu):
    # Regress the flow sensor's reported body rate against the FC IMU gyro during
    # rotation (per axis, through origin). |slope| ~1.0 means the sensor clocks its
    # output at the right rate. A slope far from 1 means the whole sensor (flow AND
    # gyro) is mis-rated - a FLOW_*SCALER cannot fix that.
    out = {}
    for axis, col in (("X", 1), ("Y", 2)):
        xs, ys = [], []
        for s in srate:
            fc = interp(s[0], imu, col)
            if fc is None or abs(fc) < 0.15:   # rotation only
                continue
            xs.append(fc)
            ys.append(s[col])
        out[axis] = fit_through_origin(xs, ys) + (len(xs),) if len(xs) >= 30 else None
    return out


def report_sensor_rate(srate, imu, cur_ratef):
    # Prints the sensor-rate verdict and returns True when the node clocks its
    # output at the right rate. Needs no truth reference - only the flow node's
    # own gyro and the FC IMU - so it is valid on a GPS-less indoor flight.
    srs = sensor_rate_slope(srate, imu) if (srate and imu) else {}
    have = [srs[a] for a in ("X", "Y") if srs.get(a)]
    if not have:
        print("Sensor-rate check: no IMU + flow gyro pair logged - cannot verify\n")
        return True
    mag = sum(abs(s[0]) for s in have) / len(have)
    ok = 0.85 <= mag <= 1.18
    print("Sensor-rate check (flow node gyro vs FC IMU, during rotation):")
    for a in ("X", "Y"):
        if srs.get(a):
            sl, co, nn = srs[a]
            print("  %s: sensor/IMU slope=%+.2f corr=%+.2f n=%d" % (a, sl, co, nn))
    if not ok:
        print("  *** slope != 1.0: the flow node is reporting at the WRONG RATE ***")
        print("  *** flow AND its gyro are scaled by ~%.2fx together - a FLOW_*SCALER" % mag)
        print("  *** cannot fix this (it scales flowRate, not bodyRate).")
        print("  *** HereFlow/DroneCAN fix: set FLOW_HF_RATEF=%.2f (= current %.2f / slope;" %
              (cur_ratef / mag, cur_ratef))
        print("  ***   scales flow and gyro together, keeping the gyro compensation valid).")
        print("  *** Root cause is sensor-side: integration_interval / IMU_INTEG_RATE / firmware.")
    else:
        print("  slope ~1.0: sensor output rate looks correct.")
    print("")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("--speed-min", type=float, default=1.0, help="min GPS speed (m/s) to include")
    ap.add_argument("--qual-min", type=float, default=50, help="min flow quality to include")
    ap.add_argument("--gps-lag", type=float, default=None,
                    help="seconds the GPS velocity lags the flow sample. Default scans "
                         "-0.2..1.0 s and picks the alignment with the best correlation; "
                         "a stale alignment attenuates the fitted scale.")
    ap.add_argument("--height", choices=["auto", "aglkf", "rfnd"], default="auto",
                    help="height source for the flow range. aglkf=XKF6.HAgl (what the EKF "
                         "actually feeds the flow fusion when EK3_OPTIONS bit 4 is set); rfnd=raw "
                         "RFND.Dist. auto prefers aglkf when present. Calibrating against the "
                         "height the EKF uses makes the EKF velocity correct by construction.")
    args = ap.parse_args()

    m = mavutil.mavlink_connection(args.log)
    rofh = []   # (t, cfx, cfy, qual)  gyro-compensated flow from EKF replay log
    of = []     # (t, cfx, cfy, qual)  gyro-compensated flow from OpticalFlow log
    rofh_g = []  # (t, bx, by)  sensor body rate logged alongside ROFH
    of_g = []    # (t, bx, by)  sensor body rate logged alongside OF
    gps = []    # (t, vn, ve)
    att = []    # (t, yaw_rad)
    rfnd = []   # (t, dist)
    aglkf = []  # (t, hagl)  XKF6 AGL Kalman filter, core 0, valid
    imu = []    # (t, gx, gy)  flight-controller IMU gyro, instance 0
    cur = {"FLOW_FXSCALER": 0.0, "FLOW_FYSCALER": 0.0, "FLOW_HF_RATEF": 1.0,
           "RNGFND1_MAX": 0.0}
    while True:
        msg = m.recv_match(type=["ROFH", "OF", "GPS", "ATT", "RFND", "XKF6", "IMU", "PARM"], blocking=False)
        if msg is None:
            break
        ty = msg.get_type()
        t = msg._timestamp
        # ROFH/OF log the driver's raw flowRate and bodyRate. writeOptFlowMeas
        # negates the flow before compensating (AP_NavEKF3_Measurements.cpp:225,
        # flowRadXYcomp = -rawFlow + bodyRate), so negate here to compare against
        # the same losPred model the EKF fuses. Without this every log reads
        # "sign inverted" regardless of FLOW_ORIENT_YAW.
        if ty == "ROFH":
            rofh.append((t, msg.GX - msg.FX, msg.GY - msg.FY, msg.Qual))
            rofh_g.append((t, msg.GX, msg.GY))
        elif ty == "OF":
            of.append((t, msg.bodyX - msg.flowX, msg.bodyY - msg.flowY, msg.Qual))
            of_g.append((t, msg.bodyX, msg.bodyY))
        elif ty == "GPS" and getattr(msg, "Status", 3) >= 3:
            c = math.radians(msg.GCrs)
            gps.append((t, msg.Spd * math.cos(c), msg.Spd * math.sin(c),
                        getattr(msg, "VZ", 0.0)))
        elif ty == "ATT":
            att.append((t, math.radians(msg.Roll), math.radians(msg.Pitch),
                        math.radians(msg.Yaw)))
        elif ty == "RFND" and getattr(msg, "Stat", 4) == 4 and msg.Dist > 0.2:
            rfnd.append((t, msg.Dist))
        elif ty == "XKF6" and msg.C == 0 and msg.Valid == 1 and 0.05 < msg.HAgl < 50:
            aglkf.append((t, msg.HAgl))
        elif ty == "IMU" and getattr(msg, "I", 0) == 0:
            imu.append((t, msg.GyrX, msg.GyrY))
        elif ty == "PARM" and msg.Name in cur:
            cur[msg.Name] = msg.Value

    # ROFH and OF carry the same _state.flowRate; use whichever was logged (ROFH
    # if both, they are identical) rather than concatenating and double-counting.
    flow = rofh if rofh else of
    flow_src = "ROFH" if rofh else "OF"
    srate = rofh_g if rofh else of_g

    # Cap the range at the sensor's own configured max. A fixed cap silently
    # truncates every sample taken near it, and because only the short readings
    # survive, the height used comes out low and the fitted scale comes out low
    # with it - a vehicle hovering at the cap can read 0.75 on a sensor that is
    # actually correct.
    rmax = cur["RNGFND1_MAX"] if cur["RNGFND1_MAX"] > 0.5 else 8.0
    rfnd = [s for s in rfnd if s[1] < rmax]
    if rfnd:
        near = sum(1 for s in rfnd if s[1] > 0.9 * rmax)
        if near > 0.2 * len(rfnd):
            print("WARNING: %.0f%% of rangefinder samples are within 10%% of RNGFND1_MAX=%.0f m."
                  % (100.0 * near / len(rfnd), rmax))
            print("         The fit is truncation-biased toward low scale - fly lower.\n")

    # Default to the raw rangefinder. The AGL KF is a filtered product and any lag
    # or attenuation in it lands directly in the fitted scale - on one airframe it
    # turned a 0.96 ratio into 0.55 and dropped the correlation from 0.97 to 0.87.
    # Calibrate the sensor against the honest reference and fix the AGL KF
    # separately; --height aglkf remains for the closed-loop comparison.
    if args.height == "aglkf" or (args.height == "auto" and not rfnd):
        rng, hsrc = aglkf, "XKF6.HAgl (AGL KF)"
    else:
        rng, hsrc = rfnd, "RFND.Dist"
    if args.height == "auto" and rfnd and aglkf:
        hsrc += "  (XKF6 present; --height aglkf to compare)"

    print("=== Flow calibration check ===")
    print("log: %s" % args.log)
    print("flow source: %s    height source: %s" % (flow_src, hsrc))
    print("current FLOW_FXSCALER=%d FLOW_FYSCALER=%d FLOW_HF_RATEF=%.2f\n" %
          (int(cur["FLOW_FXSCALER"]), int(cur["FLOW_FYSCALER"]), cur["FLOW_HF_RATEF"]))

    # The sensor-rate check needs no truth reference, so it runs before the GPS
    # gate - an indoor bring-up flight with no fix still answers it.
    sensor_rate_ok = report_sensor_rate(srate, imu, cur["FLOW_HF_RATEF"])

    if not flow or not gps or not att or not rng:
        print("Scale check needs GPS truth: flow=%d gps=%d att=%d rng(%s)=%d" %
              (len(flow), len(gps), len(att), hsrc, len(rng)))
        if flow and att and rng and not gps:
            print("no GPS fix in this log - fly outdoors with a fix to check flow scale.")
        return 0

    # build per-sample (measured cf) and (expected cf from GPS), in body axes.
    # `shift` delays the GPS series to line it up with the flow; GPS velocity is
    # reported later than the flow sample it belongs to, and at 3 m/s over 4 m of
    # height even 0.2 s of skew attenuates the fitted slope noticeably.
    def build(shift):
        mx, my, ex, ey, hgts = [], [], [], [], []
        no_range = 0
        for (t, cfx, cfy, q) in flow:
            if q < args.qual_min:
                continue
            r = interp(t, rng, 1, RANGE_MAX_GAP)
            if r is None:
                no_range += 1
            roll = interp(t, att, 1)
            pitch = interp(t, att, 2)
            yaw = interp(t, att, 3)
            vn = interp(t - shift, gps, 1)
            ve = interp(t - shift, gps, 2)
            vd = interp(t - shift, gps, 3)
            if None in (r, roll, pitch, yaw, vn, ve, vd):
                continue
            if math.hypot(vn, ve) < args.speed_min:
                continue
            # NED -> body, full rotation. The EKF's model is losPred =
            # {relVelSensor.y, -relVelSensor.x}/range with relVelSensor =
            # prevTnb*velocity, so yaw alone is not enough once the vehicle
            # leans: at 20 deg of tilt a yaw-only rotation is ~6% out.
            cr, sr = math.cos(roll), math.sin(roll)
            cp, sp = math.cos(pitch), math.sin(pitch)
            cy, sy = math.cos(yaw), math.sin(yaw)
            bvx = cp * cy * vn + cp * sy * ve - sp * vd
            bvy = ((sr * sp * cy - cr * sy) * vn +
                   (sr * sp * sy + cr * cy) * ve + sr * cp * vd)
            ex.append(bvy / r)       # expected comp_flow.x
            ey.append(-bvx / r)      # expected comp_flow.y
            mx.append(cfx)
            my.append(cfy)
            hgts.append(r)
        return mx, my, ex, ey, hgts, no_range

    def split(ex, ey, n, dom=1.5):
        return ([i for i in range(n) if abs(ey[i]) >= dom * abs(ex[i])],
                [i for i in range(n) if abs(ex[i]) >= dom * abs(ey[i])])

    def score(shift):
        # n-weighted mean |corr| over both dominant-motion subsets
        mx, my, ex, ey, _, _ = build(shift)
        n = len(mx)
        if n < 30:
            return -1.0
        fwd, side = split(ex, ey, n)
        tot = wt = 0.0
        for idx, e, mm in ((side, ex, mx), (fwd, ey, my)):
            if len(idx) < 30:
                continue
            _, c = fit_through_origin([e[i] for i in idx], [mm[i] for i in idx])
            tot += abs(c) * len(idx)
            wt += len(idx)
        return tot / wt if wt else -1.0

    if args.gps_lag is None:
        best, lag = -1.0, 0.0
        s = -0.2
        while s <= 1.0001:
            v = score(s)
            if v > best:
                best, lag = v, s
            s += 0.05
    else:
        lag = args.gps_lag
    mx, my, ex, ey, hgts, no_range = build(lag)
    print("GPS alignment: flow leads GPS by %.2f s%s\n" %
          (lag, " (auto)" if args.gps_lag is None else " (forced)"))

    n = len(mx)
    print("samples (Qual>=%g, speed>=%.1f m/s, valid rng): %d" % (args.qual_min, args.speed_min, n))
    if no_range:
        # not a warning about the fit but about the flight: it says how much
        # of it was flown with no height to scale flow by
        print("dropped %d flow samples with no height within %.1fs "
              "(rangefinder out of range or not returning)" % (no_range, RANGE_MAX_GAP))
    if n < 30:
        print("NOT ENOUGH fast-motion samples - fly faster / longer runs.")
        return 1
    print("mean height: %.2f m\n" % (sum(hgts) / n))

    # The flow sensor is body-fixed, so an axis is only exercised by motion ALONG
    # that body axis. Yawing the nose to face the direction of travel keeps even a
    # ground-frame left/right run on the forward axis. Fit each axis from the
    # samples where its own motion dominates, so a flight that does forward/back
    # and strafe in separate segments still calibrates both.
    fwd_idx, side_idx = split(ex, ey, n)   # forward/back -> FYSCALER, strafe -> FXSCALER
    print("Body-frame motion split: forward/back=%d  strafe(sideways)=%d  (of %d)" %
          (len(fwd_idx), len(side_idx), n))

    reliable = {}

    def report(label, param, idx, exp, meas, other, cur_scaler):
        if len(idx) < 30:
            reliable[param] = False
            print("  %-22s n=%-5d not exercised - too few samples moving along this body axis" %
                  (label, len(idx)))
            return
        e = [exp[i] for i in idx]
        mm = [meas[i] for i in idx]
        om = [other[i] for i in idx]
        slope, corr = fit_through_origin(e, mm)
        ratio = abs(slope)                              # scale magnitude (sign = convention, handled separately)
        snr = (sum(v * v for v in e) / len(e)) ** 0.5   # rms of expected flow on this axis
        leak_slope, _ = fit_through_origin(e, om)       # flow that landed on the OTHER axis
        leak_pct = 100.0 * abs(leak_slope) / ratio if ratio > 1e-6 else 0.0
        cur_sf = 1.0 + 0.001 * cur_scaler
        ok = snr >= 0.08 and abs(corr) >= 0.8
        reliable[param] = ok
        note = "reliable" if ok else "UNRELIABLE - move faster/longer along this axis"
        sign = "" if slope >= 0 else "  *** SIGN INVERTED - flow opposes the model, check FLOW_ORIENT_YAW ***"
        new_scaler = ""
        if ok and ratio > 0.1:
            if sensor_rate_ok:
                new_sf = cur_sf / ratio
                new_scaler = "  ->  set %s=%d" % (param, int(round((new_sf - 1.0) * 1000.0)))
            else:
                new_scaler = "  ->  (scaler suggestion suppressed: sensor-rate error, see above)"
        print("  %-22s n=%-5d corr=%+.2f  flow/ideal=%.2f  cross-axis=%.0f%%%s%s  [%s]" %
              (label, len(idx), corr, ratio, leak_pct, sign, new_scaler, note))

    print("Per-axis flow scale (each axis fit on its own dominant body motion):")
    report("X (sideways/FXSCALER)", "FLOW_FXSCALER", side_idx, ex, mx, my, cur["FLOW_FXSCALER"])
    report("Y (forward/FYSCALER)", "FLOW_FYSCALER", fwd_idx, ey, my, mx, cur["FLOW_FYSCALER"])

    print("\ncross-axis = flow that leaked onto the other axis during this motion.")
    print("high (>15%) on a reliable axis => flow frame rotated or yaw/compass")
    print("wrong; fix orientation before trusting the scaler.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
