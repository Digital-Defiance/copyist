"""Can you understand the words? Transcribe a sung vocal with Whisper and
compare what it heard with the lyrics (SPEC.md section 6).

Optional: needs `faster-whisper` (pip install faster-whisper). Without it the
check reports "not checked" instead of failing.
"""
from __future__ import annotations

import difflib
import importlib.util
import re
from pathlib import Path


def available() -> bool:
    return importlib.util.find_spec("faster_whisper") is not None


def normalise(words: list[str]) -> list[str]:
    return [re.sub(r"[^a-z']", "", w.lower().replace("’", "'")).strip("'") for w in words if w.strip()]


def heard_words(wav: Path, model: str = "base.en") -> list[str]:
    import librosa
    from faster_whisper import WhisperModel
    audio, _ = librosa.load(str(wav), sr=16000, mono=True)
    segments, _ = WhisperModel(model, device="cpu", compute_type="int8").transcribe(audio, beam_size=5)
    return [w for s in segments for w in s.text.split()]


def compare(expected: list[str], heard: list[str]) -> tuple[float, list[str]]:
    """(share of expected words heard, in order; the expected words that were missed)."""
    exp, got = normalise(expected), normalise(heard)
    matcher = difflib.SequenceMatcher(a=exp, b=got, autojunk=False)
    matched = sum(block.size for block in matcher.get_matching_blocks())
    missed = []
    for tag, a0, a1, _, _ in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            missed += exp[a0:a1]
    return (matched / len(exp) if exp else 1.0), missed


def report_lines(expected: list[str], wav: Path) -> list[str]:
    lines = ["## Lyric check", ""]
    if not available():
        return lines + ["Not checked: install `faster-whisper` to transcribe the vocal."]
    heard = heard_words(wav)
    share, missed = compare(expected, heard)
    lines.append(f"Whisper understood {share:.0%} of the words, in order.")
    lines.append("")
    lines.append(f"Heard: “{' '.join(heard)}”")
    if missed:
        lines += ["", "Missed or misheard: " + ", ".join(f"“{w}”" for w in missed)]
    return lines
