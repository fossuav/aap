#!/usr/bin/env python3
'''
Does the optical flow measure the vehicle's motion? A check that needs no GPS.

Over short windows the velocity change the flow implies is compared with the
velocity change the accelerometers integrate to. Integration drifts, but not over
half a second: a 0.1 m/s/s accel bias is 0.05 m/s there.

  flow: compensated flow (bodyRate - flowRate, as the EKF fuses it) times the
        range finder's slant range gives two body-frame velocity components,
        averaged over +-0.1 s; with the EKF's vertical velocity they solve for
        north and east
  IMU:  earth-frame acceleration R*(acc - bias) + g, integrated over the window,
        with the EKF's attitude (XKQ, else ATT) and accel bias (XKF2)

Reported as the slope and correlation of flow dV against IMU dV, pooled over
north and east, by flow quality, height and latch state. A flow that measures
motion reads slope near 1 and correlation well above 0.5. The EKF's own dV is
shown alongside; it follows the IMU by construction, so it is a control, not a
verdict. With GPS in the log, GPS dV against the IMU validates the reference
itself, and flow against GPS is shown too.

AP_FLAKE8_CLEAN
'''

import argparse
import bisect
import math

from pymavlink import mavutil

AVG_S = 0.1
QUALITY_BINS = ((0, 40), (40, 50), (50, 60), (60, 70), (70, 100), (100, 150), (150, 256))
HEIGHT_BINS = ((0.3, 0.6), (0.6, 1.0), (1.0, 2.0), (2.0, 5.0), (5.0, 1000.0))


def quat_to_dcm(w, x, y, z):
    '''body to NED rotation from a quaternion'''
    return ((1 - 2*(y*y + z*z), 2*(x*y - w*z), 2*(x*z + w*y)),
            (2*(x*y + w*z), 1 - 2*(x*x + z*z), 2*(y*z - w*x)),
            (2*(x*z - w*y), 2*(y*z + w*x), 1 - 2*(x*x + y*y)))


def euler_to_dcm(roll, pitch, yaw):
    '''body to NED rotation from Euler angles in radians'''
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return ((cp*cy, sr*sp*cy - cr*sy, cr*sp*cy + sr*sy),
            (cp*sy, sr*sp*sy + cr*cy, cr*sp*sy - sr*cy),
            (-sp, sr*cp, cr*cp))


class Series:
    def __init__(self):
        self.t = []
        self.v = []

    def add(self, t, v):
        self.t.append(t)
        self.v.append(v)

    def at(self, t, max_gap):
        i = bisect.bisect_left(self.t, t)
        best = None
        for j in (i - 1, i):
            if 0 <= j < len(self.t) and abs(self.t[j] - t) <= max_gap:
                if best is None or abs(self.t[j] - t) < abs(self.t[best] - t):
                    best = j
        return None if best is None else self.v[best]

    def between(self, a, b):
        i = bisect.bisect_left(self.t, a)
        k = bisect.bisect_right(self.t, b)
        return self.t[i:k], self.v[i:k]


def load(path):
    m = mavutil.mavlink_connection(path)
    s = {k: Series() for k in ('of', 'rng', 'q', 'att', 'imu', 'bias', 'ekfv', 'gps')}
    armed = []
    msgs = []
    t0 = None
    while True:
        msg = m.recv_match(type=['OF', 'RFND', 'XKQ', 'ATT', 'IMU', 'XKF2', 'XKF1', 'ARM', 'MSG', 'GPS'],
                           blocking=False)
        if msg is None:
            break
        tp = msg.get_type()
        t = msg.TimeUS * 1e-6
        if t0 is None:
            t0 = t
        t -= t0
        if tp == 'OF':
            s['of'].add(t, (msg.bodyX - msg.flowX, msg.bodyY - msg.flowY, msg.Qual))
        elif tp == 'RFND' and getattr(msg, 'Orient', 25) == 25:
            s['rng'].add(t, (msg.Dist, getattr(msg, 'Stat', 4)))
        elif tp == 'XKQ' and msg.C == 0:
            s['q'].add(t, quat_to_dcm(msg.Q1, msg.Q2, msg.Q3, msg.Q4))
        elif tp == 'ATT':
            s['att'].add(t, euler_to_dcm(math.radians(msg.Roll), math.radians(msg.Pitch), math.radians(msg.Yaw)))
        elif tp == 'IMU' and getattr(msg, 'I', 0) == 0:
            s['imu'].add(t, (msg.AccX, msg.AccY, msg.AccZ))
        elif tp == 'XKF2' and msg.C == 0:
            s['bias'].add(t, (msg.AX, msg.AY, msg.AZ))
        elif tp == 'XKF1' and msg.C == 0:
            s['ekfv'].add(t, (msg.VN, msg.VE, msg.VD))
        elif tp == 'ARM':
            armed.append((t, bool(msg.ArmState)))
        elif tp == 'GPS' and getattr(msg, 'I', 0) == 0 and msg.Status >= 3:
            c = math.radians(msg.GCrs)
            s['gps'].add(t, (msg.Spd * math.cos(c), msg.Spd * math.sin(c)))
        elif tp == 'MSG':
            msgs.append((t, msg.Message))
    if not s['q'].t:
        s['q'] = s['att']
    return s, armed, msgs


def armed_at(armed, t):
    state = False
    for ta, a in armed:
        if ta > t:
            break
        state = a
    return state


def flow_vel(s, t):
    '''north, east velocity from one flow sample at time t, with quality, range and cos(tilt)'''
    o = s['of'].at(t, 0.1)
    r = s['rng'].at(t, 0.2)
    R = s['q'].at(t, 0.2)
    ev = s['ekfv'].at(t, 0.2)
    if None in (o, r, R, ev) or r[1] != 4 or r[0] < 0.3:
        return None
    cfx, cfy, q = o
    bvx = -cfy * r[0]
    bvy = cfx * r[0]
    vd = ev[2]
    # body = R^T ned, so bvx = R00 vn + R10 ve + R20 vd and bvy = R01 vn + R11 ve + R21 vd
    a, b, c = R[0][0], R[1][0], bvx - R[2][0] * vd
    d, e, f = R[0][1], R[1][1], bvy - R[2][1] * vd
    det = a * e - b * d
    if abs(det) < 0.5:
        return None
    return ((c * e - b * f) / det, (a * f - c * d) / det, q, r[0], R[2][2])


def flow_vel_avg(s, t, lag):
    '''flow velocity averaged over +-AVG_S around t, the flow taken lag later'''
    ts, _ = s['of'].between(t + lag - AVG_S, t + lag + AVG_S)
    acc = [v for v in (flow_vel(s, tt) for tt in ts) if v]
    if not acc:
        return None
    n = len(acc)
    return (sum(v[0] for v in acc) / n, sum(v[1] for v in acc) / n, min(v[2] for v in acc),
            sum(v[3] for v in acc) / n, min(v[4] for v in acc))


def imu_dv(s, a, b):
    '''integrated earth-frame horizontal acceleration over [a, b]'''
    ts, vs = s['imu'].between(a, b)
    if len(ts) < 4:
        return None
    dvn = dve = 0.0
    for i in range(1, len(ts)):
        dt = ts[i] - ts[i - 1]
        if dt > 0.25:
            return None
        R = s['q'].at(ts[i], 0.25)
        if R is None:
            return None
        bias = s['bias'].at(ts[i], 1.0) or (0.0, 0.0, 0.0)
        ax, ay, az = (vs[i][0] - bias[0], vs[i][1] - bias[1], vs[i][2] - bias[2])
        dvn += (R[0][0] * ax + R[0][1] * ay + R[0][2] * az) * dt
        dve += (R[1][0] * ax + R[1][1] * ay + R[1][2] * az) * dt
    return dvn, dve


def windows(s, armed, T, step, lag, gps_lag):
    out = []
    if not s['of'].t:
        return out
    t = s['of'].t[0]
    end = s['of'].t[-1] - T
    while t < end:
        if armed_at(armed, t):
            f0 = flow_vel_avg(s, t, lag)
            f1 = flow_vel_avg(s, t + T, lag) if f0 else None
            im = imu_dv(s, t, t + T) if f1 else None
            e0 = s['ekfv'].at(t, 0.2)
            e1 = s['ekfv'].at(t + T, 0.2)
            if f0 and f1 and im and e0 and e1 and min(f0[4], f1[4]) > math.cos(math.radians(35)):
                w = {'t': t, 'flow': (f1[0] - f0[0], f1[1] - f0[1]), 'imu': im,
                     'ekf': (e1[0] - e0[0], e1[1] - e0[1]), 'q': min(f0[2], f1[2]),
                     'h': 0.5 * (f0[3] + f1[3])}
                g0 = s['gps'].at(t + gps_lag, 0.3)
                g1 = s['gps'].at(t + T + gps_lag, 0.3)
                if g0 and g1:
                    w['gps'] = (g1[0] - g0[0], g1[1] - g0[1])
                out.append(w)
        t += step
    return out


def fit(ws, key, ref='imu'):
    '''slope of key's dV against ref's dV through the origin, both axes pooled, with correlation and rms error'''
    xs, ys = [], []
    for w in ws:
        if key in w and ref in w:
            xs += [w[ref][0], w[ref][1]]
            ys += [w[key][0], w[key][1]]
    n = len(xs)
    if n < 20:
        return None
    sxx = sum(x * x for x in xs)
    sxy = sum(x * y for x, y in zip(xs, ys))
    syy = sum(y * y for y in ys)
    if sxx <= 0 or syy <= 0:
        return None
    rms = math.sqrt(sum((y - x) ** 2 for x, y in zip(xs, ys)) / n)
    return n // 2, sxy / sxx, sxy / math.sqrt(sxx * syy), rms, math.sqrt(sxx / n)


def fmt(f):
    return '%5.2f %5.2f %4.2f' % (f[1], f[2], f[3]) if f else '    -     -    -'


def row(label, ws, show_gps):
    f = fit(ws, 'flow')
    if f is None:
        return
    line = '  %-20s %5d  %s   %s   %4.2f' % (label, f[0], fmt(f), fmt(fit(ws, 'ekf')), f[4])
    if show_gps:
        line += '   %s   %s' % (fmt(fit(ws, 'gps')), fmt(fit(ws, 'flow', 'gps')))
    print(line)


def best_lag(s, armed, T, key, ref, lags, flow_lag=0.0, min_quality=0, trace=False):
    best = None
    for lag in lags:
        if key == 'flow':
            ws = windows(s, armed, T, 0.25, lag, 0.0)
        else:
            ws = windows(s, armed, T, 0.25, flow_lag, lag)
        f = fit([w for w in ws if w['q'] >= min_quality], key, ref)
        if trace and f:
            print('  lag %3d ms: n %4d slope %5.2f corr %5.2f' % (lag * 1000, f[0], f[1], f[2]))
        if f and (best is None or f[2] > best[1]):
            best = (lag, f[2])
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__.strip().split('\n')[0])
    ap.add_argument('log')
    ap.add_argument('--window', type=float, default=0.5, help='window length, s (default 0.5)')
    ap.add_argument('--step', type=float, default=0.2, help='window spacing, s (default 0.2)')
    ap.add_argument('--lag-ms', type=int, default=None, help='flow lag behind the IMU; default: scanned')
    ap.add_argument('--lag-max-ms', type=int, default=300, help='longest flow lag scanned (default 300)')
    ap.add_argument('--lag-quality', type=int, default=0,
                    help='scan the lag only over windows at or above this flow quality, where the flow is informative')
    ap.add_argument('--lag-trace', action='store_true', help='print the correlation at every lag scanned')
    args = ap.parse_args()
    s, armed, msgs = load(args.log)
    if not s['of'].t:
        print('=== %s\nno OF messages, nothing to check' % args.log)
        return 0
    if not s['imu'].t or not s['q'].t:
        print('=== %s\nno IMU or attitude' % args.log)
        return 0
    if args.lag_ms is None:
        b = best_lag(s, armed, args.window, 'flow', 'imu', [x * 1e-3 for x in range(0, args.lag_max_ms + 1, 20)],
                     min_quality=args.lag_quality, trace=args.lag_trace)
        lag = b[0] if b else 0.0
    else:
        lag = args.lag_ms * 1e-3
    has_gps = len(s['gps'].t) > 20
    gps_lag = 0.0
    if has_gps:
        b = best_lag(s, armed, max(args.window, 1.0), 'gps', 'imu', [x * 1e-3 for x in range(0, 401, 50)], lag)
        gps_lag = b[0] if b else 0.0
    ws = windows(s, armed, args.window, args.step, lag, gps_lag)
    print('=== %s' % args.log)
    print('flow lag %d ms%s; %.1f s windows, armed, range good above 0.3 m, tilt under 35 deg'
          % (lag * 1000, (', GPS lag %d ms' % (gps_lag * 1000)) if has_gps else ', no GPS', args.window))
    head = '  %-20s %5s  %-16s   %-16s   %4s' % ('', 'n', 'flow vs IMU', 'EKF vs IMU', 'IMU')
    if has_gps:
        head += '   %-16s   %-16s' % ('GPS vs IMU', 'flow vs GPS')
    print(head)
    print('  %-20s %5s  %-16s   %-16s   %4s' % ('', '', 'slope corr err', 'slope corr err', 'rms'))
    row('all', ws, has_gps)
    for lo, hi in QUALITY_BINS:
        row('quality %d-%d' % (lo, hi - 1), [w for w in ws if lo <= w['q'] < hi], has_gps)
    for lo, hi in HEIGHT_BINS:
        row('height %.1f-%.1f m' % (lo, hi) if hi < 100 else 'height over %.0f m' % lo,
            [w for w in ws if lo <= w['h'] < hi], has_gps)
    spans = []
    for t, txt in msgs:
        if 'too low to recover' in txt:
            spans.append([t, 1e9])
        elif ('flow quality recovered' in txt or 'isarm' in txt) and spans and spans[-1][1] == 1e9:
            spans[-1][1] = t
    if spans:
        inl = [w for w in ws if any(a <= w['t'] <= b for a, b in spans)]
        row('quality latched', inl, has_gps)
        row('not latched', [w for w in ws if not any(a <= w['t'] <= b for a, b in spans)], has_gps)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
