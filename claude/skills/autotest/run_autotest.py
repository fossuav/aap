#!/usr/bin/env python3
"""Run an ArduPilot SITL autotest under a wall-clock timeout.

Folds the timeout, output streaming, and a lock pre-check into one script, so the
autotest skill can be granted permission to *this script* rather than to a blanket
`timeout`/`python3`. Arguments after the optional --timeout are passed straight
through to Tools/autotest/autotest.py.

Usage:
    python3 .claude/skills/autotest/run_autotest.py [--timeout SECONDS] <autotest.py args...>

Examples:
    python3 .claude/skills/autotest/run_autotest.py test.Copter.AltHold
    python3 .claude/skills/autotest/run_autotest.py --timeout 1200 test.Plane.QuadPlane

Exit code is autotest.py's own, or 124 on timeout (matching coreutils `timeout`).
Build first with /build or ./waf - this script only runs tests.
"""
import os
import signal
import subprocess
import sys

DEFAULT_TIMEOUT = 900


def main():
    args = sys.argv[1:]
    timeout = DEFAULT_TIMEOUT
    if args and args[0] == "--timeout":
        if len(args) < 2 or not args[1].isdigit():
            print("error: --timeout needs a number of seconds", file=sys.stderr)
            return 2
        timeout = int(args[1])
        args = args[2:]
    if not args:
        print(__doc__)
        return 2

    # The lock lives at $BUILDLOGS/autotest.lck (default ../buildlogs, one level
    # above the repo root). A present lock may be a live run in a sibling clone,
    # so warn rather than touch it.
    buildlogs = os.environ.get("BUILDLOGS", os.path.join(os.getcwd(), "..", "buildlogs"))
    lock = os.path.normpath(os.path.join(buildlogs, "autotest.lck"))
    if os.path.exists(lock):
        print("warning: autotest lock present at %s - another run may be active; "
              "check `ps aux | grep -E 'autotest|arducopter'` before clearing it"
              % lock, file=sys.stderr)

    cmd = [sys.executable, "Tools/autotest/autotest.py"] + args
    print("+ %s  (timeout %ds)" % (" ".join(cmd), timeout), flush=True)
    # new session so a timeout can signal SITL children too
    proc = subprocess.Popen(cmd, start_new_session=True)
    try:
        return proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        print("\nTIMEOUT after %ds - terminating autotest and its SITL children"
              % timeout, file=sys.stderr)
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=15)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        return 124
    except KeyboardInterrupt:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except Exception:
            pass
        return 130


if __name__ == "__main__":
    sys.exit(main())
