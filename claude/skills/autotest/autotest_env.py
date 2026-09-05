#!/usr/bin/env python3
"""Per-clone autotest environment: where the logs go, and which ports to use.

The autotest harness defaults BUILDLOGS to `../buildlogs`, one level *above*
the repo root, so every sibling clone shares one lock file and one log tree.
It also has no port offset by default, so two runs on one machine fight over
5760/5501/8000 whatever their BUILDLOGS. Between them those two defaults are
why only one autotest can run on a machine at a time.

This module gives each clone its own log tree, and hands a run one of a small
number of port slots, held for the life of the run so two clones cannot pick
the same one. Both `run_autotest.py` and `autotest_results.py` import it so
they agree on where a run's output lives.

A slot is a SITL instance number; SITL moves the default ports it takes from
its command line by 10 per instance (`-I`), and `autotest.py --sitl-instance`
moves the harness's own ports and the multicast ports to match. Slot 0 is instance 0, so a single-session machine behaves
exactly as it always did.
"""
import os
import zlib

# SITL instances a run may use: the vehicle takes the base instance and each
# supplementary peripheral one above it, so this bounds a slot's port range at
# 10 ports per instance.
INSTANCES_PER_SLOT = 4

# Slots offered before a run is refused. Slot n covers TCP 5760+40n..5799+40n.
SLOT_COUNT = 4


def repo_root():
    """The clone this script was installed into.

    Derived from the script's own path rather than the cwd, so the answer does
    not change with where the caller happens to be standing.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "..", ".."))


def buildlogs_dir(root=None):
    """BUILDLOGS for this clone: $BUILDLOGS, else ../buildlogs-<clone name>."""
    env = os.environ.get("BUILDLOGS")
    if env:
        return os.path.normpath(env)
    if root is None:
        root = repo_root()
    return os.path.normpath(
        os.path.join(root, "..", "buildlogs-%s" % os.path.basename(root)))


def autotest_py(root=None):
    """Path to the harness this clone will run."""
    if root is None:
        root = repo_root()
    return os.path.join(root, "Tools", "autotest", "autotest.py")


def supports_sitl_instance(root=None):
    """Whether this clone's autotest.py can be told to move its ports.

    The skill outlives any one checkout: an older branch, a release branch, or
    a clone that predates the option all have an autotest.py without it, and
    passing it there would fail the run outright. Such a clone can still have
    its own log tree and lock - only the ports are stuck at the defaults, which
    is what pins it to slot 0.
    """
    try:
        with open(autotest_py(root)) as f:
            return "--sitl-instance" in f.read()
    except OSError:
        return False


def slot_lock_dir():
    """Where the port-slot locks live - shared by every clone on the machine."""
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(cache, "ardupilot-autotest")


def preferred_slot(root=None):
    """The slot this clone gets when it is free.

    Derived from the clone's path so a given clone keeps the same ports run to
    run, which matters when you want to point MAVProxy at one. crc32 rather
    than hash(): hash() is salted per process.
    """
    if root is None:
        root = repo_root()
    return zlib.crc32(root.encode()) % SLOT_COUNT


def sitl_instance(slot):
    return slot * INSTANCES_PER_SLOT


def base_port(slot):
    """The SITL TCP port a slot's vehicle listens on (SERIAL0)."""
    return 5760 + 10 * sitl_instance(slot)


def port_summary(slot):
    """Human-readable port range for a slot, for the runner to print."""
    off = 10 * sitl_instance(slot)
    return ("SITL %u-%u, rcin %u, spare %u-%u"
            % (5760 + off, 5768 + off, 5501 + off, 8000 + off, 8002 + off))
