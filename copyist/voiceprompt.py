"""Make a singer "voice" for SoulX-Singer from a recording (docs/singing.md).

A voice is a short clip (10 to 30 seconds) of one person singing, plus
metadata describing it in SoulX-Singer's format: the words, the notes each
word is sung on, and the pitch curve. SoulX-Singer's own preprocessing does
this with several large models; this is a lighter version built from pYIN
(pitch) and Whisper (word timings), good enough for a reference clip.

Voices live in `voices/`, which git ignores: they are personal material and
never part of the published project.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from .sing import CONTINUE, ONSET, REST, phones_for

SR = 24000
HOP = 480            # SoulX-Singer's frame: 20 ms at 24 kHz
FRAME = HOP / SR


@dataclass
class Word:
    text: str
    start: float
    end: float


def load_clip(path: Path, start: float, end: float):
    """The clip as mono 24 kHz float samples."""
    import librosa
    y, _ = librosa.load(str(path), sr=SR, mono=True, offset=start, duration=end - start)
    return y


def pitch_track(y):
    """f0 in Hz per 20 ms frame (0 where unvoiced)."""
    import librosa
    import numpy as np
    f0, voiced, _ = librosa.pyin(y, fmin=65.0, fmax=1100.0, sr=SR, frame_length=2048, hop_length=HOP)
    f0 = np.where(voiced & ~np.isnan(f0), f0, 0.0)
    return f0


def phrases(y, min_gap: float = 0.35, min_len: float = 0.8) -> list[tuple[float, float]]:
    """Stretches of singing separated by at least `min_gap` seconds of quiet."""
    import librosa
    import numpy as np
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=HOP)[0]
    loud = rms > max(float(np.percentile(rms, 70)) * 0.12, 1e-4)
    spans, start, quiet = [], None, 0
    for i, on in enumerate(loud):
        if on:
            if start is None:
                start = i
            quiet = 0
        elif start is not None:
            quiet += 1
            if quiet * FRAME >= min_gap:
                end = i - quiet + 1
                if (end - start) * FRAME >= min_len:
                    spans.append((start * FRAME, end * FRAME))
                start, quiet = None, 0
    if start is not None and (len(loud) - start) * FRAME >= min_len:
        spans.append((start * FRAME, len(loud) * FRAME))
    return spans


def best_window(y, target: tuple[float, float] = (12.0, 22.0)) -> tuple[float, float]:
    """The first run of whole phrases lasting between target[0] and target[1] seconds."""
    spans = phrases(y)
    for i in range(len(spans)):
        for j in range(i, len(spans)):
            length = spans[j][1] - spans[i][0]
            if length > target[1]:
                break
            if length >= target[0]:
                return max(0.0, spans[i][0] - 0.2), spans[j][1] + 0.2
    return (0.0, min(len(y) / SR, target[1]))


def transcribe_words(y, lyrics_hint: str | None = None) -> list[Word]:
    """Word timings from Whisper (faster-whisper)."""
    from faster_whisper import WhisperModel
    import librosa
    audio16 = librosa.resample(y, orig_sr=SR, target_sr=16000)
    model = WhisperModel("base.en", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio16, beam_size=5, word_timestamps=True,
                                   initial_prompt=lyrics_hint, vad_filter=False)
    return [Word(w.word.strip(), float(w.start), float(w.end)) for s in segments for w in s.words if w.word.strip()]


def to_midi(hz: float) -> float:
    return 69 + 12 * math.log2(hz / 440.0)


def clean_hint(text: str, max_chars: int = 400) -> str | None:
    """Lyric lines only (no [Section] tags, (directions) or markdown), for Whisper's prompt."""
    lines = []
    for line in text.splitlines():
        line = line.strip().lstrip("#>*- ").strip()
        if not line or line.startswith(("[", "(")) or line.endswith((")", "]")):
            continue
        lines.append(re.sub(r"[^\w' ,.!?-]", "", line))
    return " ".join(lines)[:max_chars] or None


def word_text(text: str) -> str:
    return re.sub(r"[^A-Za-z']", "", text.replace("\u2019", "'")).strip("'") or ""


def smooth_contour(f0):
    """MIDI pitch per frame (nan where unvoiced): octave slips folded back, vibrato smoothed."""
    import numpy as np
    from scipy.signal import medfilt
    m = np.full(len(f0), np.nan)
    v = f0 > 0
    m[v] = 69 + 12 * np.log2(f0[v] / 440.0)
    if v.any():
        centre = float(np.median(m[v]))
        m[v & (m - centre > 9)] -= 12
        m[v & (centre - m > 9)] += 12
        filled = np.where(v, m, centre)
        sm = medfilt(filled, 9)
        m = np.where(v, sm, np.nan)
    return m


def split_notes(contour, a: int, b: int, min_frames: int = 5) -> list[tuple[int, int, int]]:
    """Notes (start frame, end frame, MIDI pitch) in frames a..b: runs of one rounded pitch."""
    import numpy as np
    runs: list[list[int]] = []   # [start, end, pitch]
    for i in range(a, b):
        if np.isnan(contour[i]):
            continue
        p = int(round(contour[i]))
        if runs and abs(contour[i] - runs[-1][2]) < 0.75:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1, p])
    merged: list[list[int]] = []
    for r in runs:
        # A blip joins the note before it, and so does the same pitch resuming
        # after a blip: one held note, not two.
        if merged and (r[1] - r[0] < min_frames or r[2] == merged[-1][2]):
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    if len(merged) > 1 and merged[0][1] - merged[0][0] < min_frames:
        merged[1][0] = merged[0][0]
        merged.pop(0)
    return [(s, e, p) for s, e, p in merged]


def build_metadata(y, words: list[Word], f0, index: str = "voice") -> dict:
    """SoulX-Singer metadata for a clip: one entry per note or silence."""
    import numpy as np
    contour = smooth_contour(f0)
    n_frames = len(f0)
    voiced_pitch = [int(round(x)) for x in contour if not np.isnan(x)]
    fallback = int(np.median(voiced_pitch)) if voiced_pitch else 60
    items: list[list] = []   # [text, phones, pitch, type, frames]
    t = 0
    for w in words:
        text = word_text(w.text)
        ph = phones_for(text) if text else None
        if not ph:
            continue
        a = max(t, int(round(w.start / FRAME)))
        b = min(n_frames, max(a + 1, int(round(w.end / FRAME))))
        if a >= n_frames:
            break
        if a > t:
            if items and items[-1][3] == REST:
                items[-1][4] += a - t
            else:
                items.append(["<SP>", "<SP>", 0, REST, a - t])
        notes = split_notes(contour, a, b)
        if not notes:
            prev = next((it[2] for it in reversed(items) if it[2]), fallback)
            items.append([text, ph, prev, ONSET, b - a])
        else:
            bounds = [a] + [s for s, _, _ in notes[1:]] + [b]
            for k, (_, _, pch) in enumerate(notes):
                items.append([text, ph, pch, ONSET if k == 0 else CONTINUE, max(1, bounds[k + 1] - bounds[k])])
        t = b
    if t < n_frames:
        items.append(["<SP>", "<SP>", 0, REST, n_frames - t])
    return {
        "index": index,
        "language": "English",
        "time": [0, round(n_frames * FRAME * 1000)],
        "duration": " ".join(f"{it[4] * FRAME:.2f}" for it in items),
        "text": " ".join(it[0] for it in items),
        "phoneme": " ".join(it[1] for it in items),
        "note_pitch": " ".join(str(it[2]) for it in items),
        "note_type": " ".join(str(it[3]) for it in items),
        "f0": " ".join(f"{h:.1f}" for h in f0),
    }


def make_voice(recording: Path, out_dir: Path, name: str, start: float | None = None,
               end: float | None = None, lyrics_hint: str | None = None) -> tuple[Path, Path, dict]:
    """Cut a clip, analyse it and write <name>.wav and <name>.json into out_dir."""
    import numpy as np
    import soundfile as sf
    if start is None or end is None:
        whole = load_clip(recording, 0, 120)
        s, e = best_window(whole)
        start, end = (start if start is not None else s), (end if end is not None else e)
    y = load_clip(recording, start, end)
    y = y / (float(np.max(np.abs(y))) or 1.0) * 0.9
    f0 = pitch_track(y)
    words = transcribe_words(y, clean_hint(lyrics_hint) if lyrics_hint else None)
    meta = build_metadata(y, words, f0, index=name)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav, js = out_dir / f"{name}.wav", out_dir / f"{name}.json"
    sf.write(str(wav), y, SR)
    js.write_text(json.dumps([meta], ensure_ascii=False, indent=1), encoding="utf-8")
    info = {"source": str(recording), "start": round(start, 2), "end": round(end, 2),
            "words": " ".join(w.text for w in words),
            "median_hz": round(float(np.median(f0[f0 > 0])), 1) if (f0 > 0).any() else None}
    return wav, js, info
