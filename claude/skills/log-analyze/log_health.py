#!/usr/bin/env python3
"""Did the autopilot die, or did the vehicle? The structural sweep for a log that stops.

When a log ends mid-flight the first question is whether the FLIGHT CONTROLLER failed --
out of memory, deadlocked, watchdogged -- or whether it simply lost power with the vehicle
still airborne. This gathers everything that bears on that in one pass, so the question gets
answered from evidence rather than from the shape of the ending.

What it reports and why each one matters:

  * TIME BASE. `log_extract.py` normalises timestamps to the first message; pymavlink gives
    raw TimeUS. Confusing the two makes a log look like it has no data in the window you
    asked for. Both are printed.
  * MEMORY over time (PM.Mem). Flat rules out a leak; the crash investigation of 2026-07-19
    turned on 177528 bytes being identical across every sample.
  * INTERNAL ERRORS (PM.InE / ErrL / ErC) and the long-loop count.
  * THREAD STACKS (STAK). Anything under ~15% free is worth a look; a Lua deadlock or a
    scripting overflow shows here.
  * DATAFLASH BUFFER (DSF). If the log buffer was starving, the ending is a logging failure
    rather than a controller failure -- and it also bounds how much data the stop cost you.
  * LAST TIMESTAMP PER TYPE. Every type stopping within a few ms of the others is a whole
    -system stop (power or fault). Slow types trailing off first is a logging problem.
  * The final statustexts.

It deliberately does NOT conclude. A clean sweep plus an abrupt stop while airborne means
power, but "the FC had power" is only provable from a subsequent boot: check for a following
log, for a zero-length crash_dump.bin (no hard fault was captured), and for STAT_BOOTCNT.

Usage:
    log_health.py <log.bin> [--tail N] [--stacks-all]
"""
import argparse
import sys
from collections import defaultdict

from pymavlink import mavutil

# Boot transients: first PM has a huge MaxT, first DSF samples are still filling headers.
SETTLE_S = 10.0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("log")
    ap.add_argument("--tail", type=int, default=12, help="statustexts to show (default 12)")
    ap.add_argument("--stacks-all", action="store_true",
                    help="every thread, not just the tightest")
    a = ap.parse_args()

    mlog = mavutil.mavlink_connection(a.log)
    first = last = None
    last_by_type = {}
    count = defaultdict(int)
    pm, dsf, stak, msgs, parm = [], [], {}, [], {}
    while True:
        m = mlog.recv_match()
        if m is None:
            break
        ty = m.get_type()
        count[ty] += 1
        t = getattr(m, "TimeUS", None)
        if t is not None:
            t /= 1e6
            first = t if first is None else min(first, t)
            last = t if last is None else max(last, t)
            last_by_type[ty] = t
        if ty == "PM":
            pm.append((t, m.Mem, m.MaxT, m.NLon, m.InE, m.ErrL, m.ErC, m.Load))
        elif ty == "DSF":
            dsf.append((t, m.FMn, m.FMx, m.FAv))
        elif ty == "STAK":
            stak[(m.Id, m.Name)] = (m.Total, m.Free, m.Pri)
        elif ty == "MSG":
            msgs.append((t, m.Message))
        elif ty == "PARM" and m.Name.startswith("STAT_"):
            parm.setdefault(m.Name, m.Value)
    if first is None:
        sys.exit("no timestamped messages")

    print(f"{a.log}")
    print(f"  raw TimeUS   {first:.2f} -> {last:.2f} s   ({last - first:.1f} s of data)")
    print(f"  log_extract.py shows these as 0.00 -> {last - first:.2f} "
          f"(it subtracts {first:.2f})")
    if parm:
        print("  " + "  ".join(f"{k}={v:g}" for k, v in sorted(parm.items())))

    # Startup is not steady state: the first PM carries a boot-transient MaxT (hundreds of
    # ms) and the first DSF samples are taken while the buffer is still filling with format
    # headers. Judging the flight on either reports a fault that is not there.
    settle = first + SETTLE_S
    pm_s = [p for p in pm if p[0] > settle] or pm
    dsf_s = [d for d in dsf if d[0] > settle] or dsf

    print(f"\n  MEMORY / SCHEDULER / ERRORS   (ignoring the first {SETTLE_S:.0f} s)")
    if not pm:
        print("    no PM messages")
    else:
        mem = [p[1] for p in pm_s]
        print(f"    free memory  {min(mem):.0f} .. {max(mem):.0f} bytes over {len(pm_s)} "
              f"samples  ({'FLAT - no leak' if max(mem) - min(mem) < 512 else 'VARYING'})")
        print(f"    max loop     {max(p[2] for p in pm_s) / 1000.0:.2f} ms   "
              f"long loops/period up to {max(p[3] for p in pm_s)}   "
              f"load {max(p[7] for p in pm_s) / 10.0:.0f}%")
        ie, el, ec = (max(p[4] for p in pm), max(p[5] for p in pm), max(p[6] for p in pm))
        print(f"    internal err InE={ie}  ErrL={el}  ErC={ec}"
              + ("   <-- NON-ZERO" if (ie or el or ec) else "   (clean)"))
        print(f"    last PM at {pm[-1][0]:.2f} s, {last - pm[-1][0]:.1f} s before the end")

    print(f"\n  DATAFLASH BUFFER   (ignoring the first {SETTLE_S:.0f} s)")
    if not dsf:
        print("    no DSF messages")
    else:
        cap = max(d[2] for d in dsf_s)
        low = min(d[1] for d in dsf_s)
        print(f"    free min {low:.0f}  avg {sum(d[3] for d in dsf_s)/len(dsf_s):.0f}"
              f"  max {cap:.0f} bytes  ({100.0 * low / cap:.0f}% free at worst)")
        print(f"    last DSF at {dsf[-1][0]:.2f} s"
              + ("   (healthy -- an abrupt end is not a logging failure, and at most a"
                 f"\n     fraction of a second of data was pending)"
                 if low > 0.3 * cap else "   <-- BUFFER WAS STARVING"))

    print("\n  THREAD STACKS")
    if not stak:
        print("    no STAK messages")
    else:
        rows = sorted(stak.items(), key=lambda kv: kv[1][1] / max(kv[1][0], 1))
        for (i, name), (tot, free, pri) in (rows if a.stacks_all else rows[:6]):
            pct = 100.0 * free / tot if tot else 0
            print(f"    {name:<12} pri={pri:<4} {free:>5}/{tot:<6} free ({pct:4.1f}%)"
                  + ("   <-- LOW" if pct < 15 else ""))
        if not a.stacks_all:
            print(f"    ... {len(rows) - 6} more (--stacks-all)")

    print("\n  END OF LOG -- last timestamp per type")
    for ty, t in sorted(last_by_type.items(), key=lambda kv: -kv[1])[:8]:
        print(f"    {ty:<8} {t:9.4f}  ({last - t:+.3f} s from the last)")
    spread = last - min(sorted(last_by_type.values(), reverse=True)[:8])
    print(f"    the 8 latest types stop within {spread * 1000:.0f} ms of each other"
          + ("   -- a whole-system stop (power or fault), not a logging fade"
             if spread < 0.2 else "   -- staggered, look at logging"))

    print(f"\n  LAST {a.tail} STATUSTEXTS")
    for t, text in msgs[-a.tail:]:
        print(f"    {t:9.2f}  {text}")


if __name__ == "__main__":
    main()
