#!/usr/bin/env python3
"""Run queued jobs on the owner's Mac, one at a time, for an agent that can't run them itself.

An agent working from the cloud can write files into this checkout but can't run anything on the Mac:
no Metal GPU, none of the Mac's own environments (`.venv`, `.cache/ear/env`). The owner starts this
runner once (double-click `scripts/mac/start-runner.command`); from then on the agent drops a shell
script into `out/runner/queue/` and the runner runs it here, in the checkout, and leaves the log and
the result where the agent can read them.

Rules it keeps (AGENTS.md, "The owner's machine"):
- one job at a time, in name order;
- a job marked `# runner: gpu` runs only inside a GPU window the owner has granted
  (`out/runner/window.json`, written when she grants one in chat) and only on mains power, and is
  stopped when the window ends;
- every job runs under `caffeinate -i`, with a time limit (`hours=`, default 2);
- a macOS notification says when a job starts and ends, so she can see what runs;
- `out/runner/STOP` (or Ctrl-C) stops the runner after the current job.

Files, all under `out/runner/` (never committed):
    queue/NNN-name.sh       waiting jobs. First lines may hold `# runner: gpu hours=6`
    running/NNN-name.sh     the job now running
    done/NNN-name.sh        finished jobs, with done/NNN-name.json (exit code, times) beside them
    logs/NNN-name.log       everything the job printed
    heartbeat.json          the runner's pid, the time and the job it's on, rewritten every few seconds
    window.json             {"until": "2026-10-23T07:00:00-07:00", "note": "..."}: the granted GPU window

Standard library only, so it runs with any Python 3.10+ on the Mac.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

POLL_SECONDS = 5
DEFAULT_HOURS = 2.0
GRACE_SECONDS = 60          # after asking a job to stop, how long before it's killed
HEADER = re.compile(r"^#\s*runner:(.*)$")


@dataclass
class Job:
    path: Path
    gpu: bool = False
    hours: float = DEFAULT_HOURS

    @property
    def name(self) -> str:
        return self.path.stem


def root_dir() -> Path:
    """The checkout: $COPYIST_ROOT, else two levels above this file."""
    env = os.environ.get("COPYIST_ROOT")
    return Path(env) if env else Path(__file__).resolve().parents[2]


def runner_dir(root: Path) -> Path:
    return root / "out" / "runner"


def folders(root: Path) -> dict[str, Path]:
    base = runner_dir(root)
    out = {name: base / name for name in ("queue", "running", "done", "logs")}
    for p in out.values():
        p.mkdir(parents=True, exist_ok=True)
    return out


def now() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def read_job(path: Path) -> Job:
    """A queued script and what its `# runner:` line asks for."""
    job = Job(path)
    with open(path, encoding="utf-8", errors="replace") as f:
        for _ in range(5):
            line = f.readline()
            m = HEADER.match(line.strip())
            if not m:
                continue
            for word in m.group(1).split():
                if word == "gpu":
                    job.gpu = True
                elif word.startswith("hours="):
                    try:
                        job.hours = max(1e-4, float(word.split("=", 1)[1]))
                    except ValueError:
                        pass
    return job


def next_job(root: Path) -> Job | None:
    queued = sorted(folders(root)["queue"].glob("*.sh"))
    return read_job(queued[0]) if queued else None


def window_until(root: Path, at: datetime | None = None) -> datetime | None:
    """The end of the granted GPU window, if one is open now."""
    path = runner_dir(root) / "window.json"
    try:
        until = datetime.fromisoformat(json.loads(path.read_text(encoding="utf-8"))["until"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if until.tzinfo is None:
        until = until.astimezone()
    return until if until > (at or now()) else None


def on_mains_power() -> bool:
    """True on AC (or where pmset doesn't exist, as off the Mac)."""
    try:
        r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return True
    return "Battery Power" not in r.stdout


def notify(text: str) -> None:
    """A macOS notification (nothing elsewhere)."""
    if sys.platform != "darwin":
        return
    safe = text.replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{safe}" with title "Copyist runner"'],
                   capture_output=True, timeout=10)


def write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)


def heartbeat(root: Path, job: str | None, note: str = "") -> None:
    write_json(runner_dir(root) / "heartbeat.json",
               {"pid": os.getpid(), "time": now().isoformat(timespec="seconds"), "job": job, "note": note})


def why_not(job: Job, root: Path, power=on_mains_power) -> str | None:
    """Why a job can't start now (None when it can)."""
    if job.gpu:
        if window_until(root) is None:
            return "waiting for a GPU window"
        if not power():
            return "waiting for mains power"
    return None


def command(script: Path) -> list[str]:
    cmd = ["/bin/bash", str(script)]
    if shutil.which("caffeinate"):
        cmd = ["caffeinate", "-i", *cmd]
    return cmd


def run_job(job: Job, root: Path, notify_fn=notify) -> dict:
    """Run one job to the end (or its limit), filing the script, log and result."""
    f = folders(root)
    running = f["running"] / job.path.name
    shutil.move(str(job.path), running)
    log = f["logs"] / f"{job.name}.log"
    limit = job.hours * 3600
    if job.gpu:
        until = window_until(root)
        if until is not None:
            limit = min(limit, (until - now()).total_seconds())
    started = now()
    notify_fn(f"Started {job.name}" + (" (GPU)" if job.gpu else ""))
    stopped = None
    with open(log, "w", encoding="utf-8") as out:
        out.write(f"# {job.name} started {started.isoformat(timespec='seconds')} "
                  f"(gpu={job.gpu}, limit {limit / 3600:.2f} h)\n")
        out.flush()
        proc = subprocess.Popen(command(running), cwd=root, stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True,
                                env={**os.environ, "COPYIST_ROOT": str(root), "COPYIST_RUNNER_JOB": job.name})
        deadline = time.monotonic() + limit
        while True:
            heartbeat(root, job.name)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                stopped = "time limit" if not job.gpu or window_until(root) else "window ended"
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(GRACE_SECONDS)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                break
            try:
                proc.wait(timeout=min(POLL_SECONDS, remaining))
                break
            except subprocess.TimeoutExpired:
                continue
    finished = now()
    result = {"job": job.name, "exit": proc.returncode, "gpu": job.gpu, "stopped": stopped,
              "started": started.isoformat(timespec="seconds"), "finished": finished.isoformat(timespec="seconds"),
              "seconds": round((finished - started).total_seconds(), 1)}
    shutil.move(str(running), f["done"] / job.path.name)
    write_json(f["done"] / f"{job.name}.json", result)
    word = "finished" if proc.returncode == 0 and not stopped else f"stopped ({stopped})" if stopped else "failed"
    notify_fn(f"{job.name} {word}")
    return result


def run_once(root: Path, notify_fn=notify, power=on_mains_power) -> dict | None:
    """Start the next job if it can start; returns its result, or None when nothing ran."""
    job = next_job(root)
    if job is None:
        heartbeat(root, None, "idle")
        return None
    reason = why_not(job, root, power)
    if reason:
        heartbeat(root, None, f"{job.name}: {reason}")
        return None
    return run_job(job, root, notify_fn)


def recover(root: Path) -> None:
    """A job left in running/ by a runner that died goes back to the front of the queue."""
    f = folders(root)
    for script in f["running"].glob("*.sh"):
        shutil.move(str(script), f["queue"] / script.name)


def main() -> int:
    root = root_dir()
    stop = runner_dir(root) / "STOP"
    recover(root)
    stop.unlink(missing_ok=True)
    print(f"Copyist runner: watching {runner_dir(root) / 'queue'} (Ctrl-C to stop).", flush=True)
    notify("Runner started")
    try:
        while not stop.exists():
            result = run_once(root)
            if result:
                print(json.dumps(result), flush=True)
            else:
                time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        pass
    heartbeat(root, None, "stopped")
    print("Copyist runner stopped.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
