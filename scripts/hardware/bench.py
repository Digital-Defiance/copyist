"""Measure where Copyist's time goes on this machine, and what batching and parallel work buy
(docs/hardware.md). One unattended run, for one GPU window: about 10-15 minutes on an M4 Max.

    caffeinate -i python scripts/hardware/bench.py [--max-minutes 30] [--skip yue,plan,demucs,...]

On a Mac it keeps the machine awake itself and waits on battery until it's plugged in again, as the
GPU-window rules ask (AGENTS.md). Unload LM Studio's models first (`lms unload --all`); the run
records what was loaded. Every step is skipped, with the reason, when its tool isn't installed, so it
also runs on Linux or Windows (CUDA, Vulkan or CPU builds of yue2.cpp; Demucs on CUDA or CPU).

Steps (the GPU ones first, so a short window still gets the answers that matter most):
- yue:    one take, then 2 and 4 takes in one run (`lm_batch_size`), then 4 variations of one take
          (`synth_batch_size`), and whether take 2 of a batch is the same as that take rendered alone;
- plan:   four melody plans with `yue-plan`, one run each, as `copyist write` makes them;
- demucs: separating a take's vocal on the GPU and on the CPU;
- whisper: hearing the words (faster-whisper base.en on the CPU, as Copyist does now);
- pyin:   pitch tracking the vocal on one core;
- band:   the band's parts rendered one at a time and side by side.

Writes out/hardware/bench-<time>.json and .md.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

STEPS = ("yue", "plan", "demucs", "whisper", "pyin", "band")
SONG = ROOT / "songs" / "amazing-grace.yaml"


def run(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def machine() -> dict:
    from copyist import compute
    info = {"platform": platform.platform(), "python": platform.python_version(), "cpus": os.cpu_count(),
            "performance_cores": compute.performance_cores()}
    if sys.platform == "darwin":
        info["chip"] = run(["sysctl", "-n", "machdep.cpu.brand_string"])
        info["memory_gb"] = round(int(run(["sysctl", "-n", "hw.memsize"]) or 0) / 2 ** 30)
        info["efficiency_cores"] = run(["sysctl", "-n", "hw.perflevel1.physicalcpu"])
        info["gpu_cores"] = run(["sh", "-c", "system_profiler SPDisplaysDataType | grep -i 'cores' | head -1"])
    if shutil.which("nvidia-smi"):
        info["nvidia"] = run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
    if shutil.which("lms"):
        info["lm_studio_loaded"] = run(["lms", "ps"])
    return info


def on_battery() -> bool:
    return sys.platform == "darwin" and "Battery Power" in run(["pmset", "-g", "batt"])


def wait_for_power(deadline: float) -> bool:
    """Wait on battery until the Mac is plugged in again; False if the window ran out first."""
    told = False
    while on_battery():
        if time.time() > deadline:
            return False
        if not told:
            print("On battery: waiting for power before the next step.", flush=True)
            told = True
        time.sleep(60)
    return True


def timed(fn, *a, **kw) -> tuple[float, object]:
    t0 = time.perf_counter()
    out = fn(*a, **kw)
    return round(time.perf_counter() - t0, 2), out


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


# ------------------------------------------------------------------ steps

def step_yue(work: Path, results: dict) -> Path | None:
    from copyist import paths, yue
    from copyist.song import load_song
    if not paths.find_program("yue-synth", "COPYIST_YUE_SYNTH"):
        results["yue"] = {"skipped": "yue2.cpp isn't installed (scripts/setup-yue.sh)"}
        return None
    song = load_song(SONG)
    req = yue.request(song, verses=1, seed=831001)
    req["output_format"] = "wav16"
    r = results["yue"] = {"audio_seconds": round(yue.score_seconds(song, 1, 4), 1)}
    r["one_take_s"], (first,) = timed(yue.render_takes, req, [work / "yue" / "one"])
    r["two_takes_s"], _ = timed(yue.render_takes, req, [work / "yue" / f"two-{k}" for k in (1, 2)])
    r["four_takes_s"], four = timed(yue.render_takes, req, [work / "yue" / f"four-{k}" for k in (1, 2, 3, 4)])
    # A batch leaves each take yue2.cpp's replay request; the one-at-a-time fallback doesn't.
    r["four_takes_batched"] = all((work / "yue" / f"four-{k}" / "replay.json").is_file() for k in (1, 2, 3, 4))
    variations = dict(req, synth_batch_size=4)
    t, _ = timed(yue.run_yue2cpp, variations, work / "yue" / "variations")
    r["four_variations_s"] = t
    # Take 2 of the batch, rendered alone: the same take? (Then a failed batch's fallback is too.)
    t, alone = timed(yue.run_yue2cpp, yue.take_request(req, 1), work / "yue" / "alone-2")
    r["take_2_alone_s"] = t
    r["take_2_same_as_batch"] = digest(alone) == digest(four[1])
    for key in ("two_takes_s", "four_takes_s"):
        n = 2 if key.startswith("two") else 4
        r[key.replace("_s", "_per_take_s")] = round(r[key] / n, 2)
    return first


def step_plan(work: Path, results: dict) -> None:
    from copyist import paths, write
    if not paths.find_program("yue-plan", "COPYIST_YUE_PLAN"):
        results["plan"] = {"skipped": "yue2.cpp's planner isn't installed (scripts/setup-yue.sh)"}
        return
    lyrics = "Amazing grace, how sweet the sound\nThat saved a wretch like me\n" \
             "I once was lost, but now am found\nWas blind but now I see"
    line = write.style_line("waltz", None, "alto")
    times = []
    for seed in (11, 12, 13, 14):
        t, _ = timed(write.run_planner, write.planner_request(lyrics, line, seed), work / "plan" / str(seed))
        times.append(t)
    results["plan"] = {"each_s": times, "four_s": round(sum(times), 2)}


def step_demucs(work: Path, results: dict, take: Path | None) -> Path | None:
    from copyist import stems
    if not take:
        results["demucs"] = {"skipped": "no take to separate (the yue step didn't run)"}
        return None
    binary = stems.demucs_binary()
    if not binary:
        results["demucs"] = {"skipped": "Demucs isn't installed (scripts/setup-demucs.sh)"}
        return None
    r = results["demucs"] = {"device": stems.demucs_device(binary)}
    t, (vocals, _) = timed(stems.split_vocals, take, work / "demucs-gpu", device=r["device"])
    r["gpu_s"] = t
    r["cpu_s"], _ = timed(stems.split_vocals, take, work / "demucs-cpu", device="cpu")
    return vocals


def step_whisper(results: dict, vocals: Path | None) -> None:
    from copyist import hear
    if not vocals:
        results["whisper"] = {"skipped": "no vocal (the demucs step didn't run)"}
    elif not hear.available():
        results["whisper"] = {"skipped": "faster-whisper isn't installed"}
    else:
        t, words = timed(hear.heard_words, vocals)
        results["whisper"] = {"base_en_cpu_s": t, "words": len(words)}


def step_pyin(results: dict, vocals: Path | None) -> None:
    from copyist import pitch
    if not vocals:
        results["pyin"] = {"skipped": "no vocal (the demucs step didn't run)"}
        return
    t, _ = timed(pitch.track, vocals)
    results["pyin"] = {"one_core_s": t}


def step_band(work: Path, results: dict) -> None:
    from copyist import arrange, render
    from copyist.song import load_song
    if not render.sfizz_program():
        results["band"] = {"skipped": "sfizz isn't installed (scripts/setup-sfizz.sh)"}
        return
    song = load_song(SONG)
    band = arrange.arrange_band(song)
    midi = work / "band" / "band.mid"
    midi.parent.mkdir(parents=True, exist_ok=True)
    band.performance().write("midi", fp=str(midi))
    r = results["band"] = {}
    before = os.environ.get("COPYIST_JOBS")
    try:
        for key, jobs in (("one_at_a_time_s", "1"), ("side_by_side_s", None)):
            os.environ.pop("COPYIST_JOBS", None)
            if jobs:
                os.environ["COPYIST_JOBS"] = jobs
            r[key], audio = timed(render.render_band, midi, work / "band" / f"{key}.wav", band.style)
            r["engine"] = audio.engine
    finally:
        os.environ.pop("COPYIST_JOBS", None)
        if before is not None:
            os.environ["COPYIST_JOBS"] = before


# ------------------------------------------------------------------ main

def report(results: dict) -> str:
    lines = [f"# Copyist on this machine ({results['when']})", ""]
    m = results["machine"]
    lines += [f"- {m.get('chip') or m['platform']}, {m.get('memory_gb', '?')} GB, "
              f"{m['performance_cores']} performance cores", ""]
    lines += ["| Step | Measured |", "|---|---|"]
    for step in STEPS:
        r = results.get(step)
        if r is None:
            continue
        text = r.get("skipped") or r.get("error") or ", ".join(f"{k} {v}" for k, v in r.items())
        lines.append(f"| {step} | {text} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--max-minutes", type=float, default=30, help="stop starting new steps after this (default 30)")
    ap.add_argument("--skip", default="", help="comma-separated steps to skip: " + ",".join(STEPS))
    ap.add_argument("--out", default=str(ROOT / "out" / "hardware"))
    args = ap.parse_args(argv)
    if sys.platform == "darwin" and not os.environ.get("COPYIST_BENCH_AWAKE") and shutil.which("caffeinate"):
        env = dict(os.environ, COPYIST_BENCH_AWAKE="1")
        return subprocess.run(["caffeinate", "-i", sys.executable, *sys.argv], env=env).returncode
    deadline = time.time() + args.max_minutes * 60
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(args.out)
    work = out / f"bench-{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    results: dict = {"when": stamp, "machine": machine()}
    take = vocals = None
    plan = [("yue", lambda: step_yue(work, results)), ("plan", lambda: step_plan(work, results)),
            ("demucs", lambda: step_demucs(work, results, take)), ("whisper", lambda: step_whisper(results, vocals)),
            ("pyin", lambda: step_pyin(results, vocals)), ("band", lambda: step_band(work, results))]
    for name, fn in plan:
        if name in skip:
            results[name] = {"skipped": "--skip"}
            continue
        if time.time() > deadline or not wait_for_power(deadline):
            results[name] = {"skipped": "the window ran out"}
            continue
        print(f"[bench] {name}...", flush=True)
        try:
            got = fn()
        except Exception as e:     # one step failing mustn't lose the others' numbers
            results[name] = {"error": f"{type(e).__name__}: {e}"[:500]}
            got = None
        if name == "yue":
            take = got
        elif name == "demucs":
            vocals = got
        (out / f"bench-{stamp}.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    (out / f"bench-{stamp}.md").write_text(report(results), encoding="utf-8")
    print(report(results))
    print(f"Wrote {out / f'bench-{stamp}.json'} and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
