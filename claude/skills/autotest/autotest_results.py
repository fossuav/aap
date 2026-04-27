#!/usr/bin/env python3
"""ArduPilot autotest result extraction for Claude Code.

Parses autotest per-test output files (buildlogs/*.txt) into structured
summaries so we don't need ad-hoc grep / tail / head pipelines on test
output. Read-only — never modifies files.

Usage:
    python3 autotest_results.py summary  [--buildlogs DIR] [--vehicle V]
    python3 autotest_results.py failures [--buildlogs DIR] [--vehicle V]
    python3 autotest_results.py failure  <test_name> [--buildlogs DIR] [--lines N]
    python3 autotest_results.py logs     [--buildlogs DIR]

Default --buildlogs is $BUILDLOGS or ../buildlogs (matching the autotest
harness default — see Tools/autotest/autotest.py:buildlogs_dirpath()).

Per-test files are written by run_one_test_attempt() in vehicle_test_suite.py
and named "<Vehicle>-<TestName>.txt", with retries suffixed "-retry-<N>".
"""

import argparse
import os
import re
import sys
from pathlib import Path


PASSED_RE   = re.compile(r'PASSED:\s+"([^"]+)"')
FAILED_RE   = re.compile(r'FAILED:\s+"([^"]+)":\s*(.*?)\s*(?:\(see\s+(.+?)\))?\s*$')
EXC_HEAD_RE = re.compile(r'Exception caught:')

# Filenames: "ArduCopter-AltHold.txt" or "ArduCopter-AltHold-retry-1.txt"
FILENAME_RE = re.compile(r'^([A-Za-z][A-Za-z0-9_]*)-(.+?)(?:-retry-(\d+))?\.txt$')


def default_buildlogs() -> Path:
    env = os.environ.get('BUILDLOGS')
    if env:
        return Path(env)
    return Path.cwd().parent / 'buildlogs'


def list_test_files(buildlogs: Path, vehicle: str | None = None):
    if not buildlogs.is_dir():
        sys.exit(f"buildlogs directory not found: {buildlogs}")
    files = sorted(buildlogs.glob('*.txt'))
    if vehicle:
        files = [f for f in files if f.stem.startswith(vehicle + '-')]
    return files


def parse_filename(path: Path):
    m = FILENAME_RE.match(path.name)
    if not m:
        return None, None, None
    return m.group(1), m.group(2), int(m.group(3)) if m.group(3) else None


def parse_test_file(path: Path):
    text = path.read_text(errors='replace')
    lines = text.splitlines()

    vehicle, name_from_file, retry = parse_filename(path)
    status = 'unknown'
    name = name_from_file or path.stem
    reason = None
    debug_path = None

    # Pass/fail marker is written near the end of the file by run_one_test_attempt.
    for line in reversed(lines):
        m = FAILED_RE.search(line)
        if m:
            status = 'failed'
            name = m.group(1)
            reason = m.group(2).strip()
            debug_path = m.group(3)
            break
        m = PASSED_RE.search(line)
        if m:
            status = 'passed'
            name = m.group(1)
            break

    # Capture the exception block (from "Exception caught:" forward, capped).
    exception_block = None
    for i, line in enumerate(lines):
        if EXC_HEAD_RE.search(line):
            exception_block = '\n'.join(lines[i:i + 120])
            break

    return {
        'path': path,
        'vehicle': vehicle,
        'retry': retry,
        'status': status,
        'name': name,
        'reason': reason,
        'debug_path': debug_path,
        'exception': exception_block,
    }


def cmd_summary(args):
    bl = Path(args.buildlogs)
    files = list_test_files(bl, args.vehicle)
    if not files:
        print(f"No *.txt files in {bl}", file=sys.stderr)
        sys.exit(1)

    results = [parse_test_file(f) for f in files]
    passed  = [r for r in results if r['status'] == 'passed']
    failed  = [r for r in results if r['status'] == 'failed']
    unknown = [r for r in results if r['status'] == 'unknown']

    print(f"buildlogs: {bl}")
    print(f"total:    {len(results)}")
    print(f"passed:   {len(passed)}")
    print(f"failed:   {len(failed)}")
    if unknown:
        print(f"unknown:  {len(unknown)} (no PASSED/FAILED marker — incomplete or aborted)")
    print()

    if failed:
        print("FAILED:")
        for r in failed:
            tag = f" [retry {r['retry']}]" if r['retry'] else ""
            line = f"  {r['name']}{tag}"
            if r['reason']:
                line += f"  -- {r['reason']}"
            print(line)
        print()

    if unknown:
        print("UNKNOWN (no marker):")
        for r in unknown:
            print(f"  {r['path'].name}")


def cmd_failures(args):
    bl = Path(args.buildlogs)
    files = list_test_files(bl, args.vehicle)
    failures = [r for r in (parse_test_file(f) for f in files) if r['status'] == 'failed']

    if not failures:
        print("No failures.")
        return

    for r in failures:
        print(f"=== {r['name']}{' [retry ' + str(r['retry']) + ']' if r['retry'] else ''} ===")
        print(f"file: {r['path']}")
        if r['reason']:
            print(f"reason: {r['reason']}")
        if r['debug_path']:
            print(f"debug: {r['debug_path']}")
        if r['exception']:
            print()
            print("Exception block (truncated):")
            for line in r['exception'].splitlines()[:60]:
                print(f"  {line}")
        print()


def cmd_failure(args):
    bl = Path(args.buildlogs)
    files = list_test_files(bl)

    matches = []
    for f in files:
        _, name, _ = parse_filename(f)
        if name == args.test:
            matches.append(f)
    if not matches:
        matches = [f for f in files if args.test in f.stem]

    if not matches:
        print(f"No test output matching '{args.test}' in {bl}", file=sys.stderr)
        sys.exit(1)

    for path in matches:
        r = parse_test_file(path)
        print(f"=== {path.name} ===")
        print(f"status: {r['status']}")
        if r['reason']:
            print(f"reason: {r['reason']}")
        print()

        all_lines = path.read_text(errors='replace').splitlines()
        tail = all_lines[-args.lines:]
        print(f"--- last {len(tail)} lines ---")
        for line in tail:
            print(line)

        if r['exception']:
            print()
            print("--- exception block ---")
            for line in r['exception'].splitlines()[:120]:
                print(line)
        print()


def cmd_logs(args):
    bl = Path(args.buildlogs)
    if not bl.is_dir():
        sys.exit(f"buildlogs directory not found: {bl}")

    binlogs = sorted(list(bl.glob('*.BIN')) + list(bl.glob('*.bin')))
    tlogs   = sorted(bl.glob('*.tlog'))

    print(f"buildlogs: {bl}")
    print()
    if binlogs:
        print(f"DataFlash logs ({len(binlogs)}):")
        for f in binlogs:
            print(f"  {f}")
        print()
    if tlogs:
        print(f"MAVLink tlogs ({len(tlogs)}):")
        for f in tlogs:
            print(f"  {f}")
        print()
    if not binlogs and not tlogs:
        print("No .BIN or .tlog files found.")


def main():
    p = argparse.ArgumentParser(
        prog='autotest_results.py',
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--buildlogs', default=str(default_buildlogs()),
                   help="buildlogs directory (default: $BUILDLOGS or ../buildlogs)")
    sub = p.add_subparsers(dest='cmd', required=True)

    s = sub.add_parser('summary', help='pass/fail counts and failing test names')
    s.add_argument('--vehicle', help='filter by vehicle prefix (e.g. ArduCopter)')
    s.set_defaults(func=cmd_summary)

    s = sub.add_parser('failures', help='failing tests with reason and exception block')
    s.add_argument('--vehicle')
    s.set_defaults(func=cmd_failures)

    s = sub.add_parser('failure', help='full failure context for a specific test')
    s.add_argument('test', help='test name (matches filename component)')
    s.add_argument('--lines', type=int, default=100,
                   help='lines of file tail to show (default 100)')
    s.set_defaults(func=cmd_failure)

    s = sub.add_parser('logs', help='list .BIN / .tlog logs in buildlogs')
    s.set_defaults(func=cmd_logs)

    args = p.parse_args()
    args.func(args)


if __name__ == '__main__':
    main()
