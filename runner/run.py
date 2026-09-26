#!/usr/bin/env python3
"""Run every case in cases.tsv through one libcupsfilters build.

usage: run.py --prefix /opt/baseline --harness harness/harness-baseline --out results/baseline
"""

import argparse
import csv
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_cases(path, groups, pattern):
    with open(path, newline="") as fp:
        cases = list(csv.DictReader(fp, delimiter="\t"))
    if groups:
        cases = [c for c in cases if c["group"] in groups]
    if pattern:
        rx = re.compile(pattern)
        cases = [c for c in cases if rx.search(c["id"])]
    return cases


def job_env(prefix, tmpdir):
    env = dict(os.environ)
    env.update({
        "LD_LIBRARY_PATH": os.pathsep.join(filter(None, [str(prefix / "lib"), env.get("LD_LIBRARY_PATH")])),
        "CUPS_DATADIR": str(prefix / "share/cups"),
        "HARNESS_BANNER_DIR": str(prefix / "share/cups/data"),
        # Pin everything that could leak into output (dates, locale, temp names).
        "SOURCE_DATE_EPOCH": "1700000000",
        "TZ": "UTC",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": tmpdir,
    })
    return env


def run_case(case, harness, prefix, out_dir, timeout):
    out_file = out_dir / "outputs" / case["id"]
    log_file = out_dir / "logs" / (case["id"] + ".log")
    out_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    cmd = [str(harness),
           "--in", str(ROOT / case["input"]), "--in-type", case["in_type"],
           "--out", str(out_file), "--out-type", case["out_type"],
           "--color", case["color"], "--duplex", case["duplex"],
           "--media", case["media"], "--copies", case["copies"]]
    if case["chain"]:
        cmd += ["--chain", case["chain"]]
    if case["options"]:
        cmd += ["--options", case["options"]]

    result = {"exit": None, "signal": None, "timeout": False}
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lcfr-") as tmp, open(log_file, "wb") as log:
        log.write(("$ " + " ".join(cmd) + "\n").encode())
        log.flush()
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT,
                                  env=job_env(prefix, tmp), timeout=timeout)
            if proc.returncode < 0:
                result["signal"] = signal.Signals(-proc.returncode).name
            else:
                result["exit"] = proc.returncode
        except subprocess.TimeoutExpired:
            result["timeout"] = True
    result["duration"] = round(time.monotonic() - start, 3)
    result["output_size"] = out_file.stat().st_size if out_file.exists() else None
    return case["id"], result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--prefix", required=True, type=Path, help="install prefix of the build under test")
    ap.add_argument("--harness", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cases", type=Path, default=ROOT / "cases" / "cases.tsv")
    ap.add_argument("--group", action="append", help="only run this group (repeatable)")
    ap.add_argument("--filter", help="only run case ids matching this regex")
    ap.add_argument("--jobs", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--timeout", type=int, default=120, help="seconds per case")
    args = ap.parse_args()

    prefix, harness, out_dir = args.prefix.resolve(), args.harness.resolve(), args.out.resolve()
    cases = load_cases(args.cases, args.group, args.filter)
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)

    results = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_case, c, harness, prefix, out_dir, args.timeout) for c in cases]
        for n, fut in enumerate(as_completed(futures), 1):
            cid, res = fut.result()
            results[cid] = res
            status = "TIMEOUT" if res["timeout"] else res["signal"] or f"exit={res['exit']}"
            print(f"[{n}/{len(cases)}] {status:10s} {res['duration']:7.2f}s  {cid}", flush=True)

    info_file = prefix / "share/libcupsfilters-regression/build-info.txt"
    build_info = dict(l.split("=", 1) for l in info_file.read_text().splitlines() if "=" in l) if info_file.exists() else {}

    summary = {
        "build": build_info,
        "prefix": str(prefix),
        "cases": {c["id"]: {**c, **results[c["id"]]} for c in cases},
    }
    (out_dir / "results.json").write_text(json.dumps(summary, indent=1, sort_keys=True))

    failed = sum(1 for r in results.values() if r["exit"] != 0)
    print(f"done: {len(cases)} cases, {failed} non-zero/crashed/timed out -> {out_dir / 'results.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
