#!/usr/bin/env python3
"""ArduPilot hwdef PR check helper for Claude Code.

Run from the root of an ArduPilot checkout that has the PR branch checked out
(typically a `git worktree` populated via `gh pr checkout`).

The helper performs the deterministic portion of an hwdef PR review and emits
a markdown report. The /hwdef-check skill is responsible for the heavy
configure step, layering the playbook-driven judgment checks on top, and
posting the final comment.

Usage:
    python3 hwdef_check.py detect  [--base BASE]
    python3 hwdef_check.py files   <Board>
    python3 hwdef_check.py boardid <Board>
    python3 hwdef_check.py hwdef   <Board>
    python3 hwdef_check.py dma     <Board>
    python3 hwdef_check.py commits [--base BASE] [--board BOARD]
    python3 hwdef_check.py all     [--base BASE] [--skip-configure]

`all` runs the full sequence: detect new board(s), check files / board id /
hwdef.dat patterns / commit structure, run ./waf configure, then parse the
generated hwdef.h for DMA allocations. Use `--skip-configure` when the caller
has already run waf separately.

Defaults: --base origin/master (ArduPilot uses master, not main).
Markdown is written to stdout. Exit status is non-zero only on internal
errors (missing files, bad arguments) — finding review issues is not an error.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HWDEF_DIR = Path("libraries/AP_HAL_ChibiOS/hwdef")
BOARD_TYPES = Path("Tools/AP_Bootloader/board_types.txt")
BOOTLOADER_DIR = Path("Tools/bootloaders")
STATE_FILE = Path(".git/hwdef-check-state.json")

REQUIRED_COMMIT_PREFIXES = ("AP_Bootloader", "bootloaders", "AP_HAL_ChibiOS")

# Defines that should NOT appear in hwdef.dat because they only restate the
# default. From AP_HAL_ChibiOS/hwdef CLAUDE.md section 7.7. Each entry maps
# the define name to the value that matches the default (or None for "any
# value is redundant — codebase doesn't consume the symbol").
REDUNDANT_DEFINES = {
    "HAL_HAVE_SAFETY_SWITCH": ("0",  "Already the default when no HAL_GPIO_PIN_SAFETY_IN is defined"),
    "HAL_WITH_RTC_SRAM":      (None, "Not consumed by the codebase"),
    # HAL_WITH_DSP defaults enabled on boards >1MB flash (H7, F7). Setting it
    # to TRUE / 1 / enabled on those boards is redundant; setting FALSE is
    # the legitimate non-default case.
    "HAL_WITH_DSP":           ("TRUE", "Defaults enabled on boards >1MB flash (H7, F7); only set to disable"),
}

# 32-bit timers usable for the system tick. From hwdef CLAUDE.md section 7.2.
VALID_SYSTEM_TIMERS = {"2", "5", "TIM2", "TIM5"}

# Default STM32_ST_USE_TIMER per MCU family when an hwdef does NOT override it.
# Sourced from libraries/AP_HAL_ChibiOS/hwdef/common/stm32*_mcuconf.h.
# Keep in sync with that header set.
DEFAULT_SYSTEM_TIMER = {
    "F1": "2", "F3": "2", "F4": "2", "F7": "2",
    "G4": "2", "L4": "2",
    "H7": "5",
}


# ---------- shell helpers ----------

def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def git(*args):
    proc = run(["git", *args])
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


# ---------- board detection ----------

def detect_new_boards(base):
    out = git("diff", "--name-status", f"{base}...HEAD")
    boards = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0], parts[-1]
        m = re.match(r"^libraries/AP_HAL_ChibiOS/hwdef/([^/]+)/hwdef\.dat$", path)
        if m and status.startswith("A"):
            boards.append(m.group(1))
    return sorted(set(boards))


# ---------- individual checks ----------

def check_files(board):
    issues = []
    bdir = HWDEF_DIR / board
    required = [
        bdir / "hwdef.dat",
        bdir / "hwdef-bl.dat",
        bdir / "README.md",
        BOOTLOADER_DIR / f"{board}_bl.bin",
        BOOTLOADER_DIR / f"{board}_bl.hex",
    ]
    for f in required:
        if not f.exists():
            issues.append(f"Missing required file: `{f}`")
    # ELF file should NOT be committed
    elf = BOOTLOADER_DIR / f"{board}_bl.elf"
    if elf.exists():
        issues.append(f"`{elf}` should not be committed (build artifact only)")
    return issues


def check_board_id(board):
    issues = []
    hwdef = HWDEF_DIR / board / "hwdef.dat"
    if not hwdef.exists():
        return [f"`{hwdef}` not found"]
    text = hwdef.read_text()
    m = re.search(r"^APJ_BOARD_ID\s+(\S+)", text, re.MULTILINE)
    if not m:
        return [f"`{hwdef}`: no APJ_BOARD_ID directive"]

    token = m.group(1)
    if not BOARD_TYPES.exists():
        return [f"`{BOARD_TYPES}` not found — cannot validate APJ_BOARD_ID"]
    bt_lines = BOARD_TYPES.read_text().splitlines()

    if token.isdigit():
        # Numeric ID — should be looked up in board_types.txt
        matches = [l for l in bt_lines if re.match(rf"^\S+\s+{token}\b", l)]
        if not matches:
            issues.append(f"APJ_BOARD_ID `{token}` not registered in `{BOARD_TYPES}`")
        elif len(matches) > 1:
            issues.append(f"APJ_BOARD_ID `{token}` registered to multiple symbols: {matches}")
        # Range check
        try:
            n = int(token)
            if n > 7199 and n < 10000:
                issues.append(f"APJ_BOARD_ID `{token}` is outside the regular range (1000-7199)")
        except ValueError:
            pass
        return issues

    # Symbolic ID — look up its number, then check for collisions.
    pat = re.compile(rf"^{re.escape(token)}\s+(\d+)")
    found = None
    for line in bt_lines:
        m2 = pat.match(line)
        if m2:
            found = m2.group(1)
            break
    if found is None:
        issues.append(f"APJ_BOARD_ID `{token}` not defined in `{BOARD_TYPES}`")
        return issues

    # Check for any other symbol with the same numeric id
    collide = []
    for line in bt_lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == found and parts[0] != token:
            collide.append(parts[0])
    if collide:
        issues.append(f"APJ_BOARD_ID `{token}` (=`{found}`) collides with: {', '.join(collide)}")

    # Range check
    try:
        n = int(found)
        if n > 7199 and n < 10000:
            issues.append(f"APJ_BOARD_ID `{token}` (=`{found}`) is outside the regular range (1000-7199)")
    except ValueError:
        pass
    return issues


def parse_mcu_family(hwdef_text):
    """Return the MCU family token (e.g. 'F7', 'H7') from an MCU line."""
    m = re.search(r"^MCU\s+STM32([A-Z]\d)", hwdef_text, re.MULTILINE)
    return m.group(1) if m else None


def effective_system_timer(hwdef_text):
    """Return the system tick timer in effect for this hwdef.

    Returns a tuple ``(value, source)``: ``source`` is ``"explicit"`` when the
    hwdef sets ``STM32_ST_USE_TIMER`` (with or without ``define`` prefix), or
    ``"default"`` when it falls back to the MCU-family default in
    ``stm32*_mcuconf.h``. Returns ``(None, None)`` when neither can be
    determined.
    """
    m = re.search(r"^(?:define\s+)?STM32_ST_USE_TIMER\s+(\S+)",
                  hwdef_text, re.MULTILINE)
    if m:
        return m.group(1), "explicit"
    fam = parse_mcu_family(hwdef_text)
    if fam and fam in DEFAULT_SYSTEM_TIMER:
        return DEFAULT_SYSTEM_TIMER[fam], "default"
    return None, None


def pwm_timers(hwdef_text):
    """Return the set of timer names used as ``PWM(n)`` outputs."""
    timers = set()
    for line in hwdef_text.splitlines():
        # Strip leading whitespace and comments.
        line = re.sub(r"#.*", "", line).strip()
        if not line:
            continue
        # "P<port><pin> <alt_func> TIMn PWM(...) ..."
        m = re.match(r"^P\S+\s+\S+\s+(TIM\d+)\b.*\bPWM\(", line)
        if m:
            timers.add(m.group(1))
    return timers


def check_hwdef_patterns(board):
    """Static checks against hwdef.dat for things the playbook flags."""
    issues = []
    hwdef = HWDEF_DIR / board / "hwdef.dat"
    bl_hwdef = HWDEF_DIR / board / "hwdef-bl.dat"
    if not hwdef.exists():
        return [f"`{hwdef}` not found"]
    text = hwdef.read_text()
    bl_text = bl_hwdef.read_text() if bl_hwdef.exists() else ""

    # 32-bit system timer (only flags an explicit override to a 16-bit timer;
    # the default is checked separately below).
    m = re.search(r"^(?:define\s+)?STM32_ST_USE_TIMER\s+(\S+)", text, re.MULTILINE)
    if m and m.group(1) not in VALID_SYSTEM_TIMERS:
        issues.append(
            f"`STM32_ST_USE_TIMER {m.group(1)}` is not a 32-bit timer "
            f"— must be TIM2 or TIM5 (see hwdef CLAUDE.md §7.2)"
        )

    # System timer vs PWM conflict.
    st_val, st_source = effective_system_timer(text)
    if st_val and st_val in VALID_SYSTEM_TIMERS:
        st_timer = f"TIM{st_val.replace('TIM', '')}"
        used = pwm_timers(text)
        if st_timer in used:
            if st_source == "default":
                fam = parse_mcu_family(text)
                issues.append(
                    f"`{st_timer}` is used for `PWM(...)` outputs but it is also "
                    f"the {fam} ChibiOS default `STM32_ST_USE_TIMER` "
                    f"(see `stm32*_mcuconf.h`). Set `STM32_ST_USE_TIMER` "
                    f"explicitly in both `hwdef.dat` and `hwdef-bl.dat` to the "
                    f"other 32-bit timer (see hwdef CLAUDE.md §7.2)."
                )
            else:
                issues.append(
                    f"`STM32_ST_USE_TIMER {st_val}` collides with `{st_timer}` "
                    f"PWM assignment(s) — system tick and PWM cannot share a timer."
                )

    # Bootloader timer match (§7.2 — both files must agree when overridden).
    if bl_text:
        m_main = re.search(r"^(?:define\s+)?STM32_ST_USE_TIMER\s+(\S+)", text, re.MULTILINE)
        m_bl   = re.search(r"^(?:define\s+)?STM32_ST_USE_TIMER\s+(\S+)", bl_text, re.MULTILINE)
        main_val = m_main.group(1) if m_main else None
        bl_val   = m_bl.group(1)   if m_bl   else None
        if (main_val or bl_val) and main_val != bl_val:
            issues.append(
                f"`STM32_ST_USE_TIMER` mismatch between `hwdef.dat` "
                f"(`{main_val or '(unset)'}`) and `hwdef-bl.dat` "
                f"(`{bl_val or '(unset)'}`) — they must agree (§7.2)."
            )

    # Redundant defines — value-aware so we don't flag legitimate non-default uses.
    for name, (default_val, why) in REDUNDANT_DEFINES.items():
        for m_def in re.finditer(rf"^define\s+{re.escape(name)}(?:\s+(\S+))?", text, re.MULTILINE):
            value = m_def.group(1)
            if default_val is None or (value is not None and value.upper() == default_val.upper()):
                shown = f" {value}" if value else ""
                issues.append(f"Redundant `define {name}{shown}` — {why}")

    # SERIAL_ORDER natural ordering — SERIALn should map to USARTn / UARTn.
    m = re.search(r"^SERIAL_ORDER\s+(.+)$", text, re.MULTILINE)
    if m:
        entries = m.group(1).split()
        for idx, entry in enumerate(entries):
            if entry in ("EMPTY", "OTG1", "OTG2"):
                continue
            em = re.match(r"^U(S?ART)(\d+)$", entry)
            if not em:
                continue  # not the standard form; skip
            expected_n = int(em.group(2))
            if idx != expected_n:
                issues.append(
                    f"SERIAL_ORDER position {idx} maps to `{entry}` "
                    f"(expected SERIAL{idx} → U(S)ART{idx} per natural-order rule §7.3)"
                )
                break  # one warning is enough; reviewer can sort the rest

    # CS / DRDY pin labels must not start with SPIx_ or I2Cx_ — the parser
    # treats those as alternate-function lookups.
    bad_labels = re.findall(
        r"^\s*P[A-Z]\d+\s+((?:SPI|I2C)\d+_(?:CS|DRDY)\w*)\b",
        text, re.MULTILINE,
    )
    for label in sorted(set(bad_labels)):
        issues.append(
            f"Pin label `{label}` uses peripheral-style prefix — rename to "
            f"`IMUx_CS`/`BARO_CS`/etc (hwdef CLAUDE.md §7.3 SPI)"
        )

    return issues


def check_commits(base, board=None):
    out = git("log", "--pretty=%s", f"{base}..HEAD")
    subjects = [l for l in out.splitlines() if l.strip()]
    issues = []
    prefixes = []
    for s in subjects:
        m = re.match(r"^([A-Za-z][A-Za-z0-9_]*)\s*:", s)
        prefixes.append(m.group(1) if m else None)

    seen = {p for p in prefixes if p}
    missing = [p for p in REQUIRED_COMMIT_PREFIXES if p not in seen]
    if missing:
        issues.append(
            "Commit structure: a new-board PR is expected to ship as separate "
            f"per-subsystem commits prefixed `{'`, `'.join(REQUIRED_COMMIT_PREFIXES)}` "
            f"(missing: `{'`, `'.join(missing)}`). Observed subjects: "
            + "; ".join(f"`{s}`" for s in subjects)
        )

    unprefixed = [s for s, p in zip(subjects, prefixes) if p is None]
    if unprefixed:
        issues.append(
            "Commit subjects without a subsystem prefix: "
            + ", ".join(f"`{s}`" for s in unprefixed)
        )
    return issues


# ---------- DMA parsing (post-configure) ----------

DMA_NO_RE = re.compile(r"//.*\bNO\s*DMA\b", re.IGNORECASE)
DMA_SHARE_RE = re.compile(r"//.*\bSHARED\b", re.IGNORECASE)
# Lines listing peripheral DMA, e.g. "// USART1_RX  DMA1 stream 5  channel 4"
DMA_LIST_RE = re.compile(r"//\s*([A-Z][A-Z0-9_]+(?:_(?:TX|RX))?)\s+(.*)$")

CRITICAL_PERIPHS_RE = re.compile(
    r"^(USART\d+_RX|UART\d+_RX|TIM\d+_(UP|CH\d+)|SDMMC\d+)$"
)


def parse_dma_section(hwdef_h):
    """Extract the peripheral DMA comment block from build/<Board>/hwdef.h."""
    if not hwdef_h.exists():
        return None, [f"`{hwdef_h}` missing — was `./waf configure` run?"]
    lines = hwdef_h.read_text(errors="replace").splitlines()

    no_dma = []
    shared = []
    for i, line in enumerate(lines):
        if DMA_NO_RE.search(line):
            no_dma.append(line.strip())
        elif DMA_SHARE_RE.search(line):
            shared.append(line.strip())
    return (no_dma, shared), []


def check_dma(board):
    hwdef_h = Path("build") / board / "hwdef.h"
    parsed, errors = parse_dma_section(hwdef_h)
    if errors:
        return errors
    no_dma, shared = parsed

    issues = []
    if no_dma:
        crit = [l for l in no_dma if any(
            re.search(p, l) for p in (
                r"\bUSART\d+_RX\b", r"\bUART\d+_RX\b",
                r"\bSDMMC", r"\bTIM\d+_CH\d+\b",
            )
        )]
        if crit:
            issues.append("Critical peripherals running without DMA — verify each is not RC input, GPS at high baud, HD VTX, SDMMC, or a DShot motor timer:")
            for l in crit[:30]:
                issues.append(f"  - {l}")
        non_crit = [l for l in no_dma if l not in crit]
        if non_crit:
            issues.append(f"Additional peripherals without DMA ({len(non_crit)} — usually acceptable for telemetry / I2C / NODMA-tagged ports):")
            for l in non_crit[:10]:
                issues.append(f"  - {l}")
            if len(non_crit) > 10:
                issues.append(f"  ... and {len(non_crit) - 10} more")
    if shared:
        issues.append(f"Peripherals sharing DMA streams ({len(shared)}) — review for contention on time-critical paths:")
        for l in shared[:20]:
            issues.append(f"  - {l}")
    return issues


def run_waf_configure(board):
    """Run ./waf configure --board <board>. Returns (success, combined_output)."""
    if not Path("waf").exists():
        return False, "./waf not found in current directory"
    proc = subprocess.run(
        ["./waf", "configure", "--board", board],
        capture_output=True, text=True,
    )
    return proc.returncode == 0, proc.stdout + proc.stderr


# ---------- markdown output ----------

def section(title, issues, ok_msg="No issues found."):
    print(f"### {title}")
    print()
    if issues:
        for it in issues:
            if it.startswith("  "):
                print(it)
            else:
                print(f"- {it}")
    else:
        print(ok_msg)
    print()


# ---------- subcommands ----------

def cmd_detect(args):
    boards = detect_new_boards(args.base)
    if not boards:
        print(f"No new hwdef boards added between `{args.base}` and HEAD.")
        return 0
    print("New boards added in this branch:")
    for b in boards:
        print(f"- {b}")
    return 0


def cmd_files(args):
    section(f"Required files for `{args.board}`", check_files(args.board))


def cmd_boardid(args):
    section(f"APJ_BOARD_ID for `{args.board}`", check_board_id(args.board))


def cmd_hwdef(args):
    section(f"hwdef.dat patterns for `{args.board}`", check_hwdef_patterns(args.board))


def cmd_dma(args):
    section(f"DMA allocation for `{args.board}`", check_dma(args.board))


def cmd_commits(args):
    section("Commit structure", check_commits(args.base, args.board))


# ---------- in-place PR checkout state machine ----------

def _current_ref():
    """Return (ref, is_detached). ``ref`` is the branch name when on a branch,
    or the HEAD SHA when detached."""
    proc = run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if proc.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {proc.stderr.strip()}")
    name = proc.stdout.strip()
    if name == "HEAD":
        sha = git("rev-parse", "HEAD").strip()
        return sha, True
    return name, False


def _in_progress_op():
    """Return a label for any in-progress git operation, else None."""
    git_dir = Path(".git")
    for d in ("rebase-merge", "rebase-apply"):
        if (git_dir / d).is_dir():
            return f"rebase (.git/{d})"
    for f, label in (("MERGE_HEAD", "merge"),
                     ("CHERRY_PICK_HEAD", "cherry-pick"),
                     ("REVERT_HEAD", "revert"),
                     ("BISECT_LOG", "bisect")):
        if (git_dir / f).exists():
            return label
    return None


def _has_tracked_changes():
    """True iff the working tree has staged/unstaged changes to tracked files.
    Deliberately ignores untracked files so that .claude/ (the skill's own
    install root) is not swept up by a stash."""
    out = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        text=True,
    )
    return bool(out.strip())


def cmd_prepare(args):
    if not Path(".git").exists():
        sys.exit("Not in a git repository root.")

    if STATE_FILE.exists():
        prev = json.loads(STATE_FILE.read_text())
        sys.exit(
            f"hwdef-check is already in progress for PR {prev['pr']} "
            f"(branch `{prev['pr_branch']}`). Run "
            f"`python3 .claude/skills/hwdef-check/hwdef_check.py restore` first."
        )

    op = _in_progress_op()
    if op:
        sys.exit(f"Refusing to proceed: {op} in progress. Resolve it first.")

    original_ref, is_detached = _current_ref()

    stashed = False
    if _has_tracked_changes():
        msg = f"hwdef-check: auto-stash for PR {args.pr}"
        proc = run(["git", "stash", "push", "-m", msg])
        if proc.returncode != 0:
            sys.exit(f"git stash push failed: {proc.stderr.strip()}")
        stashed = True

    pr_branch = f"hwdef-check-pr{args.pr}"
    gh_cmd = ["gh", "pr", "checkout", str(args.pr), "--branch", pr_branch]
    if args.repo:
        gh_cmd += ["--repo", args.repo]
    proc = subprocess.run(gh_cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        # Roll back the stash so the user is left where they started.
        if stashed:
            subprocess.run(["git", "stash", "pop"], capture_output=True, text=True)
        sys.exit(
            "gh pr checkout failed — leaving working tree as it was.\n"
            f"  cmd: {' '.join(gh_cmd)}\n"
            f"  stderr: {proc.stderr.strip()}"
        )

    STATE_FILE.write_text(json.dumps({
        "pr":           args.pr,
        "original_ref": original_ref,
        "is_detached":  is_detached,
        "pr_branch":    pr_branch,
        "stashed":      stashed,
    }, indent=2))

    print(f"Prepared review of PR {args.pr}")
    print(f"  Original ref: {original_ref}{' (detached)' if is_detached else ''}")
    print(f"  PR branch:    {pr_branch}")
    if stashed:
        print(f"  Stashed tracked changes (will be popped by `restore`)")
    print()
    print(f"State written to {STATE_FILE}.")
    print(f"When done, run `python3 .claude/skills/hwdef-check/hwdef_check.py restore`.")


def cmd_restore(args):
    if not STATE_FILE.exists():
        print("No hwdef-check state file — nothing to restore.")
        return 0
    state = json.loads(STATE_FILE.read_text())

    # 1. Checkout the original ref.
    proc = run(["git", "checkout", state["original_ref"]])
    if proc.returncode != 0:
        print(f"git checkout {state['original_ref']} failed:")
        print(f"  {proc.stderr.strip()}")
        print()
        print(f"State file kept at `{STATE_FILE}` — fix the working tree (likely")
        print(f"uncommitted changes blocking the switch) and re-run `restore`.")
        return 1
    print(f"Restored ref: {state['original_ref']}"
          f"{' (detached)' if state.get('is_detached') else ''}")

    # 2. Delete the PR branch (best effort).
    pr_branch = state["pr_branch"]
    proc = run(["git", "branch", "-D", pr_branch])
    if proc.returncode == 0:
        print(f"Deleted branch: {pr_branch}")
    elif "not found" in proc.stderr.lower() or "did not match" in proc.stderr.lower():
        pass  # branch already gone, nothing to clean
    else:
        print(f"Warning: could not delete {pr_branch}: {proc.stderr.strip()}")

    # 3. Pop the stash, if we made one.
    if state.get("stashed"):
        proc = run(["git", "stash", "pop"])
        if proc.returncode != 0:
            print("git stash pop failed (likely a merge conflict):")
            print(f"  {proc.stderr.strip()}")
            print("Your stashed changes are still in `git stash list` — resolve by hand.")
            # Don't delete the state file; the user may want to know what we did.
            return 1
        print("Popped auto-stash (tracked changes restored)")

    STATE_FILE.unlink()
    print("hwdef-check state cleared.")
    return 0


def cmd_all(args):
    boards = detect_new_boards(args.base)
    if not boards:
        print(f"No new hwdef boards added between `{args.base}` and HEAD — nothing to check.")
        print()
        print("If the PR modifies an existing board rather than adding a new one, run individual subcommands by board name.")
        return 0

    print(f"# Automated hwdef PR review")
    print()
    print(f"Detected new boards: {', '.join(f'`{b}`' for b in boards)}  ")
    print(f"Base: `{args.base}`")
    print()

    section("Commit structure", check_commits(args.base))

    for board in boards:
        print(f"## Board: `{board}`")
        print()
        section("Required files",         check_files(board))
        section("APJ_BOARD_ID",           check_board_id(board))
        section("hwdef.dat patterns",     check_hwdef_patterns(board))

        if args.skip_configure:
            print(f"### Build configure")
            print()
            print(f"Skipped (`--skip-configure`). Assuming `build/{board}/hwdef.h` is present from a prior run.")
            print()
        else:
            print(f"### Build configure")
            print()
            ok, out = run_waf_configure(board)
            if ok:
                print(f"`./waf configure --board {board}` succeeded.")
            else:
                print(f"`./waf configure --board {board}` **FAILED** — fix this before proceeding. Output (tail):")
                print()
                print("```")
                for line in out.splitlines()[-40:]:
                    print(line)
                print("```")
            print()

        section("DMA allocation",         check_dma(board))

    return 0


# ---------- main ----------

def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("detect", help="list new boards added vs --base")
    s.add_argument("--base", default="origin/master")
    s.set_defaults(func=cmd_detect)

    s = sub.add_parser("files", help="check required files for a board")
    s.add_argument("board")
    s.set_defaults(func=cmd_files)

    s = sub.add_parser("boardid", help="check APJ_BOARD_ID uniqueness")
    s.add_argument("board")
    s.set_defaults(func=cmd_boardid)

    s = sub.add_parser("hwdef", help="static hwdef.dat pattern checks")
    s.add_argument("board")
    s.set_defaults(func=cmd_hwdef)

    s = sub.add_parser("dma", help="parse build/<Board>/hwdef.h for DMA issues")
    s.add_argument("board")
    s.set_defaults(func=cmd_dma)

    s = sub.add_parser("commits", help="check commit structure (per-subsystem)")
    s.add_argument("--base", default="origin/master")
    s.add_argument("--board")
    s.set_defaults(func=cmd_commits)

    s = sub.add_parser("all", help="run the full sequence and emit markdown")
    s.add_argument("--base", default="origin/master")
    s.add_argument("--skip-configure", action="store_true",
                   help="skip ./waf configure (use when caller has already run it)")
    s.set_defaults(func=cmd_all)

    s = sub.add_parser("prepare",
                       help="stash + check out a PR branch into the current repo")
    s.add_argument("--pr", type=int, required=True,
                   help="PR number to fetch and switch to")
    s.add_argument("--repo",
                   help="<owner>/<repo>; defaults to gh's auto-detected remote")
    s.set_defaults(func=cmd_prepare)

    s = sub.add_parser("restore",
                       help="undo `prepare`: switch back to the saved ref and pop the stash")
    s.set_defaults(func=cmd_restore)

    args = p.parse_args()
    sys.exit(args.func(args) or 0)


if __name__ == "__main__":
    main()
