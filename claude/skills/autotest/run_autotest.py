#!/usr/bin/env python3
"""Run an ArduPilot SITL autotest under a wall-clock timeout.

Folds the timeout, output streaming, a lock pre-check and per-clone isolation
into one script, so the autotest skill can be granted permission to *this
script* rather than to a blanket `timeout`/`python3`. Arguments after this
script's own options are passed straight through to Tools/autotest/autotest.py.

Usage:
    python3 .claude/skills/autotest/run_autotest.py [options] <autotest.py args...>

Options (must come before the autotest.py arguments):
    --timeout SECONDS   wall-clock bound on the run (default 900)
    --slot N            use port slot N rather than the one this clone prefers
    --buildlogs DIR     write logs and take the harness lock here
    --no-isolate        old behaviour: shared ../buildlogs, no port offset

Examples:
    python3 .claude/skills/autotest/run_autotest.py test.Copter.AltHold
    python3 .claude/skills/autotest/run_autotest.py --timeout 1200 test.Plane.QuadPlane

By default each clone gets its own BUILDLOGS (so its own harness lock and its
own log tree) and one of a few port slots, held for the life of the run. That
is what lets autotests run in two clones at once; see autotest_env.py.

Moving the ports needs `autotest.py --sitl-instance`, which older checkouts do
not have. Against one of those the run still gets its own log tree and lock,
but has to use the default ports, so it is pinned to slot 0 and waits for it.

Exit code is autotest.py's own, 124 on timeout (matching coreutils `timeout`),
or 125 when this clone's lock or every port slot is already taken. That last
one matters: autotest.py exits 0 when it cannot take the lock, so without this
a blocked run is indistinguishable from a passing one.
Build first with /build or ./waf - this script only runs tests.
"""
import os
import signal
import socket
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import autotest_env  # noqa: E402

try:
    import fcntl
except ImportError:
    fcntl = None  # not a POSIX host; nothing to arbitrate with

DEFAULT_TIMEOUT = 900


def lock_is_held(path):
    """True when another process holds autotest.py's lock on path.

    autotest.py takes an fcntl advisory lock and exits 0 when it cannot get it,
    so a caller that only checks the exit code cannot tell a blocked run from a
    passing one. The lock is released when its holder dies, so the file existing
    proves nothing - test-acquire it instead.
    """
    if not os.path.exists(path) or fcntl is None:
        return False
    try:
        f = open(path, "a")
    except OSError:
        return False
    try:
        fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        return True
    else:
        fcntl.lockf(f, fcntl.LOCK_UN)
        return False
    finally:
        f.close()


def lock_slot(slot):
    """Hold the lock on a port slot, or return None if another clone has it.

    The returned file object must stay open for as long as the slot is wanted:
    the lock goes when it closes.
    """
    d = autotest_env.slot_lock_dir()
    os.makedirs(d, exist_ok=True)
    f = open(os.path.join(d, "slot%u.lck" % slot), "a+")
    if fcntl is not None:
        try:
            fcntl.lockf(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            f.close()
            return None
    return f


def take_slot(slot, root):
    """Lock a slot and record who holds it, for the refusal message."""
    f = lock_slot(slot)
    if f is None:
        return None
    f.seek(0)
    f.truncate()
    f.write("%s %u\n" % (root, os.getpid()))
    f.flush()
    return f


def port_is_free(port):
    """True when nothing has the slot's SITL port.

    The slot locks only see runs started through this script. A sim_vehicle, a
    hand-started autotest.py, or a clone still on the old runner is invisible
    to them and would show up only as the run failing partway through, so test
    the port itself before handing the slot out.

    Bound the way SITL binds it - wildcard address, SO_REUSEADDR - so the probe
    answers the question SITL will ask. Without the option a port left in
    TIME_WAIT by the previous run reads as busy for a minute, costing a slot
    that SITL would have taken quite happily.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("0.0.0.0", port))
    except OSError:
        return False
    finally:
        s.close()
    return True


def slot_holder(slot):
    """Which clone last took a slot, from the record left in its lock file."""
    try:
        with open(os.path.join(autotest_env.slot_lock_dir(),
                               "slot%u.lck" % slot)) as f:
            return f.read().split()[0]
    except (OSError, IndexError):
        return "unknown"


def slot_state(slot):
    """Why a slot is unavailable: a run holding it, or something on its port.

    Worth telling apart - the first will clear on its own, the second wants a
    look at what is squatting the port.
    """
    held = lock_slot(slot)
    if held is None:
        return "run in %s" % slot_holder(slot)
    held.close()
    port = autotest_env.base_port(slot)
    if not port_is_free(port):
        return "port %u busy" % port
    return "free"


def acquire_slot(root, wanted=None, slots=None):
    """Take the clone's preferred slot, or the first free one after it."""
    if slots is None:
        slots = list(range(autotest_env.SLOT_COUNT))
    if wanted is not None:
        held = take_slot(wanted, root)
        if held is not None and not port_is_free(autotest_env.base_port(wanted)):
            held.close()
            return wanted, None
        return wanted, held
    first = autotest_env.preferred_slot(root)
    order = sorted(slots, key=lambda s: (s - first) % autotest_env.SLOT_COUNT)
    for slot in order:
        held = take_slot(slot, root)
        if held is None:
            continue
        if port_is_free(autotest_env.base_port(slot)):
            return slot, held
        held.close()
    return None, None


def parse_args(args):
    """Split our own leading options off the autotest.py arguments."""
    opts = {"timeout": DEFAULT_TIMEOUT, "slot": None,
            "buildlogs": None, "isolate": True}
    while args:
        if args[0] == "--timeout":
            if len(args) < 2 or not args[1].isdigit():
                raise ValueError("--timeout needs a number of seconds")
            opts["timeout"] = int(args[1])
            args = args[2:]
        elif args[0] == "--slot":
            if len(args) < 2 or not args[1].isdigit():
                raise ValueError("--slot needs a slot number")
            opts["slot"] = int(args[1])
            if opts["slot"] >= autotest_env.SLOT_COUNT:
                raise ValueError("--slot must be below %u"
                                 % autotest_env.SLOT_COUNT)
            args = args[2:]
        elif args[0] == "--buildlogs":
            if len(args) < 2:
                raise ValueError("--buildlogs needs a directory")
            opts["buildlogs"] = args[1]
            args = args[2:]
        elif args[0] == "--no-isolate":
            opts["isolate"] = False
            args = args[1:]
        else:
            break
    return opts, args


def main():
    try:
        opts, args = parse_args(sys.argv[1:])
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    if not args:
        print(__doc__)
        return 2

    root = autotest_env.repo_root()

    if opts["buildlogs"] is not None:
        buildlogs = os.path.normpath(opts["buildlogs"])
    elif opts["isolate"]:
        buildlogs = autotest_env.buildlogs_dir(root)
    else:
        buildlogs = os.path.normpath(os.path.join(root, "..", "buildlogs"))
    os.makedirs(buildlogs, exist_ok=True)

    lock = os.path.join(buildlogs, "autotest.lck")
    if lock_is_held(lock):
        print("error: another autotest holds %s - nothing was run.\n"
              "       find it with `ps aux | grep -E 'autotest|arducopter'` and wait for it."
              % lock, file=sys.stderr)
        return 125

    can_move_ports = autotest_env.supports_sitl_instance(root)
    if not can_move_ports:
        print("note: this checkout's autotest.py has no --sitl-instance, so the "
              "run must use the default ports (slot 0).", flush=True)
        if opts["slot"] not in (None, 0):
            print("error: --slot %u needs --sitl-instance, which this checkout's "
                  "autotest.py does not have." % opts["slot"], file=sys.stderr)
            return 2
        opts["slot"] = 0

    slot, held = (0, None)
    if opts["isolate"]:
        slots = None if can_move_ports else [0]
        slot, held = acquire_slot(root, opts["slot"], slots)
        if held is None:
            if opts["slot"] is not None:
                print("error: port slot %u unavailable (%s) - nothing was run."
                      % (opts["slot"], slot_state(opts["slot"])), file=sys.stderr)
            else:
                busy = ", ".join("%u: %s" % (s, slot_state(s))
                                 for s in range(autotest_env.SLOT_COUNT))
                print("error: no port slot is free - nothing was run.\n       %s"
                      % busy, file=sys.stderr)
            return 125

    env = dict(os.environ)
    env["BUILDLOGS"] = buildlogs

    instance = autotest_env.sitl_instance(slot)
    cmd = [sys.executable, "Tools/autotest/autotest.py"]
    if instance != 0:
        cmd.extend(["--sitl-instance", str(instance)])
    cmd.extend(args)

    print("BUILDLOGS=%s" % buildlogs, flush=True)
    print("port slot %u (%s)" % (slot, autotest_env.port_summary(slot)), flush=True)
    print("+ %s  (timeout %ds)" % (" ".join(cmd), opts["timeout"]), flush=True)
    # new session so a timeout can signal SITL children too
    proc = subprocess.Popen(cmd, start_new_session=True, env=env, cwd=root)
    try:
        return proc.wait(timeout=opts["timeout"])
    except subprocess.TimeoutExpired:
        print("\nTIMEOUT after %ds - terminating autotest and its SITL children"
              % opts["timeout"], file=sys.stderr)
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
    finally:
        if held is not None:
            held.close()


if __name__ == "__main__":
    sys.exit(main())
