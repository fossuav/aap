#!/usr/bin/env python3
# AP_FLAKE8_CLEAN
"""Replay a whole fleet of flight logs through two builds and say what moved.

replay_sweep.py answers "did this change move the flight that motivated it".
This answers the next question: what else did it move?  A review fix can pass
its own test and the flight it was written for, and still cost another
airframe seconds of bad velocity on a flight nobody thought to replay.  On
SmallFastDrone's refresh16 a drop of a pending flow velocity set passed both,
and only the throw quad's log replayed in a 360-log sweep showed it costing
throws up to 7 s.

    replay_fleet.py find ROOT... > fleet.txt          # logs that carry RFRH
    replay_fleet.py cache fleet.txt ~/replay-cache > local.txt
    cp build/sitl/tool/Replay Replay.before            # per build: the next
    replay_fleet.py run Replay.before local.txt out/before   # build replaces it
    replay_fleet.py run Replay.after local.txt out/after
    replay_fleet.py compare out/before out/after
    replay_fleet.py recover out/before out/after --after "EKF Source Set 2"

run keeps, per log, the replayed cores' XKF1 and XKF5 rows, GPS and MSG, and
the EKF3 lines Replay printed, in OUTDIR/NNNN.pkl, and deletes the BIN, so a
360-log sweep is a few hundred MB rather than tens of GB.  The BIN is read by
a small parser here rather than pymavlink, whose native reader calls exit() at
C level on a malformed FMT record.

Real logs are never copied anywhere but the cache directory you name, and
nothing here quotes their contents; only numbers come back.
"""
import argparse
import bisect
import collections
import concurrent.futures
import hashlib
import json
import math
import os
import pickle
import shutil
import struct
import subprocess
import sys
import tempfile

REPLAY_CORE_OFFSET = 100
HEAD = b'\xa3\x95'
FMT_ID = 128
FMT_LEN = 89
WANT = ('XKF1', 'XKF5', 'GPS', 'MSG')
# DataFlash format characters; 'a' is int16[32]
FMTCH = {'b': 'b', 'B': 'B', 'h': 'h', 'H': 'H', 'i': 'i', 'I': 'I', 'f': 'f', 'd': 'd',
         'n': '4s', 'N': '16s', 'Z': '64s', 'c': 'h', 'C': 'H', 'e': 'i', 'E': 'I',
         'L': 'i', 'M': 'B', 'q': 'q', 'Q': 'Q', 'a': '32h', 'g': 'e'}
SCALE = {'c': 0.01, 'C': 0.01, 'e': 0.01, 'E': 0.01, 'L': 1e-7}
# a log that defines RFRH but logs a handful of frames was flown with LOG_REPLAY off
# and its RFRH records are the format's own announcement, not a replayable stream
RFRH_MIN = 20
SCAN_BYTES = 2 * 1024 * 1024
XKF1_FIELDS = ('Roll', 'Pitch', 'Yaw', 'VN', 'VE', 'VD', 'PN', 'PE', 'PD')
# GPS rows are 5-10 Hz and XKF1 25 Hz; a row further than this from the nearest
# estimate is a gap, not a sample
GPS_MATCH_US = 250000
# below this height above ground the flow innovation times height is noise
FLOW_HAGL_MIN_M = 0.3
# a gap longer than this between XKF5 rows is a gap in fusion, not time spent out
FLOW_GAP_US = 500000


# ---------------------------------------------------------------- find, cache

def scan_rfrh(path):
    """True when the log logs RFRH frames, read from its first 2 MB."""
    try:
        with open(path, 'rb') as f:
            buf = f.read(SCAN_BYTES)
    except OSError:
        return False
    if not buf.startswith(HEAD):
        return False
    i = buf.find(b'RFRH')
    # FMT record: head(2) id(1)=128 type(1) length(1) name(4) ...
    rec = i - 5
    if i < 0 or rec < 0 or buf[rec:rec + 2] != HEAD or buf[rec + 2] != FMT_ID:
        return False
    return buf.count(HEAD + bytes([buf[rec + 3]])) >= RFRH_MIN


def cmd_find(args):
    paths = []
    for root in args.roots:
        for dirpath, _dirs, files in os.walk(root):
            # case-insensitive: some ground stations save .BIN
            paths += [os.path.join(dirpath, f) for f in files if f.lower().endswith('.bin')]
    with concurrent.futures.ThreadPoolExecutor(16) as ex:
        for path, ok in zip(paths, ex.map(scan_rfrh, paths)):
            if ok:
                print(path, flush=True)
    return 0


def read_list(listfile):
    return [line.strip() for line in open(listfile) if line.strip()]


def common_root(logs):
    if len(logs) == 1:
        return os.path.dirname(logs[0])
    return os.path.commonpath(logs)


def cmd_cache(args):
    """Copy the logs to local disk, keeping their paths below the list's common root.

    Replay reads its source a message at a time, and over WSL's 9p mount that
    dominates: one log took 3039 s read from /mnt/c and 2 s from a local copy.
    """
    logs = read_list(args.list)
    root = common_root(logs)
    for log in logs:
        dst = os.path.join(args.dir, os.path.relpath(log, root))
        st = os.stat(log)
        if not (os.path.exists(dst) and os.path.getsize(dst) == st.st_size):
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(log, dst)
        print(dst, flush=True)
    return 0


# ---------------------------------------------------------------- run

def parse_bin(path):
    """The WANT messages from a DataFlash log as row dicts, with the type's own scaling."""
    data = open(path, 'rb').read()
    fmts = {FMT_ID: (FMT_LEN, None, None, None)}
    out = {w: [] for w in WANT}
    i, n = 0, len(data)
    while i + 3 <= n:
        f = fmts.get(data[i + 2]) if data[i] == 0xA3 and data[i + 1] == 0x95 else None
        if f is None:
            j = data.find(HEAD, i + 1)
            if j < 0:
                break
            i = j
            continue
        length = f[0]
        if i + length > n:
            break
        if data[i + 2] == FMT_ID:
            t, ln = data[i + 3], data[i + 4]
            name = data[i + 5:i + 9].rstrip(b'\0').decode('ascii', 'replace')
            fmt = data[i + 9:i + 25].rstrip(b'\0').decode('ascii', 'replace')
            cols = data[i + 25:i + 89].rstrip(b'\0').decode('ascii', 'replace').split(',')
            st = None
            if name in out and 'a' not in fmt:
                try:
                    st = struct.Struct('<' + ''.join(FMTCH[c] for c in fmt))
                except KeyError:
                    pass
            fmts[t] = (ln, name, (fmt, cols), st)
        elif f[3] is not None:
            fmt, cols = f[2]
            row = dict(zip(cols, f[3].unpack_from(data, i + 3)))
            for k, c in zip(cols, fmt):
                if c in SCALE:
                    row[k] *= SCALE[c]
            out[f[1]].append(row)
        i += length
    for name in ('XKF1', 'XKF5'):
        out[name] = [r for r in out[name] if r.get('C', 0) >= REPLAY_CORE_OFFSET]
    return out


def replay_one(job):
    replay, replay_args, idx, log, outdir = job
    dst = os.path.join(outdir, '%04d.pkl' % idx)
    if os.path.exists(dst):
        return idx, 'done'
    d = tempfile.mkdtemp(prefix='replay', dir=outdir)
    try:
        proc = subprocess.run(['nice', '-n', '10', replay] + replay_args + [log], cwd=d,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              universal_newlines=True, errors='replace', timeout=3600)
        logdir = os.path.join(d, 'logs')
        bins = sorted(f for f in os.listdir(logdir) if f.upper().endswith('.BIN')) \
            if os.path.isdir(logdir) else []
        res = {'log': log, 'rc': proc.returncode,
               'ekf': [line for line in proc.stdout.splitlines() if 'EKF3' in line],
               'tail': proc.stdout[-2000:]}
        if bins:
            res.update(parse_bin(os.path.join(logdir, bins[-1])))
        with open(dst + '.tmp', 'wb') as f:
            pickle.dump(res, f)
        os.rename(dst + '.tmp', dst)
        return idx, 'rc=%d xkf1=%d' % (proc.returncode, len(res.get('XKF1', [])))
    except Exception as ex:
        with open(dst, 'wb') as f:
            pickle.dump({'log': log, 'rc': -1, 'error': repr(ex)}, f)
        return idx, 'error ' + repr(ex)
    finally:
        shutil.rmtree(d, ignore_errors=True)


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def cmd_run(args):
    replay = os.path.abspath(args.replay)
    outdir = os.path.abspath(args.outdir)
    logs = [os.path.abspath(p) for p in read_list(args.list)]
    replay_args = [] if args.no_force_ekf3 else ['--force-ekf3']
    for p in args.param:
        replay_args += ['-p', p]
    manifest = {'replay': replay, 'md5': md5(replay), 'args': replay_args, 'logs': logs}
    mpath = os.path.join(outdir, 'manifest.json')
    os.makedirs(outdir, exist_ok=True)
    if os.path.exists(mpath):
        old = json.load(open(mpath))
        if (old['md5'], old['args'], old['logs']) != (manifest['md5'], manifest['args'], manifest['logs']):
            raise SystemExit("%s holds a sweep of another binary, arguments or list; "
                             "use a fresh OUTDIR" % outdir)
    json.dump(manifest, open(mpath, 'w'), indent=1)
    jobs = [(replay, replay_args, i, log, outdir) for i, log in enumerate(logs)]
    with concurrent.futures.ProcessPoolExecutor(args.jobs) as ex:
        for idx, msg in ex.map(replay_one, jobs):
            print('%04d %s' % (idx, msg), flush=True)
    return 0


# ---------------------------------------------------------------- compare

def load_run(outdir):
    mpath = os.path.join(outdir, 'manifest.json')
    if not os.path.exists(mpath):
        raise SystemExit("%s has no manifest.json; it is not a replay_fleet.py run" % outdir)
    m = json.load(open(mpath))
    return m, {log: os.path.join(outdir, '%04d.pkl' % i) for i, log in enumerate(m['logs'])}


def load_pkl(path):
    if not os.path.exists(path):
        return None
    return pickle.load(open(path, 'rb'))


def gps_rows(r):
    return [g for g in r.get('GPS', []) if g.get('Status', 0) >= 3 and g.get('I', 0) == 0]


def gps_vel_err(r, gps):
    """Per replayed core, sorted horizontal velocity errors against a 3D-fix GPS."""
    out = {}
    for c in sorted(set(x['C'] for x in r.get('XKF1', []))):
        rows = [x for x in r['XKF1'] if x['C'] == c]
        ts = [x['TimeUS'] for x in rows]
        errs = []
        for g in gps:
            i = bisect.bisect_left(ts, g['TimeUS'])
            if i >= len(ts) or abs(ts[i] - g['TimeUS']) > GPS_MATCH_US:
                continue
            crs = math.radians(g['GCrs'])
            errs.append(math.hypot(rows[i]['VN'] - g['Spd'] * math.cos(crs),
                                   rows[i]['VE'] - g['Spd'] * math.sin(crs)))
        if errs:
            out[c] = sorted(errs)
    return out


def flow_time_over(r, limit_ms):
    """Per replayed core, seconds the flow disagrees with the state by more than limit_ms.

    XKF5 logs the flow innovation in mrad/s; times the height above ground it is
    the velocity the flow and the state disagree by, which no GPS is needed for.
    """
    out = {}
    for c in sorted(set(x['C'] for x in r.get('XKF5', []))):
        mm = [(x['TimeUS'], math.hypot(x['FIX'], x['FIY']) * 1e-3 * x['HAGL'])
              for x in r['XKF5'] if x['C'] == c and x['HAGL'] > FLOW_HAGL_MIN_M]
        if not any(m for _, m in mm):
            continue
        out[c] = sum((t1 - t0) * 1e-6 for (t0, m0), (t1, _) in zip(mm, mm[1:])
                     if m0 > limit_ms and t1 - t0 < FLOW_GAP_US)
    return out


def xkf1_diff(b, a):
    rb = {(r['TimeUS'], r['C']): r for r in b.get('XKF1', [])}
    ra = {(r['TimeUS'], r['C']): r for r in a.get('XKF1', [])}
    keys = sorted(set(rb) | set(ra))
    first, missing = None, 0
    worst = collections.defaultdict(lambda: [0.0, 0.0, 0.0])
    for k in keys:
        x, y = rb.get(k), ra.get(k)
        if x is None or y is None:
            missing += 1
            first = k[0] if first is None else first
            continue
        if any(x[f] != y[f] for f in XKF1_FIELDS):
            first = k[0] if first is None else first
            w = worst[k[1]]
            w[0] = max(w[0], math.sqrt(sum((x[f] - y[f]) ** 2 for f in ('VN', 'VE', 'VD'))))
            w[1] = max(w[1], math.sqrt(sum((x[f] - y[f]) ** 2 for f in ('PN', 'PE', 'PD'))))
            w[2] = max(w[2], abs((x['Yaw'] - y['Yaw'] + 180) % 360 - 180))
    t0 = keys[0][0] if keys else 0
    return (None if first is None else (first - t0) * 1e-6), dict(worst), missing


def pct(s, p):
    return s[min(len(s) - 1, int(len(s) * p))]


def cmd_compare(args):
    mb, before = load_run(args.before)
    ma, after = load_run(args.after)
    lb, la = os.path.basename(os.path.normpath(args.before)), os.path.basename(os.path.normpath(args.after))
    if mb['md5'] == ma['md5'] and mb['args'] == ma['args']:
        print("NOTE: both runs used the same binary and arguments; nothing should differ")
    logs = [log for log in mb['logs'] if log in after]
    root = common_root(logs) if logs else ''
    only = len(set(before) ^ set(after))
    same, changed, failed = 0, [], []
    for log in logs:
        b, a = load_pkl(before[log]), load_pkl(after[log])
        name = os.path.relpath(log, root)
        if b is None or a is None:
            failed.append((name, 'not run yet'))
            continue
        if b.get('rc') != 0 or a.get('rc') != 0:
            err = b.get('error', '') or a.get('error', '')
            failed.append((name, 'replay exit %s / %s %s' % (b.get('rc'), a.get('rc'), err)))
            continue
        first, worst, missing = xkf1_diff(b, a)
        eb = collections.Counter(line.split('EKF3', 1)[1].strip() for line in b.get('ekf', []))
        ea = collections.Counter(line.split('EKF3', 1)[1].strip() for line in a.get('ekf', []))
        if first is None and eb == ea:
            same += 1
            continue
        changed.append((name, b, a, first, worst, missing, eb - ea, ea - eb))
    print("unchanged %d of %d%s" % (same, same + len(changed) + len(failed),
                                    ("; %d logs in only one run" % only) if only else ""))
    for name, why in failed:
        print("FAILED %s: %s" % (name, why))
    totals = {lb: 0.0, la: 0.0}
    for name, b, a, first, worst, missing, only_b, only_a in changed:
        print("\n%s  first difference %s s%s" % (
            name, '-' if first is None else '%.2f' % first, ("; %d rows in one run only" % missing) if missing else ""))
        for c, w in sorted(worst.items()):
            print("  c%d  max dV %.2f m/s  dP %.2f m  dYaw %.1f deg" % (c, w[0], w[1], w[2]))
        fb, fa = flow_time_over(b, args.limit), flow_time_over(a, args.limit)
        for c in sorted(set(fb) | set(fa)):
            totals[lb] += fb.get(c, 0.0)
            totals[la] += fa.get(c, 0.0)
            print("  c%d  flow more than %.1f m/s out: %s %.1f s, %s %.1f s"
                  % (c, args.limit, lb, fb.get(c, 0.0), la, fa.get(c, 0.0)))
        gps = gps_rows(b)
        if gps:
            gb, ga = gps_vel_err(b, gps), gps_vel_err(a, gps)
            for c in sorted(set(gb) & set(ga)):
                print("  c%d  velocity error to GPS p50/p95/max: %s %.2f/%.2f/%.2f, %s %.2f/%.2f/%.2f" % (
                    c, lb, pct(gb[c], 0.5), pct(gb[c], 0.95), gb[c][-1],
                    la, pct(ga[c], 0.5), pct(ga[c], 0.95), ga[c][-1]))
        if args.detail:
            for m, k in only_b.items():
                print("    %s only x%d: %s" % (lb, k, m))
            for m, k in only_a.items():
                print("    %s only x%d: %s" % (la, k, m))
    if changed:
        print("\nflow more than %.1f m/s out, over the %d changed logs: %s %.1f s, %s %.1f s"
              % (args.limit, len(changed), lb, totals[lb], la, totals[la]))
    return 0


# ---------------------------------------------------------------- recover

def cmd_recover(args):
    """Per occurrence of a statustext, how long each replayed core takes to agree with GPS."""
    runs = [(os.path.basename(os.path.normpath(d)),) + load_run(d) for d in args.runs]
    logs = [log for log in runs[0][1]['logs'] if all(log in r[2] for r in runs)]
    root = common_root(logs) if logs else ''
    window_us = args.window * 1e6
    for log in logs:
        ref = load_pkl(runs[0][2][log])
        if ref is None or not ref.get('MSG'):
            continue
        texts = [(m['TimeUS'], m['Message'].decode(errors='replace') if isinstance(m['Message'], bytes)
                  else m['Message']) for m in ref['MSG']]
        events = [t for t, s in texts if args.after in s]
        gps = gps_rows(ref)
        if not events or not gps:
            continue
        gt = [g['TimeUS'] for g in gps]
        print("%s: %d x \"%s\"" % (os.path.relpath(log, root), len(events), args.after))
        for label, _m, files in runs:
            r = load_pkl(files[log])
            if r is None:
                print("  %-12s not run" % label)
                continue
            cells = []
            for n, ts in enumerate(events):
                per_core = []
                for c in sorted(set(x['C'] for x in r.get('XKF1', []))):
                    errs = []
                    for x in r['XKF1']:
                        if x['C'] != c or not ts <= x['TimeUS'] <= ts + window_us:
                            continue
                        i = bisect.bisect_left(gt, x['TimeUS'])
                        if i >= len(gt) or abs(gt[i] - x['TimeUS']) > GPS_MATCH_US:
                            continue
                        crs = math.radians(gps[i]['GCrs'])
                        errs.append(((x['TimeUS'] - ts) * 1e-6,
                                     math.hypot(x['VN'] - gps[i]['Spd'] * math.cos(crs),
                                                x['VE'] - gps[i]['Spd'] * math.sin(crs))))
                    good = None
                    for k, (t, e) in enumerate(errs):
                        if all(e2 < args.within for t2, e2 in errs[k:] if t2 <= t + args.hold):
                            good = t
                            break
                    per_core.append("c%d %s" % (c, ('%.2fs' % good) if good is not None
                                                else '>%gs' % args.window))
                cells.append("#%d %s" % (n + 1, ' '.join(per_core)))
            print("  %-12s %s" % (label, '  '.join(cells)))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('find', help="print the logs under ROOTs that carry Replay frames (RFRH)")
    p.add_argument('roots', nargs='+')
    p = sub.add_parser('cache', help="copy a list of logs to local disk; prints the new list")
    p.add_argument('list')
    p.add_argument('dir')
    p = sub.add_parser('run', help="replay every log in a list through one Replay binary")
    p.add_argument('replay', help="a Replay binary, copied aside: the next build replaces build/sitl/tool/Replay")
    p.add_argument('list')
    p.add_argument('outdir')
    p.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) // 2))
    p.add_argument('--no-force-ekf3', action='store_true',
                   help="replay with the log's own EKF selection instead of forcing EKF3")
    p.add_argument('--param', action='append', default=[], metavar='NAME=VALUE',
                   help="parameter override passed to Replay (repeatable)")
    p = sub.add_parser('compare', help="what moved between two runs of the same list")
    p.add_argument('before')
    p.add_argument('after')
    p.add_argument('--limit', type=float, default=1.0,
                   help="flow disagreement counted as out, m/s (default 1.0)")
    p.add_argument('--detail', action='store_true', help="list the EKF3 messages only one run printed")
    p = sub.add_parser('recover', help="time to agree with GPS after each occurrence of a statustext")
    p.add_argument('runs', nargs='+', help="run directories; the first supplies the statustexts and GPS")
    p.add_argument('--after', required=True, help="statustext to time from, e.g. 'EKF Source Set 2'")
    p.add_argument('--within', type=float, default=1.0, help="horizontal velocity error, m/s (default 1.0)")
    p.add_argument('--hold', type=float, default=0.5, help="seconds it must stay within (default 0.5)")
    p.add_argument('--window', type=float, default=10.0, help="seconds to look after each (default 10)")
    args = ap.parse_args()
    return {'find': cmd_find, 'cache': cmd_cache, 'run': cmd_run,
            'compare': cmd_compare, 'recover': cmd_recover}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())
