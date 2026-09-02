#!/usr/bin/env python3
"""
Pre-submission PR review helper for the /pr-review skill.

The review workflow this supports is adapted from Andrew Tridgell's /reviewprs
dev-call command:

    https://github.com/tridge/junkcode/tree/master/AI/claude/reviewprs

The dual-reviewer pipeline, the head-hash skip, the detached-pool-with-sentinel
handling of parallel codex agents, and most of the review rules stated in
SKILL.md come from there. The code in this file is an independent
implementation of that design rather than a port of it.

Folds the deterministic half of an ArduPilot PR review into one process:
working out what the PR actually changes, running the mechanical checks a
reviewer bounces PRs for, and driving a parallel `codex exec` pool as an
independent second reviewer.

Subcommands:
  scope   - resolve base/head, commits, files, diffstat
  checks  - run the mechanical gate over the diff
  codex   - run (detached) or poll a pool of `codex exec` reviewers
  state   - record/compare the head a review was completed at

Everything here is read-only with respect to the working tree. The one thing
it writes outside its own scratch directory is the state file under .git/.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time

# ---------------------------------------------------------------- git plumbing


class GitError(RuntimeError):
    pass


def git(*args, check=True):
    """Run a git command in the repo root and return its stdout."""
    proc = subprocess.run(
        ("git",) + args, capture_output=True, text=True, cwd=REPO_ROOT
    )
    if check and proc.returncode != 0:
        raise GitError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def git_ok(*args):
    """True when the git command succeeds."""
    return subprocess.run(
        ("git",) + args, capture_output=True, text=True, cwd=REPO_ROOT
    ).returncode == 0


def refresh_remote_ref(ref):
    """Fetch a remote-tracking ref so the merge-base is against today's base.

    A day-stale upstream/master turned a 16-file PR into a 69-file gate run
    with findings on commits that were not the author's. Best effort: offline
    or slow remotes leave the local ref as it is.
    """
    remote, sep, branch = ref.partition("/")
    if not sep or remote not in git("remote").split():
        return
    try:
        subprocess.run(
            ("git", "fetch", "--quiet", remote, branch),
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=60,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass


def find_repo_root():
    proc = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if proc.returncode != 0:
        sys.exit("error: not inside a git repository")
    return proc.stdout.strip()


REPO_ROOT = find_repo_root()


def gh(*args, check=True):
    """Run a gh command and return stdout.

    With check=True a failure raises rather than returning empty. An API call
    that fails silently is indistinguishable from a genuine "nothing there",
    and that turns a broken fetch into a confident wrong answer - "no review
    comments" when the truth is "could not ask".
    """
    if not shutil.which("gh"):
        if check:
            raise GitError("gh CLI not found on PATH")
        return ""
    proc = subprocess.run(
        ("gh",) + args, capture_output=True, text=True, cwd=REPO_ROOT
    )
    if proc.returncode != 0:
        if check:
            raise GitError("gh %s failed (rc=%d): %s"
                           % (" ".join(args[:3]), proc.returncode,
                              proc.stderr.strip()[:200]))
        return ""
    return proc.stdout


# ------------------------------------------------------------ subsystem naming

# Directory -> commit-message prefix, from the Commit Conventions section of
# the playbook. Longest prefix wins, so the Tools/ special cases are checked
# before the generic Tools/<sub> rule.
_EXPLICIT_PREFIX = {
    "ArduCopter": "Copter",
    "ArduPlane": "Plane",
    "Rover": "Rover",
    "ArduSub": "Sub",
    "AntennaTracker": "AntennaTracker",
    "Blimp": "Blimp",
    "Tools/scripts": "scripts",
    "Tools/ardupilotwaf": "ardupilotwaf",
    "Tools/AP_Bootloader": "AP_Bootloader",
    "Tools/bootloaders": "bootloaders",
    "Tools/autotest": "autotest",
    "Tools/AP_Periph": "AP_Periph",
    "Tools/Frame_params": "Frame_params",
    "Tools/CodeStyle": "CodeStyle",
    ".github": "github-actions",
    "Docs": "Docs",
}


def subsystem_of(path):
    """Return the commit prefix a file belongs under, or None if unclassified."""
    parts = path.split("/")
    if parts[0] == "libraries" and len(parts) > 1:
        # hwdef board directories all belong to AP_HAL_ChibiOS
        return parts[1]
    for prefix, name in _EXPLICIT_PREFIX.items():
        pre = prefix.split("/")
        if parts[: len(pre)] == pre:
            return name
    if parts[0] == "Tools" and len(parts) > 1:
        return parts[1]
    if parts[0] == "modules":
        # A submodule pointer bump is prefixed with the submodule's own name
        # ("ChibiOS: kernel v9"), not with "modules".
        return parts[1] if len(parts) > 1 else "modules"
    if len(parts) == 1:
        # Top-level files (wscript, README, design notes) have no established
        # prefix. Claiming one would invent a rule the project does not have.
        return None
    return parts[0]


# Prefixes upstream uses interchangeably for a subsystem. Measured against
# ArduPilot master, not assumed: hwdef changes carry "AP_HAL_ChibiOS:" (1159),
# "HAL_ChibiOS:" (1005) and "hwdef:" (667) in roughly comparable numbers, so
# treating any of them as wrong is a false positive.
PREFIX_ALIASES = {
    "AP_HAL_ChibiOS": {"AP_HAL_ChibiOS", "HAL_ChibiOS", "AP_HAL_Chibios", "hwdef"},
}


def acceptable_prefixes(subsystem):
    """Prefixes that are legitimate for a subsystem."""
    return PREFIX_ALIASES.get(subsystem, {subsystem})


_PREFIX_HISTORY = {}


def upstream_uses_prefix(prefix, path, base_ref, threshold=3):
    """True when the base branch's own history uses this prefix for this path.

    The alias table above cannot know every local convention, so before
    reporting a prefix as wrong, ask the repository. A prefix the project has
    used repeatedly for these files is the project's practice, whatever the
    playbook says, and reporting it wastes the author's time.
    """
    directory = os.path.dirname(path) or "."
    key = (prefix, directory)
    if key in _PREFIX_HISTORY:
        return _PREFIX_HISTORY[key]
    try:
        subjects = git("log", base_ref, "-400", "--format=%s", "--", directory,
                       check=False).split("\n")
    except GitError:
        subjects = []
    hits = sum(1 for s in subjects if s.startswith(prefix + ":"))
    _PREFIX_HISTORY[key] = hits >= threshold
    return _PREFIX_HISTORY[key]


# ------------------------------------------------------------------ diff model


_HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@")

CXX_SUFFIXES = (".cpp", ".h", ".hpp", ".cc", ".c", ".inc")


def added_lines(rev_range, paths=None):
    """Yield (path, lineno, text) for every added line in the range."""
    args = ["diff", "-U0", "--no-color", "--no-ext-diff", rev_range]
    if paths:
        args += ["--"] + list(paths)
    path = None
    lineno = 0
    for line in git(*args).split("\n"):
        if line.startswith("+++ "):
            p = line[4:].strip()
            path = None if p == "/dev/null" else re.sub(r"^b/", "", p)
        elif line.startswith("@@"):
            m = _HUNK.match(line)
            if m:
                lineno = int(m.group(1))
        elif line.startswith("+") and not line.startswith("+++"):
            if path:
                yield path, lineno, line[1:]
            lineno += 1
        # -U0 emits no context lines, and '-'/'\' lines do not advance lineno


def changed_files(rev_range):
    """Return [{path, status, added, deleted}] for the range."""
    status = {}
    for line in git("diff", "--name-status", "--no-renames", rev_range).split("\n"):
        if not line.strip():
            continue
        bits = line.split("\t")
        status[bits[-1]] = bits[0]
    out = []
    for line in git("diff", "--numstat", "--no-renames", rev_range).split("\n"):
        if not line.strip():
            continue
        add, dele, path = line.split("\t", 2)
        out.append({
            "path": path,
            "status": status.get(path, "M"),
            "added": None if add == "-" else int(add),
            "deleted": None if dele == "-" else int(dele),
        })
    return out


# -------------------------------------------------------------------- scoping


def resolve_base(explicit=None, pr=None):
    """Pick the ref the PR is against. Returns (base_ref, merge_base_sha)."""
    candidates = []
    if explicit:
        candidates.append(explicit)
    if pr and pr.get("baseRefName"):
        base = pr["baseRefName"]
        candidates += ["upstream/" + base, "origin/" + base, base]
    candidates += ["upstream/master", "origin/master", "master"]
    for ref in candidates:
        if git_ok("rev-parse", "--verify", "--quiet", ref + "^{commit}"):
            refresh_remote_ref(ref)
            mb = git("merge-base", ref, "HEAD").strip()
            if mb:
                return ref, mb
    raise GitError(
        "cannot resolve a base ref (tried %s) - pass --base" % ", ".join(candidates)
    )


def lookup_pr(target):
    """Return PR metadata dict for a number/URL/branch, or None."""
    fields = "number,title,url,state,baseRefName,headRefName,headRefOid,isDraft,body,author"
    args = ["pr", "view"]
    repo = None
    if target:
        m = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/(\d+)", target)
        if m:
            repo, target = m.group(1), m.group(2)
        args.append(target)
    args += ["--json", fields]
    if repo:
        args += ["--repo", repo]
    out = gh(*args, check=False)
    if not out.strip():
        return None
    try:
        pr = json.loads(out)
    except json.JSONDecodeError:
        return None
    if repo:
        pr["repo"] = repo
    return pr


def commit_records(rev_range):
    """Return [{sha, short, subject, body, parents, files, subsystems}]."""
    sep = "\x1e"
    fmt = sep.join(["%H", "%h", "%s", "%P", "%an", "%ae", "%B"]) + "\x1d"
    raw = git("log", "--reverse", "--format=" + fmt, rev_range)
    records = []
    for chunk in raw.split("\x1d"):
        chunk = chunk.strip("\n")
        if not chunk.strip():
            continue
        sha, short, subject, parents, an, ae, body = chunk.split(sep, 6)
        files = [
            f for f in git("show", "--pretty=", "--name-only", "--no-renames", sha)
            .split("\n") if f.strip()
        ]
        subs = sorted({subsystem_of(f) for f in files if subsystem_of(f)})
        records.append({
            "sha": sha, "short": short, "subject": subject, "body": body,
            "parents": parents.split(), "author": an, "email": ae,
            "files": files, "subsystems": subs,
        })
    return records


def build_scope(args):
    pr = lookup_pr(args.target) if (args.target or args.pr) else lookup_pr(None)
    base_ref, merge_base = resolve_base(args.base, pr)
    head = git("rev-parse", "HEAD").strip()
    rev_range = "%s..HEAD" % merge_base
    files = changed_files(rev_range)
    commits = commit_records(rev_range)
    porcelain = git("status", "--porcelain").split("\n")
    dirty = [
        s[3:] for s in porcelain if s.strip() and not s.startswith("??")
    ]
    untracked = len([s for s in porcelain if s.startswith("??")])
    # A PR target names metadata; the diff always comes from the local HEAD.
    # If they are not the same commit, every finding below is scoped to code
    # that is not what the PR contains, so say so rather than quietly mixing
    # one PR's title with another branch's diff.
    warnings = []
    if pr and pr.get("headRefOid") and pr["headRefOid"] != head:
        warnings.append(
            "PR #%s is at %s but the checkout is at %s - the review below covers "
            "the LOCAL branch, not the PR. Check the PR out first "
            "(gh pr checkout %s) if you meant to review it."
            % (pr.get("number"), pr["headRefOid"][:10], head[:10], pr.get("number")))
    return {
        "repo_root": REPO_ROOT,
        "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
        "warnings": warnings,
        "head": head,
        "head_short": head[:10],
        "base_ref": base_ref,
        "merge_base": merge_base,
        "rev_range": rev_range,
        "pr": pr,
        "dirty": dirty,
        "untracked": untracked,
        "commits": [
            {k: c[k] for k in ("short", "subject", "files", "subsystems", "author")}
            for c in commits
        ],
        "files": files,
        "totals": {
            "files": len(files),
            "added": sum(f["added"] or 0 for f in files),
            "deleted": sum(f["deleted"] or 0 for f in files),
            "commits": len(commits),
        },
        "subsystems": sorted({s for c in commits for s in c["subsystems"]}),
    }


# --------------------------------------------------------------- mechanical gate

# Decorative Unicode that marks code and commit messages as machine-written.
# Kept in step with hooks/post_edit_check.py.
BANNED_CHARS = {
    "—": "-- or -", "–": "-", "‘": "'", "’": "'",
    "“": '"', "”": '"', "…": "...", "→": "->",
    "←": "<-", "↔": "<->", "⇒": "=>", "•": "* or -",
    " ": "a normal space",
}

# printf() is a flight-code rule; tests, tools and the simulator are exempt.
PRINTF_EXEMPT = (
    "Tools/", "libraries/SITL/", "libraries/AP_HAL_SITL/",
    "libraries/AP_HAL_Empty/", "libraries/AP_Scripting/examples/",
)


# Paths whose formatting is not the author's to fix: vendored submodules, ST
# CubeMX output, and committed binaries.
VENDORED = ("modules/", "libraries/AP_HAL_ChibiOS/hwdef/STM32CubeConf/",
            "Tools/bootloaders/")
VENDORED_SUFFIXES = (".ioc", ".hex", ".bin", ".ld", ".mk")


def is_vendored(path):
    return path.startswith(VENDORED) or path.endswith(VENDORED_SUFFIXES)


def finding(check, severity, message, **kw):
    f = {"check": check, "severity": severity, "message": message}
    f.update(kw)
    return f


def check_whitespace(scope):
    """git's own trailing-whitespace / space-before-tab detector."""
    proc = subprocess.run(
        ["git", "diff", "--check", scope["rev_range"]],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    per_file = {}
    for line in proc.stdout.split("\n"):
        # `git diff --check` prints "path:line: reason" and then echoes the
        # offending source line. Only the first form is a finding; the echoed
        # line is context and must not be reported as one.
        m = re.match(r"^([^:]+):(\d+): ([a-z].*)$", line)
        if m:
            per_file.setdefault(m.group(1), []).append((int(m.group(2)), m.group(3)))
    out = []
    # One finding per file, not per line: a CubeMX export contributes hundreds
    # of identical lines and drowns everything else in the report.
    for path, hits in sorted(per_file.items()):
        lines = sorted(n for n, _ in hits)
        kinds = sorted({k.rstrip(".") for _, k in hits})
        out.append(finding(
            "whitespace", "note" if is_vendored(path) else "must-fix",
            "%d line(s) with %s%s" % (
                len(hits), "/".join(kinds),
                " (vendored/generated file - not yours to reformat)"
                if is_vendored(path) else ""),
            file=path, line=lines[0],
            detail="lines " + ", ".join(str(n) for n in lines[:12])
                   + (" ..." if len(lines) > 12 else ""),
        ))
    return out


def check_non_ascii(scope):
    out = []
    for path, lineno, text in added_lines(scope["rev_range"]):
        if not path.endswith(CXX_SUFFIXES + (".py", ".lua")):
            continue
        hits = sorted({c for c in text if c in BANNED_CHARS})
        if hits:
            repls = ", ".join("'%s' -> %s" % (c, BANNED_CHARS[c]) for c in hits)
            out.append(finding(
                "non-ascii", "must-fix",
                "non-ASCII punctuation in added code: " + repls,
                file=path, line=lineno, detail=text.strip()[:120],
            ))
    return out


def check_printf(scope):
    out = []
    for path, lineno, text in added_lines(scope["rev_range"]):
        if not path.endswith((".cpp", ".h", ".hpp", ".cc")):
            continue
        if any(path.startswith(p) for p in PRINTF_EXEMPT) or "/tests/" in path:
            continue
        stripped = text.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        if "printf(" not in stripped:
            continue
        if "console->printf" in stripped or "DEV_PRINTF" in stripped:
            continue
        out.append(finding(
            "printf", "must-fix",
            "printf() in flight code - use gcs().send_text(), or "
            "hal.console->printf() for debug builds",
            file=path, line=lineno, detail=stripped[:120],
        ))
    return out


def check_defensive_init(scope):
    """Added POD member initialisers in headers - a reliable LLM-tell."""
    decl = re.compile(
        r"^\s*(?:static\s+)?(?:const\s+)?"
        r"(?:u?int(?:8|16|32|64)_t|float|double|bool|char|size_t)\s+"
        r"\w+(?:\[\w*\])?\s*(?:=\s*(?:0|0\.0f?|false|nullptr)|\{\s*0?\s*\})\s*;"
    )
    out = []
    for path, lineno, text in added_lines(scope["rev_range"], ["*.h", "*.hpp"]):
        if decl.match(text) and "//" not in text.split(";")[0]:
            out.append(finding(
                "defensive-init", "note",
                "explicit zero-initialiser on a class member; ArduPilot zeroes "
                "BSS, new and calloc, so this is redundant unless it is a stack "
                "local or a non-zero default",
                file=path, line=lineno, detail=text.strip()[:120],
            ))
    return out


def check_commits(scope):
    out = []
    commits = commit_records(scope["rev_range"])
    for c in commits:
        ref = c["short"]
        if len(c["parents"]) > 1:
            out.append(finding(
                "commit-merge", "must-fix",
                "merge commit in the branch - rebase onto %s instead"
                % scope["base_ref"], commit=ref, detail=c["subject"],
            ))
            continue
        if re.match(r"^(fixup|squash|amend)! ", c["subject"]):
            out.append(finding(
                "commit-autosquash", "note",
                "autosquash marker - fold it with an autosquash rebase before pushing",
                commit=ref, detail=c["subject"][:100],
            ))
            continue
        if not re.match(r"^[A-Za-z][A-Za-z0-9_]*:", c["subject"]):
            out.append(finding(
                "commit-prefix", "must-fix",
                "commit subject has no subsystem prefix",
                commit=ref, detail=c["subject"][:100],
            ))
        else:
            prefix = c["subject"].split(":", 1)[0]
            allowed = set()
            for sub_name in c["subsystems"]:
                allowed |= acceptable_prefixes(sub_name)
            if c["subsystems"] and prefix not in allowed and not any(
                    upstream_uses_prefix(prefix, f, scope["base_ref"])
                    for f in c["files"][:4]):
                out.append(finding(
                    "commit-prefix-mismatch", "should-fix",
                    "prefix '%s:' does not match the files touched (%s), and the "
                    "base branch has no established history of using it there"
                    % (prefix, ", ".join(c["subsystems"])),
                    commit=ref, detail=c["subject"][:100],
                ))
        if len(c["subsystems"]) > 1:
            out.append(finding(
                "commit-multi-subsystem", "should-fix",
                "commit touches %d subsystems (%s) - split one commit per module"
                % (len(c["subsystems"]), ", ".join(c["subsystems"])),
                commit=ref, detail=c["subject"][:100],
            ))
        if re.search(
            r"Co-Authored-By\s*:.*(Claude|Anthropic|Codex|OpenAI|ChatGPT|"
            r"noreply@anthropic|noreply@openai)", c["body"], re.IGNORECASE
        ) or re.search(
            r"Generated with \[?(Claude|Codex)", c["body"], re.IGNORECASE
        ) or "\U0001f916" in c["body"]:
            out.append(finding(
                "commit-attribution", "must-fix",
                "commit message carries AI attribution - commits must read as "
                "authored by the human contributor",
                commit=ref, detail=c["subject"][:100],
            ))
        hits = sorted({ch for ch in c["body"] if ch in BANNED_CHARS})
        if hits:
            out.append(finding(
                "commit-non-ascii", "should-fix",
                "commit message uses non-ASCII punctuation (%s) - a reviewer "
                "tell for machine-written text" % " ".join(hits),
                commit=ref, detail=c["subject"][:100],
            ))
        if len(c["subject"]) > 72:
            out.append(finding(
                "commit-subject-length", "note",
                "subject is %d chars; keep it under ~72" % len(c["subject"]),
                commit=ref, detail=c["subject"][:100],
            ))
        body_lines = c["body"].split("\n")[1:]
        long_body = [b for b in body_lines if len(b) > 80 and " " in b]
        if long_body:
            out.append(finding(
                "commit-body-wrap", "note",
                "commit body has %d line(s) over 80 chars; wrap bodies to ~75"
                % len(long_body), commit=ref, detail=long_body[0][:100],
            ))
    return out


_GROUPINFO = re.compile(r"AP_(?:GROUPINFO|SUBGROUPINFO|GROUPINFO_FLAGS)\w*\s*\(\s*\"([^\"]+)\"")


def check_params(scope):
    """New AP_Param entries need a doc block, and names are length-limited."""
    out = []
    touched = {}
    for path, lineno, text in added_lines(scope["rev_range"]):
        if not path.endswith((".cpp", ".h", ".hpp", ".cc")):
            continue
        m = _GROUPINFO.search(text)
        if m:
            touched.setdefault(path, []).append((m.group(1), lineno))
    for path, entries in touched.items():
        full = ""
        abspath = os.path.join(REPO_ROOT, path)
        if os.path.exists(abspath):
            with open(abspath, "r", errors="replace") as fh:
                full = fh.read()
        documented = set(re.findall(r"//\s*@Param:\s*(\S+)", full))
        for name, lineno in entries:
            if len(name) > 16:
                out.append(finding(
                    "param-name-length", "must-fix",
                    "parameter name '%s' is %d chars; the limit is 16"
                    % (name, len(name)), file=path, line=lineno,
                ))
            if name not in documented:
                out.append(finding(
                    "param-undocumented", "must-fix",
                    "parameter '%s' has no // @Param: documentation block" % name,
                    file=path, line=lineno,
                ))
    # doc blocks missing the mandatory fields
    for path in {f["path"] for f in scope["files"]}:
        if not path.endswith((".cpp", ".h", ".hpp", ".cc")):
            continue
        abspath = os.path.join(REPO_ROOT, path)
        if not os.path.exists(abspath):
            continue
        with open(abspath, "r", errors="replace") as fh:
            lines = fh.read().split("\n")
        new_here = {n for n, _ in touched.get(path, [])}
        for i, line in enumerate(lines):
            m = re.match(r"\s*//\s*@Param:\s*(\S+)", line)
            if not m or m.group(1) not in new_here:
                continue
            block = []
            j = i + 1
            while j < len(lines) and re.match(r"\s*//\s*@", lines[j]):
                block.append(lines[j])
                j += 1
            text = "\n".join(block)
            for field in ("@DisplayName", "@Description", "@User"):
                if field not in text:
                    out.append(finding(
                        "param-doc-incomplete", "should-fix",
                        "@Param: %s block is missing %s" % (m.group(1), field),
                        file=path, line=i + 1,
                    ))
    return out


def check_new_file_headers(scope):
    out = []
    for f in scope["files"]:
        if f["status"] != "A" or not f["path"].endswith((".cpp", ".h", ".hpp", ".cc")):
            continue
        abspath = os.path.join(REPO_ROOT, f["path"])
        if not os.path.exists(abspath):
            continue
        with open(abspath, "r", errors="replace") as fh:
            head = fh.read(2000)
        # Vendored headers legitimately carry their upstream licence (ST and
        # ChibiOS files are Apache-2.0), so require *a* licence, not GPLv3.
        if not re.search(r"Copyright|Licen[cs]e|SPDX-License-Identifier", head):
            out.append(finding(
                "new-file-license", "should-fix",
                "new source file has no licence or copyright header",
                file=f["path"], line=1,
            ))
    return out


def astyle_scope():
    """The paths CI actually astyle-checks, read from Tools/scripts/run_astyle.py.

    ArduPilot is NOT astyle-clean repo-wide - run_astyle.py names three
    libraries and six files. Running astyle over anything else reports
    reformatting that no reviewer will ask for and no CI job enforces.
    """
    path = os.path.join(REPO_ROOT, "Tools/scripts/run_astyle.py")
    if not os.path.exists(path):
        return None, None
    with open(path, "r", errors="replace") as fh:
        text = fh.read()

    def listed(name):
        m = re.search(name + r"\s*=\s*\[(.*?)\]", text, re.S)
        if not m:
            return []
        return [a or b for a, b in
                re.findall(r"'([^']+)'|\"([^\"]+)\"", m.group(1))]

    return listed("directories_to_check"), listed("files_to_check")


def check_flake8(scope):
    """Changed .py files marked AP_FLAKE8_CLEAN must still pass flake8.

    This is a real CI gate (Tools/scripts/run_flake8.py walks the tree for the
    marker), and it is the cheapest red-CI cause to catch before pushing.
    """
    targets = []
    for f in scope["files"]:
        if f["status"] == "D" or not f["path"].endswith(".py"):
            continue
        abspath = os.path.join(REPO_ROOT, f["path"])
        if not os.path.exists(abspath):
            continue
        with open(abspath, "r", errors="replace") as fh:
            if "AP_FLAKE8_CLEAN" in fh.read():
                targets.append(f["path"])
    if not targets:
        return []
    if not shutil.which("flake8"):
        return [finding(
            "flake8", "note",
            "%d changed file(s) are marked AP_FLAKE8_CLEAN but flake8 is not "
            "installed - CI will still check them" % len(targets))]
    proc = subprocess.run(
        ["flake8"] + targets, capture_output=True, text=True, cwd=REPO_ROOT)
    out = []
    for line in proc.stdout.split("\n"):
        m = re.match(r"^(.+?):(\d+):(\d+): (\S+) (.*)$", line)
        if m:
            out.append(finding(
                "flake8", "must-fix",
                "%s %s" % (m.group(4), m.group(5)),
                file=m.group(1), line=int(m.group(2))))
    if len(out) > 20:
        extra = len(out) - 20
        out = out[:20]
        out.append(finding("flake8", "must-fix",
                           "... and %d more flake8 violation(s)" % extra))
    return out


def check_astyle(scope):
    """Report astyle changes that land on lines this PR added, within CI's scope."""
    if not shutil.which("astyle"):
        return [finding("astyle", "note", "astyle not installed - style check skipped")]
    rc = os.path.join(REPO_ROOT, "Tools/CodeStyle/astylerc")
    if not os.path.exists(rc):
        return [finding("astyle", "note", "Tools/CodeStyle/astylerc not found - skipped")]
    dirs, files = astyle_scope()
    if dirs is None:
        return [finding("astyle", "note",
                        "Tools/scripts/run_astyle.py not found - style check skipped")]
    added = {}
    for path, lineno, _ in added_lines(scope["rev_range"], ["*.cpp", "*.h", "*.hpp", "*.cc"]):
        in_scope = path in files or any(
            path.startswith(d.rstrip("/") + "/") for d in dirs)
        if in_scope:
            added.setdefault(path, set()).add(lineno)
    out = []
    for path, lines in added.items():
        abspath = os.path.join(REPO_ROOT, path)
        if not os.path.exists(abspath):
            continue
        with open(abspath, "r", errors="replace") as fh:
            original = fh.read()
        proc = subprocess.run(
            ["astyle", "--options=" + rc], input=original,
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        if proc.returncode != 0 or proc.stdout == original:
            continue
        orig_lines = original.split("\n")
        new_lines = proc.stdout.split("\n")
        sm = difflib.SequenceMatcher(None, orig_lines, new_lines, autojunk=False)
        hit = []
        for tag, i1, i2, _, _ in sm.get_opcodes():
            if tag == "equal":
                continue
            for n in range(i1 + 1, max(i2, i1 + 1) + 1):
                if n in lines:
                    hit.append(n)
        if hit:
            out.append(finding(
                "astyle", "should-fix",
                "astyle would reformat %d line(s) this PR added (%s)"
                % (len(hit), ", ".join(str(n) for n in sorted(hit)[:8])),
                file=path, line=sorted(hit)[0],
            ))
    return out


def check_size(scope):
    out = []
    t = scope["totals"]
    if t["added"] + t["deleted"] > 1500:
        out.append(finding(
            "diff-size", "note",
            "%d changed lines across %d files - large enough that a reviewer "
            "will ask for it to be split" % (t["added"] + t["deleted"], t["files"]),
        ))
    if scope["dirty"]:
        out.append(finding(
            "uncommitted", "note",
            "%d tracked file(s) have uncommitted changes; they are NOT part of "
            "this review: %s" % (len(scope["dirty"]), ", ".join(scope["dirty"][:5])),
        ))
    return out


CHECKS = {
    "whitespace": check_whitespace,
    "non-ascii": check_non_ascii,
    "printf": check_printf,
    "commits": check_commits,
    "params": check_params,
    "new-file-license": check_new_file_headers,
    "flake8": check_flake8,
    "defensive-init": check_defensive_init,
    "astyle": check_astyle,
    "size": check_size,
}

SEVERITY_ORDER = {"must-fix": 0, "should-fix": 1, "note": 2}


def run_checks(scope, skip=()):
    findings = []
    for name, fn in CHECKS.items():
        if name in skip:
            continue
        try:
            findings += fn(scope)
        except Exception as exc:                      # a broken check is a note
            findings.append(finding(
                name, "note", "check failed to run: %s: %s"
                % (type(exc).__name__, exc)))
    findings.sort(key=lambda f: (
        SEVERITY_ORDER.get(f["severity"], 3), f["check"],
        f.get("file") or "", f.get("line") or 0))
    return findings


# ------------------------------------------------------------------ PR thread


def fetch_thread(pr):
    """Return the PR's comments, reviews and review comments, oldest first.

    Every list is paginated: an active PR easily exceeds the 30-item first page
    and the newest items - the ones that answer your last round of findings -
    are exactly the ones that fall off it.
    """
    if not pr:
        return []
    repo = pr.get("repo")
    if not repo:
        out = gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner",
                 check=False)
        repo = out.strip() or "ArduPilot/ardupilot"
    n = pr["number"]
    items = []
    counts = {}

    def collect(path, kind, jq):
        raw = gh("api", "--paginate", path % (repo, n), "--jq", jq)
        counts[kind] = 0
        for line in raw.split("\n"):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            rec["kind"] = kind
            counts[kind] += 1
            items.append(rec)

    collect("repos/%s/issues/%d/comments", "comment",
            '.[] | {when: .created_at, who: .user.login, body: .body}')
    collect("repos/%s/pulls/%d/reviews", "review",
            '.[] | {when: .submitted_at, who: .user.login, state: .state, body: .body}')
    collect("repos/%s/pulls/%d/comments", "review-comment",
            r'.[] | {when: .created_at, who: .user.login, '
            r'where: "\(.path):\(.line)", body: .body}')
    items.sort(key=lambda r: r.get("when") or "")
    return items, counts


def thread_cmd(args):
    pr = lookup_pr(args.target)
    if not pr:
        print("no open PR for this branch - nothing to read")
        return
    items, counts = fetch_thread(pr)
    if args.json:
        print(json.dumps({"pr": pr["number"], "counts": counts, "items": items},
                         indent=2))
        return
    print("PR #%s %s" % (pr["number"], pr.get("title", "")))
    # Per-source counts, so "nothing to read" is visibly a fetched result
    # rather than a fetch that quietly failed.
    print("fetched: %s" % ", ".join("%d %s" % (v, k) for k, v in counts.items()))
    print("%d thread item(s)\n" % len(items))
    for r in items:
        head = "[%s] %s %s" % (r["kind"], r.get("when", "")[:19], r.get("who", ""))
        if r.get("state"):
            head += " %s" % r["state"]
        if r.get("where"):
            head += " %s" % r["where"]
        print(head)
        body = (r.get("body") or "").strip()
        for line in body.split("\n"):
            print("    %s" % line)
        print("")


# ------------------------------------------------------------------ codex pool


def pool_paths(directory):
    return (
        os.path.join(directory, "tasks"),
        os.path.join(directory, "logs"),
        os.path.join(directory, "POOL_DONE"),
        os.path.join(directory, "summary.json"),
    )


def pool_tasks(tasks_dir):
    if not os.path.isdir(tasks_dir):
        return []
    return sorted(
        f[:-5] for f in os.listdir(tasks_dir) if f.endswith(".task")
    )


def run_one(name, tasks_dir, logs_dir, timeout):
    with open(os.path.join(tasks_dir, name + ".task"), "r") as fh:
        prompt = fh.read()
    log = os.path.join(logs_dir, name + ".log")
    started = time.time()
    with open(log, "w") as out, open(os.devnull, "r") as devnull:
        try:
            proc = subprocess.run(
                ["codex", "exec", "--skip-git-repo-check", prompt],
                stdin=devnull, stdout=out, stderr=subprocess.STDOUT,
                cwd=REPO_ROOT, timeout=timeout,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            out.write("\n[pr_review] TIMEOUT after %ds\n" % timeout)
            rc = 124
        except FileNotFoundError:
            out.write("[pr_review] codex CLI not found on PATH\n")
            rc = 127
    return {
        "task": name, "rc": rc,
        "seconds": round(time.time() - started, 1),
        "bytes": os.path.getsize(log) if os.path.exists(log) else 0,
    }


def pool_run(args):
    tasks_dir, logs_dir, done, summary = pool_paths(args.dir)
    names = pool_tasks(tasks_dir)
    if not names:
        sys.exit("error: no *.task files in %s" % tasks_dir)
    os.makedirs(logs_dir, exist_ok=True)
    if args.retry:
        names = [
            n for n in names
            if not os.path.exists(os.path.join(logs_dir, n + ".log"))
            or os.path.getsize(os.path.join(logs_dir, n + ".log")) == 0
        ]
        if not names:
            print("nothing to retry - every task has a non-empty log")
            return
    if os.path.exists(done):
        os.remove(done)

    if not args.foreground:
        # Detach so the pool outlives the tool call that started it. The
        # sentinel file, not the process table, is the completion signal.
        if os.fork() != 0:
            print("pool started: %d task(s), %d at a time, dir=%s"
                  % (len(names), args.jobs, args.dir))
            print("poll with: pr_review.py codex status --dir %s" % args.dir)
            return
        os.setsid()
        if os.fork() != 0:
            os._exit(0)
        fd = os.open(os.devnull, os.O_RDWR)
        for target in (0, 1, 2):
            os.dup2(fd, target)

    from concurrent.futures import ThreadPoolExecutor
    results = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [
            pool.submit(run_one, n, tasks_dir, logs_dir, args.timeout) for n in names
        ]
        for fut in futures:
            results.append(fut.result())
    with open(summary, "w") as fh:
        json.dump({"tasks": results, "finished": int(time.time())}, fh, indent=2)
    with open(done, "w") as fh:
        fh.write("%d\n" % len(results))
    if args.foreground:
        print(json.dumps({"tasks": results}, indent=2))
    else:
        os._exit(0)


def pool_status(args):
    tasks_dir, logs_dir, done, summary = pool_paths(args.dir)
    names = pool_tasks(tasks_dir)
    rows = []
    for n in names:
        log = os.path.join(logs_dir, n + ".log")
        size = os.path.getsize(log) if os.path.exists(log) else 0
        if not os.path.exists(log):
            state = "pending"
        elif os.path.exists(done):
            state = "done" if size else "EMPTY"
        else:
            state = "running" if size == 0 else "writing"
        rows.append({"task": n, "state": state, "bytes": size, "log": log})
    finished = os.path.exists(done)
    if finished:
        for r in rows:
            if r["state"] in ("running", "writing", "pending"):
                r["state"] = "done" if r["bytes"] else "EMPTY"
    detail = {}
    if os.path.exists(summary):
        with open(summary) as fh:
            detail = {t["task"]: t for t in json.load(fh).get("tasks", [])}
    for r in rows:
        if r["task"] in detail:
            r["rc"] = detail[r["task"]]["rc"]
            r["seconds"] = detail[r["task"]]["seconds"]
    bad = [r for r in rows if r["state"] == "EMPTY" or r.get("rc") not in (None, 0)]
    if args.json:
        print(json.dumps({"finished": finished, "tasks": rows, "failed": len(bad)},
                         indent=2))
    else:
        for r in rows:
            extra = ""
            if "rc" in r:
                extra = "  rc=%s  %ss" % (r["rc"], r["seconds"])
            print("%-28s %-8s %8d bytes%s" % (r["task"], r["state"], r["bytes"], extra))
        print("---")
        print("pool %s; %d/%d task(s) produced output%s"
              % ("finished" if finished else "still running",
                 len([r for r in rows if r["bytes"]]), len(rows),
                 ", %d FAILED" % len(bad) if bad else ""))
    if not finished:
        sys.exit(3)
    sys.exit(4 if bad else 0)


# ------------------------------------------------------------------ state file


def state_path():
    common = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        capture_output=True, text=True, cwd=REPO_ROOT,
    ).stdout.strip() or ".git"
    if not os.path.isabs(common):
        common = os.path.join(REPO_ROOT, common)
    return os.path.join(common, "pr-review-state.json")


def state_cmd(args):
    path = state_path()
    if args.action == "show":
        if not os.path.exists(path):
            print("no recorded review")
            sys.exit(1)
        print(open(path).read())
        return
    if args.action == "clear":
        if os.path.exists(path):
            os.remove(path)
        print("cleared %s" % path)
        return
    head = git("rev-parse", "HEAD").strip()
    if args.action == "save":
        blob = {
            "head": head, "head_short": head[:10],
            "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(),
            "verdict": args.verdict, "findings": args.findings,
            "base_ref": args.base or "", "when": int(time.time()),
        }
        with open(path, "w") as fh:
            json.dump(blob, fh, indent=2)
        print("recorded review of %s at %s" % (blob["branch"], blob["head_short"]))
        return
    # diff: what changed since the recorded review
    if not os.path.exists(path):
        print("no recorded review - review everything")
        sys.exit(1)
    with open(path) as fh:
        blob = json.load(fh)
    if blob["head"] == head:
        print("unchanged since the recorded review at %s (verdict: %s)"
              % (blob["head_short"], blob.get("verdict")))
        sys.exit(0)
    if not git_ok("rev-parse", "--verify", "--quiet", blob["head"] + "^{commit}"):
        print("recorded head %s is gone (rebased?) - re-review everything"
              % blob["head_short"])
        sys.exit(2)
    print("head moved %s -> %s since the last review; changed since then:"
          % (blob["head_short"], head[:10]))
    print(git("diff", "--stat", blob["head"], head).rstrip())
    sys.exit(2)


# ----------------------------------------------------------------- presentation


def print_scope(scope):
    pr = scope["pr"]
    for w in scope.get("warnings", []):
        print("WARNING:  %s" % w)
        print("")
    print("branch:   %s @ %s" % (scope["branch"], scope["head_short"]))
    print("base:     %s (merge-base %s)" % (scope["base_ref"], scope["merge_base"][:10]))
    if pr:
        print("PR:       #%s %s [%s%s]" % (
            pr.get("number"), pr.get("title", ""), pr.get("state", ""),
            ", draft" if pr.get("isDraft") else ""))
        print("          %s" % pr.get("url", ""))
    else:
        print("PR:       none open for this branch (pre-submission review)")
    t = scope["totals"]
    print("diff:     %d commit(s), %d file(s), +%d/-%d"
          % (t["commits"], t["files"], t["added"], t["deleted"]))
    print("subsystems: %s" % (", ".join(scope["subsystems"]) or "-"))
    if scope["dirty"]:
        print("dirty:    %d uncommitted tracked file(s) - excluded from the review"
              % len(scope["dirty"]))
    print("")
    for c in scope["commits"]:
        print("  %s  %s" % (c["short"], c["subject"][:88]))
    print("")
    for f in scope["files"]:
        print("  %s  +%-5s -%-5s %s" % (
            f["status"], f["added"], f["deleted"], f["path"]))


def print_findings(findings):
    if not findings:
        print("mechanical gate: clean")
        return
    counts = {}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    print("mechanical gate: %s" % ", ".join(
        "%d %s" % (counts[s], s) for s in ("must-fix", "should-fix", "note")
        if s in counts))
    print("")
    current = None
    for f in findings:
        if f["severity"] != current:
            current = f["severity"]
            print("== %s ==" % current.upper())
        where = f.get("file", "")
        if where and f.get("line"):
            where += ":%d" % f["line"]
        if f.get("commit"):
            where = "commit %s" % f["commit"]
        print("  [%s] %s%s" % (f["check"], where + " - " if where else "", f["message"]))
        if f.get("detail"):
            print("        %s" % f["detail"])


# ------------------------------------------------------------------------- main


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    for name in ("scope", "checks"):
        p = sub.add_parser(name)
        p.add_argument("target", nargs="?", help="PR number/URL (default: current branch)")
        p.add_argument("--base", help="base ref to diff against")
        p.add_argument("--pr", action="store_true", help="force a gh PR lookup")
        p.add_argument("--json", action="store_true")
        # Skill-level flags: the SKILL.md passes $ARGUMENTS through verbatim, so
        # these have to be accepted and ignored here rather than crashing the
        # first command of the pipeline.
        p.add_argument("--fix", action="store_true",
                       help=argparse.SUPPRESS)
        p.add_argument("--no-codex", dest="no_codex", action="store_true",
                       help=argparse.SUPPRESS)
        if name == "checks":
            p.add_argument("--skip", default="", help="comma-separated checks to skip")

    t = sub.add_parser("thread")
    t.add_argument("target", nargs="?")
    t.add_argument("--json", action="store_true")

    c = sub.add_parser("codex")
    csub = c.add_subparsers(dest="action", required=True)
    cr = csub.add_parser("run")
    cr.add_argument("--dir", required=True, help="pool directory holding tasks/")
    cr.add_argument("--jobs", type=int, default=4)
    cr.add_argument("--timeout", type=int, default=900)
    cr.add_argument("--retry", action="store_true", help="only re-run empty/missing logs")
    cr.add_argument("--foreground", action="store_true")
    cs = csub.add_parser("status")
    cs.add_argument("--dir", required=True)
    cs.add_argument("--json", action="store_true")

    s = sub.add_parser("state")
    s.add_argument("action", choices=["save", "show", "diff", "clear"])
    s.add_argument("--verdict", default="")
    s.add_argument("--findings", type=int, default=0)
    s.add_argument("--base", default="")

    args = ap.parse_args()

    if args.cmd == "codex":
        return pool_run(args) if args.action == "run" else pool_status(args)
    if args.cmd == "state":
        return state_cmd(args)
    if args.cmd == "thread":
        return thread_cmd(args)

    scope = build_scope(args)
    if args.cmd == "scope":
        print(json.dumps(scope, indent=2)) if args.json else print_scope(scope)
        return
    findings = run_checks(scope, skip=[s for s in args.skip.split(",") if s])
    if args.json:
        print(json.dumps({"scope": {k: scope[k] for k in
                                    ("branch", "head_short", "base_ref", "totals",
                                     "warnings")},
                          "findings": findings}, indent=2))
    else:
        print_scope(scope)
        print("")
        print_findings(findings)
    if any(f["severity"] == "must-fix" for f in findings):
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except GitError as exc:
        sys.exit("error: %s" % exc)
    except BrokenPipeError:
        pass
