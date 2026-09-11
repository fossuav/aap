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

## 3. Confirm it actually attached

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

## 4. GDB

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

## 5. Flashing

```bash
<openocd> -s "$SCRIPTS_WIN" -f interface/cmsis-dap.cfg -f target/<target>.cfg \
  -c "init" -c "reset halt" \
  -c "flash write_image erase <file>.bin <flash-base>" \
  -c "reset run" -c "shutdown"
```

The flash base is a property of the board and its bootloader layout - take it
from the board's own documentation, never guess it. Writing at the wrong base
can overwrite the bootloader and cost you the only recovery path that does not
need physical access.

## 6. Reading a target that is running

Halting perturbs what you are measuring. For anything timing- or load-related,
prefer a mechanism that samples the running target (a PC sampler, or reading a
counter the firmware maintains) over stopping at a breakpoint. Halt only when
you need exact state.
