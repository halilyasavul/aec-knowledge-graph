"""One-shot driver for the Claude Code evaluation on a Windows machine with Docker Desktop.

    python -X utf8 -m eval.win_run [--model sonnet] [--run-id run7-claude-rep1] [--ids-file ...]

Does, in order, logging everything to eval/runs/_win_run.log:
  1. Docker Desktop up (starts it if the daemon is not answering, waits up to 4 min).
  2. A Neo4j 5 container running: the first existing container whose image is neo4j, else
     `docker compose up -d neo4j`. Waits for bolt; tries the compose password and the .env one.
  3. The graph populated: if it has no :Class nodes, runs aec_kg.ingest_graph + reingest_ucks.
  4. NEO4J_* exported for everything below (the MCP servers inherit them).
  5. eval.generate_claude --probe; stops if it does not print "probe ok".
  6. eval.generate_claude for the item list (resumable: rerun this script to continue).
  7. eval.score for strict, determined-only (+excused, +request values), standard and probe sets.
Nothing here needs a Gemini key.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import subprocess
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LOG = REPO / "eval" / "runs" / "_win_run.log"
DOCKER_DESKTOP = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"
LOCAL_URI = "bolt://localhost:7687"


def log(msg: str) -> None:
    line = f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def sh(cmd: list[str], timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess:
    log(f"$ {' '.join(cmd)}")
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    for ln in out.strip().splitlines()[-25:]:
        log(f"  | {ln}")
    if check and p.returncode:
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}")
    return p


def docker_up() -> None:
    if subprocess.run(["docker", "info"], capture_output=True).returncode == 0:
        log("docker daemon already running")
        return
    log("docker daemon not answering; starting Docker Desktop")
    subprocess.Popen([DOCKER_DESKTOP], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for i in range(48):
        time.sleep(5)
        if subprocess.run(["docker", "info"], capture_output=True).returncode == 0:
            log(f"docker daemon up after {(i + 1) * 5} s")
            return
    raise SystemExit("Docker daemon did not come up in 4 minutes")


def neo4j_container() -> str:
    p = sh(["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"])
    rows = [ln.split("\t") for ln in p.stdout.splitlines() if ln.strip()]
    neo = [r for r in rows if len(r) >= 2 and "neo4j" in r[1].lower()]
    running = [r for r in neo if r[2].lower().startswith("up")]
    if running:
        log(f"neo4j container already running: {running[0][0]}")
        return running[0][0]
    if neo:
        name = neo[0][0]
        sh(["docker", "start", name], check=True)
        log(f"started existing neo4j container {name} ({neo[0][1]})")
        return name
    log("no neo4j container found; creating one with docker compose (service neo4j)")
    sh(["docker", "compose", "up", "-d", "neo4j"], timeout=600, check=True)
    p = sh(["docker", "ps", "--format", "{{.Names}}\t{{.Image}}"])
    for ln in p.stdout.splitlines():
        if "neo4j" in ln.lower():
            return ln.split("\t")[0]
    raise SystemExit("compose ran but no neo4j container is listed")


def wait_for_bolt(passwords: list[str]) -> tuple[str, str]:
    import neo4j
    last = None
    for i in range(60):
        for pw in passwords:
            try:
                d = neo4j.GraphDatabase.driver(LOCAL_URI, auth=("neo4j", pw), connection_timeout=5)
                with d.session() as s:
                    n = s.run("MATCH (c:Class) RETURN count(c) AS n").single()["n"]
                d.close()
                log(f"bolt up; auth ok with password #{passwords.index(pw) + 1}; :Class nodes = {n}")
                return pw, n
            except Exception as e:  # noqa: BLE001
                last = f"{type(e).__name__}: {str(e)[:120]}"
        time.sleep(5)
    raise SystemExit(f"Neo4j did not accept a connection in 5 minutes; last error: {last}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--run-id", default="run7-claude-rep1")
    ap.add_argument("--ids-file", default="eval/item_lists/v8_47.json")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--skip-score", action="store_true")
    args = ap.parse_args(argv)
    os.chdir(REPO)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log(f"=== win_run start: model={args.model} run={args.run_id} python={sys.executable}")

    # deps
    try:
        import mcp  # noqa: F401
        log("mcp already installed")
    except ImportError:
        sh([sys.executable, "-m", "pip", "install", "--user", "mcp>=2.0"], timeout=600, check=True)

    docker_up()
    neo4j_container()
    from dotenv import dotenv_values
    envv = dotenv_values(REPO / ".env")
    passwords = ["password123"]
    if envv.get("NEO4J_PASSWORD") and envv["NEO4J_PASSWORD"] not in passwords:
        passwords.append(envv["NEO4J_PASSWORD"])
    passwords.append("password")
    pw, n_classes = wait_for_bolt(passwords)
    os.environ.update({"NEO4J_URI": LOCAL_URI, "NEO4J_USER": "neo4j", "NEO4J_PASSWORD": pw})
    if n_classes == 0:
        log("graph is empty; ingesting (this takes a while)")
        sh([sys.executable, "-X", "utf8", "-m", "aec_kg.ingest_graph"], timeout=3600, check=True)
        sh([sys.executable, "-X", "utf8", "-m", "aec_kg.reingest_ucks"], timeout=600)
        pw, n_classes = wait_for_bolt([pw])
        if n_classes == 0:
            raise SystemExit("ingest finished but the graph still has no :Class nodes")

    # probe
    p = sh([sys.executable, "-X", "utf8", "-m", "eval.generate_claude", "--run-id", "run7-probe", "--probe",
            "--model", args.model], timeout=600)
    if "probe ok" not in (p.stdout or ""):
        raise SystemExit("probe did not pass; see the lines above")

    # the run (resumable)
    cmd = [sys.executable, "-X", "utf8", "-m", "eval.generate_claude", "--run-id", args.run_id,
           "--ids-file", args.ids_file, "--model", args.model]
    if args.limit:
        cmd += ["--limit", str(args.limit)]
    log(f"$ {' '.join(cmd)}")
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                          encoding="utf-8", errors="replace", bufsize=1) as proc:
        for ln in proc.stdout:
            log("  | " + ln.rstrip())
    log(f"generate exit code {proc.returncode}")

    if args.skip_score:
        return
    run_dir = f"eval/runs/{args.run_id}"
    base = [sys.executable, "-X", "utf8", "-m", "eval.score", run_dir, "eval/nl_to_ids_testset/spec_tasks.jsonl", "eval/models"]
    for extra in ([], ["--probe"], ["--relaxed"], ["--relaxed", "--probe"],
                  ["--relaxed", "--excuse-extras"], ["--relaxed", "--excuse-extras", "--probe"],
                  ["--relaxed", "--annotations", "eval/annotations/determinacy_plus_request_values.jsonl", "--tag", "_rv",
                   "--excuse-extras", "--probe"]):
        sh(base + extra, timeout=1800)
    log("=== win_run done")


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        log(f"STOPPED: {e}")
        raise
    except Exception as e:  # noqa: BLE001
        import traceback
        log("CRASH: " + traceback.format_exc()[-2000:])
        raise
