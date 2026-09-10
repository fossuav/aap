#!/usr/bin/env python3
"""Replay real flight logs through the current build and report what changed.

An EKF change that a real flight motivated has to be replayed against that
flight before it is believed.  Doing that by hand costs a run every time and
walks into the same two traps, so both are handled here once:

  * Replay writes its re-run cores at C+100.  C<100 in the output is the
    original flight passed straight through, so reading XKF1 without
    filtering reproduces the flight's own numbers and looks like a result.
  * Reset counts are read from the statustexts Replay emits, which is only
    sound if the source log carries none of its own.  That is checked, and
    said, rather than assumed.

Run it once per tree state and compare the two result files:

    replay_sweep.py --label before --out before.json logA.bin logB.bin
    ... change the code, rebuild ...
    replay_sweep.py --label after --out after.json logA.bin logB.bin
    replay_sweep.py --compare before.json after.json

A log is named by path, or by bare name if AP_LOG_ROOTS is set - the same
roots ardupilot-pr-analysis/find_log.py searches.  Real logs are never copied
or quoted here; only the numbers come back.
"""
import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import time

# statustexts the optical flow recovery emits, and what each one means
EVENTS = {
    'reset': 'flow vel reset',
    'deferred': 'flow recovery deferred',
    'quality': 'too low to recover',
    'unhealthy': 'flow aiding unhealthy',
}

REPLAY_CORE_OFFSET = 100


@contextlib.contextmanager
def quiet_reader():
    """Swallow the DFReader chatter and count it.

    Some of these logs desync the reader part way through ("bad header",
    "Invalid length in FMT message"), which floods stdout and hides the
    result.  It also means records after that point may be lost, so the
    count is reported rather than discarded.
    """
    buf = io.StringIO()
    # DFReader reports a desync on stderr, not stdout
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        errs = []
        yield errs
    errs.append(sum(1 for line in buf.getvalue().splitlines()
                    if 'bad header' in line or 'Invalid length' in line))


TOPDIR = None


def topdir():
    if TOPDIR:
        return os.path.abspath(TOPDIR)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, '..', '..', '..'))


def resolve(name):
    """A path, or a bare log name to find under AP_LOG_ROOTS."""
    if os.path.exists(name):
        return os.path.abspath(name)
    roots = [p for p in os.environ.get('AP_LOG_ROOTS', '').split(':') if p.strip()]
    if not roots:
        raise SystemExit("%s is not a file and AP_LOG_ROOTS is not set" % name)
    hits = []
    for root in roots:
        for dirpath, _dirnames, filenames in os.walk(root):
            if os.path.basename(name) in filenames:
                hits.append(os.path.join(dirpath, os.path.basename(name)))
    if not hits:
        raise SystemExit("no %s under AP_LOG_ROOTS" % name)
    if len(hits) > 1:
        raise SystemExit("%d logs named %s under AP_LOG_ROOTS; pass a path, or "
                         "resolve it with ardupilot-pr-analysis/find_log.py:\n  %s"
                         % (len(hits), name, "\n  ".join(hits)))
    return hits[0]


def scan_source(path):
    """What the source log can and cannot support, read from the log itself."""
    with quiet_reader() as errs:
        out = _scan_source(path)
    return out + (errs[-1],)


def _scan_source(path):
    from pymavlink import mavutil
    mlog = mavutil.mavlink_connection(path)
    replayable = False
    own_events = 0
    while True:
        msg = mlog.recv_match(type=['RFRH', 'MSG'])
        if msg is None:
            break
        if msg.get_type() == 'RFRH':
            replayable = True
            continue
        text = getattr(msg, 'Message', '')
        if any(k in text for k in EVENTS.values()):
            own_events += 1
    return replayable, own_events


def run_replay(logpath, params, progress):
    """Run Replay from topdir and return the BIN it wrote."""
    logdir = os.path.join(topdir(), 'logs')
    before = set(os.listdir(logdir)) if os.path.isdir(logdir) else set()
    cmd = [os.path.join('build', 'sitl', 'tool', 'Replay')]
    for p in params:
        cmd += ['-p', p]
    if progress:
        cmd.append('-P')
    cmd.append(logpath)
    started = time.time()
    proc = subprocess.run(cmd, cwd=topdir(), stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, universal_newlines=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stdout[-4000:] + "\n")
        raise SystemExit("Replay failed on %s (exit %d)" % (logpath, proc.returncode))
    after = set(os.listdir(logdir)) if os.path.isdir(logdir) else set()
    new = sorted(after - before)
    if not new:
        raise SystemExit("Replay wrote no log in %s" % logdir)
    return os.path.join(logdir, new[-1]), time.time() - started, proc.stdout


def count_events(replay_stdout):
    """Count the statustexts the re-run EKF emitted.

    Read from Replay's own output rather than from MSG records in the output
    BIN.  The re-run emits these itself, so nothing the source log carried can
    contaminate the count, and it does not depend on the log reader surviving
    the file.
    """
    events = {k: 0 for k in EVENTS}
    for line in replay_stdout.splitlines():
        if 'TOGCS:' not in line:
            continue
        for key, needle in EVENTS.items():
            if needle in line:
                events[key] += 1
    return events


# Read in a child process: pymavlink's native reader calls exit() at C level on
# a malformed FMT record, which no try/except can catch and which killed a whole
# sweep silently before this was isolated.
PEAK_SCAN = """
import json, math, sys
from pymavlink import mavutil
mlog = mavutil.mavlink_connection(sys.argv[1])
peak, fvc, saw = {}, {}, False
while True:
    m = mlog.recv_match(type=['XKF1', 'XKF7'])
    if m is None:
        break
    c = getattr(m, 'C', None)
    if c is None or c < %d:
        continue
    saw = True
    c -= %d
    if m.get_type() == 'XKF1':
        d = math.hypot(m.PN, m.PE)
        if d > peak.get(c, 0.0):
            peak[c] = d
    else:
        fvc[c] = max(fvc.get(c, 0), m.FVC)
sys.stdout.write(json.dumps({'peak': {str(k): v for k, v in peak.items()},
                             'fvc': {str(k): v for k, v in fvc.items()}, 'saw': saw}))
""" % (REPLAY_CORE_OFFSET, REPLAY_CORE_OFFSET)


def scan_output(path):
    """Peak excursion per re-run core, or None if the reader could not finish."""
    proc = subprocess.run([sys.executable, '-c', PEAK_SCAN, path],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          universal_newlines=True)
    try:
        got = json.loads(proc.stdout)
    except ValueError:
        return None, None, False
    return ({int(k): v for k, v in got['peak'].items()},
            {int(k): v for k, v in got['fvc'].items()}, got['saw'])


def sweep(args):
    results = []
    for name in args.logs:
        path = resolve(name)
        replayable, own_events, src_errs = scan_source(path)
        if not replayable:
            print("%-14s SKIPPED - no RFRH records, flown without LOG_REPLAY" % name)
            results.append({'log': name, 'skipped': 'not replayable'})
            continue
        out, secs, replay_stdout = run_replay(path, args.param, args.progress)
        events = count_events(replay_stdout)
        peak, fvc, saw = scan_output(out)
        if peak is None:
            print("%-14s   NOTE: log reader aborted on the output BIN; peak excursion "
                  "unavailable, counts are unaffected" % name)
            peak, fvc = {}, {}
        elif not saw:
            print("%-14s WARNING - no C>=%d rows; Replay produced no re-run cores"
                  % (name, REPLAY_CORE_OFFSET))
        kept = out
        if args.keep_dir:
            os.makedirs(args.keep_dir, exist_ok=True)
            kept = os.path.join(args.keep_dir, "%s-%s.BIN" % (args.label or 'run', os.path.basename(name)))
            shutil.move(out, kept)
        results.append({
            'log': name,
            'events': events,
            'peak_m': {str(c): round(v, 2) for c, v in sorted(peak.items())},
            'xkf7_fvc': {str(c): v for c, v in sorted(fvc.items())},
            'source_reader_errors': src_errs,
            'output': kept,
            'seconds': round(secs, 1),
        })
        print("%-14s resets=%-3d deferred=%-3d quality=%-3d unhealthy=%-3d peak=%s  (%.0fs)" % (
            name, events['reset'], events['deferred'], events['quality'], events['unhealthy'],
            ", ".join("c%s %.1fm" % (c, v) for c, v in sorted(peak.items())) or "-", secs))
        sys.stdout.flush()   # a sweep is minutes per log; do not sit on the result
        if src_errs:
            print("%-14s   NOTE: %d reader desync records in the source log; it replays, but "
                  "anything read back out of it is partial" % (name, src_errs))
    if args.out:
        with open(args.out, 'w') as f:
            json.dump({'label': args.label, 'results': results}, f, indent=2)
        print("\nwrote %s" % args.out)
    return 0


def compare(before_path, after_path):
    before = json.load(open(before_path))
    after = json.load(open(after_path))
    b = {r['log']: r for r in before['results']}
    print("%-14s %-28s %-28s" % ("log", before.get('label') or 'before', after.get('label') or 'after'))
    for r in after['results']:
        prev = b.get(r['log'])
        if prev is None or 'skipped' in r or 'skipped' in prev:
            print("%-14s %s" % (r['log'], r.get('skipped', 'no baseline')))
            continue
        def fmt(x):
            return "resets=%-3d peak=%s" % (
                x['events']['reset'],
                ", ".join("%.1f" % v for v in x['peak_m'].values()) or "-")
        flag = "" if fmt(prev) == fmt(r) else "   <-- moved"
        print("%-14s %-28s %-28s%s" % (r['log'], fmt(prev), fmt(r), flag))
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('logs', nargs='*', help="log paths, or bare names to find under AP_LOG_ROOTS")
    ap.add_argument('--label', help="name for this tree state, recorded in the result file")
    ap.add_argument('--out', help="write results as JSON here")
    ap.add_argument('--compare', nargs=2, metavar=('BEFORE', 'AFTER'),
                    help="compare two result files instead of running a sweep")
    ap.add_argument('--param', action='append', default=[], metavar='NAME=VALUE',
                    help="parameter override passed to Replay (repeatable)")
    ap.add_argument('--keep-dir', help="move each replayed BIN here instead of leaving it in logs/")
    ap.add_argument('--progress', action='store_true', help="show Replay's own progress")
    ap.add_argument('--build', action='store_true', help="build Replay first")
    ap.add_argument('--topdir', help="ardupilot checkout to replay in (default: this script's own)")
    args = ap.parse_args()

    global TOPDIR
    TOPDIR = args.topdir

    if args.compare:
        return compare(*args.compare)
    if not args.logs:
        ap.error("give at least one log, or --compare")
    if args.build:
        subprocess.run(['./waf', '--targets', 'tool/Replay'], cwd=topdir(), check=True)
    tool = os.path.join(topdir(), 'build', 'sitl', 'tool', 'Replay')
    if not os.path.exists(tool):
        raise SystemExit("no %s - run with --build, or ./waf --targets tool/Replay" % tool)
    return sweep(args)


if __name__ == '__main__':
    sys.exit(main())
