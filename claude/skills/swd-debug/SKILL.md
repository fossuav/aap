---
name: swd-debug
description: Flash and debug an MCU over SWD with OpenOCD and GDB via a CMSIS-DAP probe. Use when USB/serial is dead, the board will not enumerate, boot crashes need tracing, or live memory/register inspection is needed. Covers running OpenOCD from WSL against a Windows-side probe.
allowed-tools: Bash, Read, Grep, Glob
---

# Flash and debug over SWD

SWD reaches the target when nothing else does: no USB enumeration, a crash
before the console comes up, or a board physically mounted where nobody can
press a button. It needs no cooperation from the firmware.

This skill is target-agnostic. The board's own documentation supplies the
OpenOCD target config, the flash base address, and the wiring.

## 1. Find OpenOCD

Do not assume a path. Check, in order:

```bash
which openocd
ls -d ~/openocd-pico 2>/dev/null
ls -d /opt/openocd* 2>/dev/null
```

## 2. Running under WSL

**A probe attached to Windows is invisible to WSL.** `/dev/ttyACM*`, `lsusb` and
`/dev/serial` will all show nothing, because WSL2 has no USB unless `usbipd
attach` has been run. That does not mean the probe is absent.

The fix is to run the **Windows** OpenOCD binary through WSL interop: it uses the
Windows USB stack, while you drive it from Linux.

Two things make this work, and both are easy to miss:

- Pass the scripts directory as a **Windows** path, or OpenOCD cannot find its
  own configs and fails with `Can't find interface/<probe>.cfg`. Convert it with
  `wslpath -w`.
- OpenOCD then listens on the Windows side, but WSL reaches those ports on
  `127.0.0.1` (not on the default-gateway address). Confirm before relying on it.

```bash
OOCD=/opt/openocd-<version>-x64-win/openocd.exe     # adjust
SCRIPTS_WIN=$(wslpath -w /opt/openocd-<version>-x64-win/scripts)

cd "$(dirname "$OOCD")"
nohup ./openocd.exe -s "$SCRIPTS_WIN" \
  -c "gdb port 50000" -c "tcl port 50001" -c "telnet port 50002" \
  -f interface/cmsis-dap.cfg \
  -f target/<target>.cfg \
  -c "adapter speed 5000" > /tmp/oocd.log 2>&1 &
```

Newer OpenOCD deprecates `gdb_port`/`tcl_port`/`telnet_port`; use `gdb port` etc.

## 3. Attaching halts the target

Not just `monitor halt` - the attach itself. On a multi-core target it halts
every core. Expect this before connecting to anything you need to keep running:

- A real-time system may not survive being stopped for seconds and resumed. It
  comes back with a large time jump, and on an SMP target one core can be
  halted while holding a lock the other is spinning on.
- If the firmware writes flash, or drives motors, or feeds a watchdog, work out
  what a multi-second stop does to it before you attach, not after.
- A watchdog that is enabled will reset the board while you sit at a prompt.

So: attach to a board you are willing to reboot. If you need measurements from
a running system and cannot afford to disturb it, use a mechanism that needs no
debugger at all - an on-chip sampler the firmware reads out over its own
telemetry, or counters it maintains - and only reach for SWD when the target is
already stopped or expendable.

## 4. Confirm it actually attached

Never assume the launch worked. Read the log:

```bash
grep -E 'Listening on port|DPIDR|processor detected|Examination' /tmp/oocd.log
```

A working attach shows a non-zero DPIDR, one `processor detected` line per core,
and a `Listening on port <gdb>` line. Then check the port from your side:

```bash
timeout 3 bash -c 'echo > /dev/tcp/127.0.0.1/50000' && echo reachable
```

| Symptom | Cause |
|---|---|
| `Error connecting DP: cannot read IDR` | target unpowered - the probe powers itself, the target does not |
| `Can't find interface/....cfg` | scripts path not in the form the binary expects (see WSL note) |
| No probe listed at all | probe not attached to this OS; under WSL that is expected |
| Hung, or stale after a target reset | `pkill -f openocd` and relaunch; it does not always recover |
| Halts again immediately after every `resume` | Often the firmware, not OpenOCD: fault handlers commonly execute `BKPT` only when a debugger is attached, so any fault now stops the core. That is the handler working. Read the fault state (below) rather than fighting it |

## 5. GDB

**Always pass `--nx`.** A user `.gdbinit` will otherwise run against the target
and can halt or reset it before you have looked at anything.

```bash
<toolchain>-gdb --nx build/<board>/bin/<binary> \
  -ex "target extended-remote :50000" \
  -ex "monitor halt"
```

Useful once attached:

```
info threads
bt
info registers
x/16xw <addr>          # raw memory
p <symbol>             # a live global
monitor reset halt     # reset and stop at the vector table
monitor resume
```

To halt without GDB at all, use the telnet port:

```bash
echo halt | timeout 5 nc 127.0.0.1 50002
```

## 6. Flashing

```bash
<openocd> -s "$SCRIPTS_WIN" -f interface/cmsis-dap.cfg -f target/<target>.cfg \
  -c "init" -c "reset halt" \
  -c "flash write_image erase <file>.bin <flash-base>" \
  -c "reset run" -c "shutdown"
```

Confirm the write actually happened. A flashing step that exits 0 having done
nothing is a silent failure, and every measurement taken afterwards is of the
old image: look for the erase/program/verify progress in the output, not just
the exit code.

The flash base is a property of the board and its bootloader layout - take it
from the board's own documentation, never guess it. Writing at the wrong base
can overwrite the bootloader and cost you the only recovery path that does not
need physical access.

## 7. Reading a crashed target

A core stuck in a fault handler looks like a hang. Establish that first, by
sampling the PC a few times: a single unchanging address, or two alternating,
is a spin loop rather than progress.

On Cortex-M the fault registers say why. Read them without halting:

```
CFSR  0xE000ED28   MMFSR/BFSR/UFSR packed: bit 19 NOCP (coprocessor denied,
                   usually an FPU access with CPACR off), 16 UNDEFINSTR,
                   17 INVSTATE, 8 IBUSERR, 9 PRECISERR, 24 UNALIGNED
HFSR  0xE000ED2C   bit 30 FORCED means a lower fault escalated
BFAR  0xE000ED38   faulting address, valid only if CFSR bit 15
MMFAR 0xE000ED34   valid only if CFSR bit 7
```

Better still, look for a fault record the firmware itself saved. Many projects
stash the stacked frame in a `.noinit`/`.noload` section that survives a soft
reset, behind a magic value. Find it in the ELF symbol table, read it, and
check the magic before believing any of it:

```bash
<toolchain>-nm <elf> | grep -i fault_info
```

That gives the faulting PC and LR directly, which beats inferring them - resolve
both through the symbol table to name the function that actually failed.

**Match the ELF to what is flashed.** Symbol addresses move between builds, so
attributing a captured PC with the wrong ELF produces confident nonsense rather
than an obvious error.

## 8. Reading a target that is running

Halting perturbs what you are measuring. For anything timing- or load-related,
prefer a mechanism that samples the running target (a PC sampler, or reading a
counter the firmware maintains) over stopping at a breakpoint. Halt only when
you need exact state.

Know the sampler's blind spot before drawing conclusions from it. A histogram
keyed on exact PCs and truncated to the top N will over-represent small hot
loops, whose samples pile into a handful of addresses, and can miss a large
function entirely, because its samples spread thinly across thousands of
addresses and none of them makes the cut. Absence from the table is not absence
of work. A high drop or eviction count is the signature of exactly that code.
Where the firmware already times the work - a scheduler's per-task statistics,
say - prefer that: it measures the thing directly instead of inferring it.
