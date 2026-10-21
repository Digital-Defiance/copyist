"""Measure where Copyist's time goes on this machine, and what batching and parallel work buy
(docs/hardware.md). One unattended run, for one GPU window: about 10-15 minutes on an M4 Max.

    caffeinate -i python scripts/hardware/bench.py [--max-minutes 30] [--skip yue,plan,demucs,...]

On a Mac it keeps the machine awake itself and waits on battery until it's plugged in again, as the
GPU-window rules ask (AGENTS.md). Unload LM Studio's models first (`lms unload --all`); the run
records what was loaded. Every step is skipped, with the reason, when its tool isn't installed, so it
also runs on Linux or Windows (CUDA, Vulkan or CPU builds of yue2.cpp; Demucs on CUDA or CPU).

Steps (the GPU ones first, so a short window still gets the answers that matter most):
- yue:    one take, then 2 and 4 takes in one run (`lm_batch_size`), then 4 variations of one take
          (`synth_batch_size`), and whether take 2 of a batch is the same performance as that take
          rendered alone; on a Mac, each run's peak memory (`/usr/bin/time -l`);
- plan:   four melody plans with `yue-plan`, one run each, as `copyist write` makes them;
- demucs: separating a take's vocal on the GPU and on the CPU;
- whisper: hearing the words (faster-whisper base.en on the CPU, as Copyist does now);
- pyin:   pitch tracking the vocal on one core;
- band:   the band's parts rendered one at a time and side by side;
- steps:  one take's performance re-rendered from its codes at 32, 16, 12 and 8 flow-matching steps
          (yue2.cpp's `steps`; the render is most of a take's time), each checked automatically:
          its sound against the 32-step render, the melody (`copyist follow`'s pitch check) and the
          words (Whisper); plus Demucs on the GPU twice (cold, then warm) against the CPU.

`--only steps` runs just that one (about 5 minutes on the Mac).

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

STEPS = ("yue", "plan", "demucs", "whisper", "pyin", "band", "steps")
FLOW_STEPS = (32, 16, 12, 8)
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


def semantic_tokens(replay: Path) -> str | None:
    """The performance yue2.cpp drew (its replay request's codes), to compare takes by content."""
    try:
        return json.loads(replay.read_text(encoding="utf-8")).get("semantic_tokens") or None
    except (OSError, ValueError):
        return None


def timed_synth(work: Path, real: str) -> tuple[str, Path] | None:
    """On a Mac, a stand-in for yue-synth that runs it under /usr/bin/time -l, appending each run's
    resource use to a log, so the peak memory of every YuE2 run is recorded."""
    if sys.platform != "darwin" or not Path("/usr/bin/time").exists():
        return None
    log = work / "yue-synth-time.log"
    wrapper = work / "yue-synth-timed"
    wrapper.write_text(f'#!/bin/sh\nexec /usr/bin/time -a -o "{log}" -l "{real}" "$@"\n', encoding="utf-8")
    wrapper.chmod(0o755)
    return str(wrapper), log


def last_peak_gb(log: Path | None) -> dict:
    """The last run's peak memory footprint and maximum resident set from the /usr/bin/time log."""
    if not log or not log.is_file():
        return {}
    text = log.read_text(encoding="utf-8", errors="replace")
    out = {}
    for key, label in (("peak_footprint_gb", "peak memory footprint"), ("max_rss_gb", "maximum resident set size")):
        values = [int(line.split()[0]) for line in text.splitlines() if line.strip().endswith(label)]
        if values:
            out[key] = round(values[-1] / 2 ** 30, 2)
    return out


# ------------------------------------------------------------------ steps

def step_yue(work: Path, results: dict) -> Path | None:
    from copyist import paths, yue
    from copyist.song import load_song
    real = paths.find_program("yue-synth", "COPYIST_YUE_SYNTH")
    if not real:
        results["yue"] = {"skipped": "yue2.cpp isn't installed (scripts/setup-yue.sh)"}
        return None
    song = load_song(SONG)
    req = yue.request(song, verses=1, seed=831001)
    req["output_format"] = "wav16"
    r = results["yue"] = {"audio_seconds": round(yue.score_seconds(song, 1, 4), 1)}
    (work / "yue").mkdir(parents=True, exist_ok=True)
    wrapped = timed_synth(work / "yue", str(real))
    before = os.environ.get("COPYIST_YUE_SYNTH")
    if wrapped:
        os.environ["COPYIST_YUE_SYNTH"] = wrapped[0]
    log = wrapped[1] if wrapped else None
    try:
        r["one_take_s"], (first,) = timed(yue.render_takes, req, [work / "yue" / "one"])
        r["one_take_memory"] = last_peak_gb(log)
        r["two_takes_s"], _ = timed(yue.render_takes, req, [work / "yue" / f"two-{k}" for k in (1, 2)])
        r["two_takes_memory"] = last_peak_gb(log)
        r["four_takes_s"], four = timed(yue.render_takes, req, [work / "yue" / f"four-{k}" for k in (1, 2, 3, 4)])
        r["four_takes_memory"] = last_peak_gb(log)
        # A batch leaves each take yue2.cpp's replay request; the one-at-a-time fallback doesn't.
        r["four_takes_batched"] = all((work / "yue" / f"four-{k}" / "replay.json").is_file() for k in (1, 2, 3, 4))
        # Four variations of one performance: yue-synth numbers them production00 ... production03.
        folder = work / "yue" / "variations"
        t0 = time.perf_counter()
        try:
            yue.run_yue2cpp(dict(req, synth_batch_size=4), folder)
        except RuntimeError:
            pass                       # it looks for one production.wav; check the numbered ones
        r["four_variations_s"] = round(time.perf_counter() - t0, 2)
        r["four_variations_ok"] = all((folder / f"production0{j}.wav").is_file() for j in range(4))
        r["four_variations_memory"] = last_peak_gb(log)
        # Take 2 of the batch, rendered alone: the same performance? (Then a failed batch's fallback is too.)
        t, alone = timed(yue.run_yue2cpp, yue.take_request(req, 1), work / "yue" / "alone-2")
        r["take_2_alone_s"] = t
        batch_codes = semantic_tokens(four[1].parent / "replay.json")
        alone_codes = semantic_tokens(alone.with_suffix(".json"))
        r["take_2_same_performance"] = bool(batch_codes) and batch_codes == alone_codes
        r["take_2_same_audio_bytes"] = digest(alone) == digest(four[1])
    finally:
        os.environ.pop("COPYIST_YUE_SYNTH", None)
        if before is not None:
            os.environ["COPYIST_YUE_SYNTH"] = before
    for key, n in (("two_takes_s", 2), ("four_takes_s", 4)):
        r[key.replace("_s", "_per_take_s")] = round(r[key] / n, 2)
    r["four_in_one_run_vs_four_runs"] = round(r["four_takes_s"] / (4 * r["one_take_s"]), 2)
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


def mel_distance_db(a: Path, b: Path) -> float:
    """Mean absolute difference of two recordings' log-mel spectrograms, in dB (0 = the same)."""
    import librosa
    import numpy as np
    x, sr = librosa.load(str(a), sr=22050, mono=True)
    y, _ = librosa.load(str(b), sr=22050, mono=True)
    n = min(len(x), len(y))
    mx, my = (librosa.power_to_db(librosa.feature.melspectrogram(y=v[:n], sr=sr, n_mels=80), ref=1.0, top_db=None)
              for v in (x, y))
    return round(float(np.mean(np.abs(np.maximum(mx, -80) - np.maximum(my, -80)))), 2)


def melody_and_words(song, vocal: Path) -> dict:
    """The automatic checks Copyist runs on a take: notes on pitch (any octave, as `copyist follow`)
    and the share of the words Whisper hears, in order."""
    from copyist import hear, pitch, refit, sing, yue
    notes = sing.sung_notes(song, 1, pronunciations=song.pronunciations)
    checked = pitch.check(vocal, notes, offset=yue.verse_offset(song, 1, 4), search=3.0, any_octave=True)
    out = {"notes_on_pitch": round(sum(r.ok for r in checked) / max(len(checked), 1), 3)}
    if hear.available():
        expected = refit.plain_for_edit([song.verses[0]]).split()
        out["words_heard"] = round(hear.compare(expected, hear.heard_words(vocal))[0], 3)
    return out


def step_steps(work: Path, results: dict) -> None:
    """Fewer flow-matching steps: how much faster, and what it costs, checked automatically."""
    from copyist import paths, stems, yue
    from copyist.song import load_song
    if not paths.find_program("yue-synth", "COPYIST_YUE_SYNTH"):
        results["steps"] = {"skipped": "yue2.cpp isn't installed (scripts/setup-yue.sh)"}
        return
    if not stems.demucs_binary():
        results["steps"] = {"skipped": "Demucs isn't installed (scripts/setup-demucs.sh)"}
        return
    song = load_song(SONG)
    req = yue.request(song, verses=1, seed=831005)
    req["output_format"] = "wav16"
    r = results["steps"] = {}
    r["first_take_s"], ref = timed(yue.run_yue2cpp, req, work / "steps" / "take")
    replay = json.loads(ref.with_suffix(".json").read_text(encoding="utf-8"))
    rendered = {}
    for n in FLOW_STEPS:
        again = dict(replay, steps=n, output_format="wav16")
        t, audio = timed(yue.run_yue2cpp, again, work / "steps" / f"steps-{n}")
        rendered[n] = audio
        r[f"steps_{n}"] = {"render_s": t}
    # Demucs: the GPU cold and warm, then the CPU, on the same take.
    gpu = stems.demucs_device(stems.demucs_binary())
    r["demucs"] = {"device": gpu}
    r["demucs"]["gpu_first_s"], _ = timed(stems.split_vocals, ref, work / "steps" / "demucs-gpu-1", device=gpu)
    r["demucs"]["gpu_again_s"], _ = timed(stems.split_vocals, ref, work / "steps" / "demucs-gpu-2", device=gpu)
    r["demucs"]["cpu_s"], _ = timed(stems.split_vocals, ref, work / "steps" / "demucs-cpu", device="cpu")
    for n, audio in rendered.items():
        entry = r[f"steps_{n}"]
        entry["sound_vs_32_db"] = mel_distance_db(audio, rendered[FLOW_STEPS[0]])
        vocal, _ = stems.split_vocals(audio, work / "steps" / f"stems-{n}", device="cpu")
        entry.update(melody_and_words(song, vocal))
    # Two renders of the same codes at 32 steps should be the same: the floor the others are measured against.
    r["steps_32_again_vs_32_db"] = mel_distance_db(ref, rendered[FLOW_STEPS[0]])


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
    ap.add_argument("--only", default="", help="comma-separated steps to run, skipping the rest")
    ap.add_argument("--out", default=str(ROOT / "out" / "hardware"))
    args = ap.parse_args(argv)
    if sys.platform == "darwin" and not os.environ.get("COPYIST_BENCH_AWAKE") and shutil.which("caffeinate"):
        env = dict(os.environ, COPYIST_BENCH_AWAKE="1")
        return subprocess.run(["caffeinate", "-i", sys.executable, *sys.argv], env=env).returncode
    deadline = time.time() + args.max_minutes * 60
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    if only:
        skip |= set(STEPS) - only
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out = Path(args.out)
    work = out / f"bench-{stamp}"
    work.mkdir(parents=True, exist_ok=True)
    results: dict = {"when": stamp, "machine": machine()}
    take = vocals = None
    plan = [("yue", lambda: step_yue(work, results)), ("plan", lambda: step_plan(work, results)),
            ("demucs", lambda: step_demucs(work, results, take)), ("whisper", lambda: step_whisper(results, vocals)),
            ("pyin", lambda: step_pyin(results, vocals)), ("band", lambda: step_band(work, results)),
            ("steps", lambda: step_steps(work, results))]
    for name, fn in plan:
        if name in skip:
            if not only:
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
