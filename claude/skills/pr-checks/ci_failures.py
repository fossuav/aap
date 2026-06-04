#!/usr/bin/env python3
"""Summarise failing CI checks for an ArduPilot pull request.

Wraps the gh calls (pr view, run jobs, job-log download) in a single process so
the whole workflow runs under one `python3 ...` permission instead of prompting
for each gh invocation. Resolves the PR's check rollup, finds the failed checks,
downloads only the failed jobs' logs (via the REST API, which is reliable where
`gh run view --log-failed` returns nothing for this repo), and extracts the
failing tests / build errors.

Usage:
    python3 ci_failures.py [PR]               # PR number, URL, or branch
    python3 ci_failures.py [PR] --repo OWNER/REPO
    python3 ci_failures.py [PR] --raw NAME    # dump matching job's raw error lines
    python3 ci_failures.py [PR] --max-lines 40

With no PR argument it uses the current branch's PR (via gh's own resolution).
"""
import argparse
import json
import re
import subprocess
import sys
from collections import Counter, OrderedDict

# conclusions that mean "this check did not pass"
BAD = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ACTION_REQUIRED", "STALE"}

TS = re.compile(r"^\S+Z\s")  # leading ISO8601 timestamp the API prepends
ANNOT = re.compile(r"##\[error\]\s*(.+)")
TESTS_SUMMARY = re.compile(r"\bFAILED \d+ tests?:\s*\[.*\]")
PER_TEST = re.compile(r'\bFAILED:\s+".+')
STEP = re.compile(r">>>>\s*FAILED STEP:")
# build failures that the problem matcher did not annotate (some toolchains)
COMPILE = re.compile(r"\S+:\d+:\d+:\s*(?:fatal\s+)?error:\s|undefined reference to")
BUILDFAIL = re.compile(r"^Build failed\b|->\s*task in .+ failed \(exit status")
DROP = re.compile(r"Process completed with exit code")


def gh(args, repo=None):
    cmd = ["gh"] + args
    if repo:
        cmd += ["--repo", repo]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return ("%s" % e, False)
    if p.returncode != 0:
        return (p.stderr.strip() or p.stdout.strip(), False)
    return (p.stdout, True)


def repo_from_url(url):
    m = re.search(r"github\.com/([^/]+/[^/]+)/", url or "")
    return m.group(1) if m else None


def ids_from_url(url):
    """Return (run_id, job_id) parsed from a check detailsUrl, either may be None."""
    run = re.search(r"/actions/runs/(\d+)", url or "")
    job = re.search(r"/job/(\d+)", url or "")
    return (run.group(1) if run else None, job.group(1) if job else None)


def job_log(repo, job_id):
    """Download a single job's full log via the REST API."""
    return gh(["api", "repos/%s/actions/jobs/%s/logs" % (repo, job_id)])


def extract_failures(log, max_lines):
    """Surface the curated failure lines: ##[error] annotations, the test
    summary, per-test FAILED lines. Skips the in-test GCS chatter."""
    hits = OrderedDict()
    for raw in log.splitlines():
        line = TS.sub("", raw).rstrip()
        if not line or DROP.search(line):
            continue
        m = ANNOT.search(line)
        if m:
            text = m.group(1).strip()
        elif (TESTS_SUMMARY.search(line) or PER_TEST.search(line) or STEP.search(line)
              or COMPILE.search(line) or BUILDFAIL.search(line)):
            text = line.strip()
        else:
            continue
        if not DROP.search(text):
            hits.setdefault(text[:240], True)
        if len(hits) >= max_lines:
            break
    return list(hits.keys())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pr", nargs="?", help="PR number, URL, or branch")
    ap.add_argument("--repo", help="OWNER/REPO (default: derived from the PR)")
    ap.add_argument("--raw", help="dump raw matching lines for jobs whose name contains this string")
    ap.add_argument("--max-lines", type=int, default=30, help="max failure lines per job")
    args = ap.parse_args()

    view = ["pr", "view"]
    if args.pr:
        view.append(args.pr)
    view += ["--json", "number,title,url,headRefName,statusCheckRollup"]
    out, ok = gh(view, repo=args.repo)
    if not ok:
        print("Could not read the PR: %s" % out, file=sys.stderr)
        return 1
    pr = json.loads(out)
    repo = args.repo or repo_from_url(pr.get("url"))
    rollup = pr.get("statusCheckRollup") or []

    states = Counter()
    failed = []
    for c in rollup:
        concl = (c.get("conclusion") or "").upper()
        status = (c.get("status") or "").upper()
        if status not in ("COMPLETED", ""):
            states["pending"] += 1
        elif concl == "SUCCESS":
            states["pass"] += 1
        elif concl in ("SKIPPED", "NEUTRAL"):
            states["skipped"] += 1
        elif concl in BAD:
            states["fail"] += 1
            failed.append(c)
        else:
            states[concl.lower() or "pending"] += 1

    print("PR #%s  %s" % (pr.get("number"), pr.get("title", "")))
    print("%s" % pr.get("url", ""))
    print("checks: %d total - %s" % (
        len(rollup),
        ", ".join("%d %s" % (n, k) for k, n in sorted(states.items())) or "none",
    ))
    print()

    if not failed:
        if states.get("pending"):
            print("No failures yet. %d check(s) still pending - re-run when they finish."
                  % states["pending"])
        else:
            print("All checks passed.")
        return 0

    # one failed job -> one log download, deduped by job id; external checks
    # (no /job/ in the URL) are just listed with their link.
    jobs = OrderedDict()
    external = []
    for c in failed:
        run_id, job_id = ids_from_url(c.get("detailsUrl"))
        if job_id:
            jobs.setdefault(job_id, c)
        else:
            external.append(c)

    print("=== %d failing check(s) ===\n" % len(failed))

    for job_id, c in jobs.items():
        name = c.get("name", "?")
        wf = c.get("workflowName", "")
        label = "%s / %s" % (wf, name) if wf and wf != name else (name or wf)
        print("- %s" % label)
        log, ok = job_log(repo, job_id)
        if not ok or not log.strip():
            print("    (could not download job log - open the run)")
            print("    %s" % c.get("detailsUrl", ""))
            print()
            continue
        if args.raw and args.raw.lower() in label.lower():
            for raw in log.splitlines():
                line = TS.sub("", raw).rstrip()
                if "##[error]" in line or TESTS_SUMMARY.search(line):
                    print("    %s" % line)
            print()
            continue
        fails = extract_failures(log, args.max_lines)
        if fails:
            for f in fails:
                print("    %s" % f)
        else:
            print("    (no recognised failure markers - open the run log)")
            print("    %s" % c.get("detailsUrl", ""))
        print()

    for c in external:
        print("- external: %s  (%s)" % (c.get("name", "?"), c.get("conclusion")))
        print("  %s" % c.get("detailsUrl", ""))
        print()

    print("Tip: --raw <job-name-substring> dumps that job's raw error lines; "
          "open the detailsUrl for full logs.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
