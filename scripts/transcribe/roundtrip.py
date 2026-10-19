"""Round-trip transcription eval: known score → (YuE2) recording → open engine → score F1.

This is the measurable loop for improving `copyist transcribe`. Owner songs without a written
score are out of scope here; use evaluate.py --sung for those.

Usage:
  python scripts/transcribe/roundtrip.py              # all truth takes that have stems
  python scripts/transcribe/roundtrip.py --only saints
  python scripts/transcribe/roundtrip.py --write out/roundtrip.md

Each case needs a song YAML (truth) and a recording (YuE2 take or band). Vocals/accompaniment
stems are reused when present; otherwise Demucs runs once into the case's stem folder.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from copyist import syllables, transcribe as tr  # noqa: E402
from copyist.song import load_song  # noqa: E402

# librosa/numba often print these on short stems; they are not transcription failures.
warnings.filterwarnings("ignore", message="Empty filters detected in mel frequency basis")
warnings.filterwarnings("ignore", category=RuntimeWarning, module=r"numba(\.|$)")


def _load_evaluate():
    spec = importlib.util.spec_from_file_location("tr_eval", ROOT / "scripts/transcribe/evaluate.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@dataclass
class Case:
    name: str
    song: Path
    mix: Path
    vocals: Path
    accompaniment: Path
    lyrics: Path | None = None


CASES = [
    Case("saints",
         ROOT / "songs/when-the-saints.yaml",
         ROOT / "out/when-the-saints/takes/truth/production.wav",
         ROOT / "out/when-the-saints-go-marching-in/transcribe/stems/htdemucs/source/vocals.wav",
         ROOT / "out/when-the-saints-go-marching-in/transcribe/stems/htdemucs/source/no_vocals.wav",
         ROOT / "out/when-the-saints-go-marching-in/transcribe/lyrics.txt"),
    Case("silent-night",
         ROOT / "songs/silent-night.yaml",
         ROOT / "out/silent-night/takes/truth/production.wav",
         ROOT / "out/silent-night/transcribe/stems/htdemucs/source/vocals.wav",
         ROOT / "out/silent-night/transcribe/stems/htdemucs/source/no_vocals.wav",
         ROOT / "out/silent-night/transcribe/lyrics.txt"),
    Case("amazing-grace",
         ROOT / "songs/amazing-grace.yaml",
         ROOT / "out/amazing-grace/production/production.wav",
         ROOT / "out/amazing-grace/production/htdemucs/production/vocals.wav",
         ROOT / "out/amazing-grace/production/htdemucs/production/no_vocals.wav",
         None),
    Case("tyger",
         ROOT / "songs/the-tyger.yaml",
         ROOT / "out/the-tyger/takes/truth/production.wav",
         ROOT / "out/the-tyger/takes/truth/htdemucs/production/vocals.wav",
         ROOT / "out/the-tyger/takes/truth/htdemucs/production/no_vocals.wav",
         None),
    # Large patter stress case (~128 notes). Produce first:
    #   copyist produce songs/major-general.yaml --take truth --device MTL0
    Case("major-general",
         ROOT / "songs/major-general.yaml",
         ROOT / "out/major-general/takes/truth/production.wav",
         ROOT / "out/major-general/takes/truth/htdemucs/production/vocals.wav",
         ROOT / "out/major-general/takes/truth/htdemucs/production/no_vocals.wav",
         None),
]


def ensure_stems(case: Case, device: str | None) -> tuple[Path, Path]:
    """Vocals + accompaniment on disk; Demucs into the accompaniment's parent if needed."""
    from copyist import stems as stems_mod
    if case.vocals.is_file() and case.accompaniment.is_file():
        return case.vocals, case.accompaniment
    if not case.mix.is_file():
        raise FileNotFoundError(f"{case.name}: missing mix {case.mix}")
    # split_vocals writes <out_dir>/htdemucs/<mix.stem>/{vocals,no_vocals}.wav
    out_dir = case.vocals.parent.parent.parent if case.vocals.parent.name == case.mix.stem else case.mix.parent
    v, a = stems_mod.split_vocals(case.mix, out_dir, device=device)
    return v, a


def lyric_count(case: Case) -> int | None:
    """Melody-note target for the open engine: syllables plus `_` holds (Silent Night 46, not 41).

    Prefer the song's fitted `slots_available` when the verse fits; else tokenize the lyric text.
    """
    from copyist import lyrics as lyr
    song = load_song(case.song)
    if song.lyric_fits and song.lyric_fits[0].fits:
        return song.lyric_fits[0].slots_available
    if case.lyrics and case.lyrics.is_file():
        text = case.lyrics.read_text(encoding="utf-8")
    else:
        # First verse only (YuE2 truth takes are one verse).
        block = song.verses[0] if song.verses else ""
        text = block if isinstance(block, str) else "\n".join(block)
    if not text.strip():
        return None
    return lyr.note_target(text)


def run_case(case: Case, ev, device: str | None, engine: str = "open") -> dict:
    if not case.song.is_file() or not case.mix.is_file():
        return {"name": case.name, "ok": False, "error": "missing song or mix"}
    try:
        vocals, acc = ensure_stems(case, device)
    except Exception as e:
        return {"name": case.name, "ok": False, "error": str(e)}
    syl = lyric_count(case)
    stems = tr.stems_from_files(case.mix, vocals, acc)
    try:
        if engine == "neural":
            draft = tr.draft_neural(stems, vocals, syllables=syl)
        else:
            draft = tr.draft(stems, syllables=syl)
    except Exception as e:
        return {"name": case.name, "ok": False, "error": f"draft: {e}"}
    abc_path = Path(f"/tmp/copyist-roundtrip-{case.name}.abc")
    abc_path.write_text(draft.abc, encoding="utf-8")
    tn, tc, spq = ev.truth(case.song)
    notes, chords, plan = ev.transcribed(draft.abc)
    f, shift, ratio = ev.best_alignment(tn, notes, spq, True)
    f, p, r, hits, offs = ev.match(tn, notes, spq, True, shift, ratio)
    end = tn[-1][0] + tn[-1][1]
    ch = ev.chord_accuracy(tc, chords, shift, ratio, end) if tc and chords else float("nan")
    return {
        "name": case.name,
        "ok": True,
        "meter": draft.meter,
        "key": draft.key,
        "tempo": draft.tempo,
        "n_notes": len(notes),
        "n_true": len(tn),
        "note_f1": f,
        "precision": p,
        "recall": r,
        "chords": ch,
        "shift": shift,
        "ratio": ratio,
        "abc": str(abc_path),
    }


def format_table(rows: list[dict]) -> str:
    lines = [
        "| Case | meter/key/tempo | notes (vs true) | note F1 (P/R) | chords |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        if not row.get("ok"):
            lines.append(f"| {row['name']} | — | — | ERROR: {row.get('error', '?')} | — |")
            continue
        ch = f"{row['chords']:.2f}" if row["chords"] == row["chords"] else "—"
        lines.append(
            f"| {row['name']} | {row['meter']} {row['key']} ~{row['tempo']} | "
            f"{row['n_notes']} vs {row['n_true']} | "
            f"{row['note_f1']:.2f} ({row['precision']:.2f}/{row['recall']:.2f}) | {ch} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", help="case names to run (default: all available)")
    ap.add_argument("--write", type=Path, help="write the markdown table here")
    ap.add_argument("--device", default=None, help="Demucs device if stems must be built")
    ap.add_argument("--engine", choices=("open", "neural"), default="open", help="transcription engine")
    args = ap.parse_args(argv)
    want = set(args.only) if args.only else None
    cases = [c for c in CASES if want is None or c.name in want]
    ev = _load_evaluate()
    rows = []
    for case in cases:
        print(f"… {case.name}", flush=True)
        rows.append(run_case(case, ev, args.device, engine=args.engine))
        if rows[-1].get("ok"):
            r = rows[-1]
            print(f"  note F1 {r['note_f1']:.2f}  chords {r['chords']:.2f}  "
                  f"{r['n_notes']} vs {r['n_true']}  {r['meter']} {r['key']} ~{r['tempo']}", flush=True)
        else:
            print(f"  FAIL {rows[-1].get('error')}", flush=True)
    table = format_table(rows)
    print()
    print(table)
    if args.write:
        args.write.write_text("# Transcription round-trip (open engine vs written score)\n\n" + table, encoding="utf-8")
        print(f"Wrote {args.write}")
    # Non-zero if any case failed hard; soft quality gates stay informational.
    return 0 if all(r.get("ok") for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
