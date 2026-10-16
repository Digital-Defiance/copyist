"""Sung vocals: turn a Copyist voice part into input for a singing model,
run it, and check what comes back against the score (SPEC.md section 6).

First engine: SoulX-Singer (Apache-2.0), score-conditioned. Copyist already
knows every note's pitch, length and syllable, which is exactly what the
model needs. The model runs in its own Python environment, called as a
subprocess, so Copyist doesn't depend on PyTorch.

SoulX-Singer's English input works per word: a word sung across several
notes is repeated on each note, marked 2 on its first note and 3 on the
rest (both for extra syllables and for held notes); silences are "<SP>"
marked 1. Phonemes are ARPAbet with stress digits from the CMU dictionary,
written "en_" + phones joined by "-".
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pronouncing
from music21 import harmony, note, stream, tempo

from .song import Song, SongError

REST, ONSET, CONTINUE = 1, 2, 3

# Words the CMU dictionary lacks, mostly old contractions. Song files can add
# their own under `pronunciations:`.
PRONUNCIATIONS = {
    "'twas": "T W AH1 Z",
    "twas": "T W AH1 Z",
    "'tis": "T IH1 Z",
    "tis": "T IH1 Z",
    "o'er": "OW1 R",
    "e'er": "EH1 R",
    "ne'er": "N EH1 R",
}


@dataclass
class SungNote:
    start: float            # seconds from the start of the excerpt
    dur: float              # seconds
    midi: int               # 0 for silence
    kind: int               # REST, ONSET or CONTINUE
    word: str = "<SP>"
    phones: str = "<SP>"    # SoulX form, e.g. "en_AH0-M-EY1-Z-IH0-NG"
    bar: int | None = None
    beat: float | None = None


def clean_word(text: str) -> str:
    """Lowercase a sung word for dictionary lookup, keeping apostrophes ('twas)."""
    w = text.lower().replace("\u2019", "'").replace("\u2018", "'")
    return re.sub(r"[^a-z']", "", w)


def phones_for(word: str, extra: dict[str, str] | None = None) -> str | None:
    """CMU phones for a word in SoulX form, or None if unknown."""
    w = clean_word(word)
    table = {**PRONUNCIATIONS, **{k.lower(): v for k, v in (extra or {}).items()}}
    for candidate in (w, w.strip("'"), "'" + w.strip("'")):
        if candidate in table:
            return "en_" + "-".join(table[candidate].split())
        found = pronouncing.phones_for_word(candidate)
        if found:
            return "en_" + "-".join(found[0].split())
    return None


def seconds_per_quarter(song: Song) -> float:
    mm = song.melody.recurse().getElementsByClass(tempo.MetronomeMark).first()
    bpm = mm.getQuarterBPM() if mm is not None else 90.0
    return 60.0 / bpm


def bar_range(spec: str | None) -> tuple[int, int] | None:
    """"0-4" → (0, 4); None → None (the whole song)."""
    if not spec:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", spec)
    if not m:
        raise SongError(f"Bars should look like 1-8, not {spec!r}.")
    a = int(m.group(1))
    return a, int(m.group(2) or a)


def sung_notes(song: Song, verse: int = 1, bars: tuple[int, int] | None = None,
               pronunciations: dict[str, str] | None = None) -> list[SungNote]:
    """The notes a singer sings for one verse, with words, phonemes and timing."""
    if not 1 <= verse <= len(song.lyric_fits):
        raise SongError(f"{song.title} has {len(song.lyric_fits)} verse(s); there's no verse {verse}.")
    fit = song.lyric_fits[verse - 1]
    if not fit.fits:
        raise SongError(f"Verse {verse} doesn't fit the melody; run `copyist check` first.")

    words: dict[int, list] = {}
    for p in fit.placed:
        words.setdefault(p.word, []).append(p)
    role: dict[int, tuple] = {}
    unknown = []
    for w, sylls in words.items():
        text = "".join(s.text for s in sylls)
        ph = phones_for(text, pronunciations)
        if ph is None:
            unknown.append(re.sub(r"[^\w']", "", text))
            ph = "<SP>"
        display = re.sub(r"[^\w']", "", text.replace("’", "'"))
        for i, s in enumerate(sylls):
            role[id(s.note)] = (ONSET if i == 0 else CONTINUE, display, ph)
            for h in s.held:
                role[id(h)] = (CONTINUE, display, ph)
    if unknown:
        raise SongError("No pronunciation for: " + ", ".join(sorted(set(unknown))) +
                        ". Add them under `pronunciations:` in the song file, in CMU ARPAbet "
                        "(e.g. twas: T W AH1 Z).")

    spq = seconds_per_quarter(song)
    part = song.melody
    out: list[SungNote] = []
    t0 = None
    for el in part.recurse().notesAndRests:
        if isinstance(el, harmony.ChordSymbol):
            continue
        m = el.getContextByClass(stream.Measure)
        number = m.number if m is not None else None
        if bars and (number is None or not bars[0] <= number <= bars[1]):
            continue
        start_q = float(el.getOffsetInHierarchy(part))
        if t0 is None:
            t0 = start_q
        start, dur = (start_q - t0) * spq, el.quarterLength * spq
        if isinstance(el, note.Note) and el.tie is not None and el.tie.type in ("stop", "continue") and out:
            out[-1].dur += dur
            continue
        if isinstance(el, note.Note) and id(el) in role:
            kind, word, ph = role[id(el)]
            out.append(SungNote(start, dur, el.pitch.midi, kind, word, ph, number, float(el.beat)))
        else:  # a rest, or a note with no syllable in this verse
            if out and out[-1].kind == REST:
                out[-1].dur += dur
            else:
                out.append(SungNote(start, dur, 0, REST, bar=number, beat=float(el.beat)))
    if out and out[0].kind == CONTINUE:
        out[0].kind = ONSET  # an excerpt that starts mid-word
    return out


def soulx_segments(notes: list[SungNote], lead: float = 0.5, pad: float = 0.15,
                   target: float = 8.0, limit: float = 14.0) -> list[dict]:
    """Split notes into SoulX-Singer segments at word starts, about `target` seconds each.

    Times in the metadata are milliseconds on the output timeline, which starts
    `lead` seconds before the first note.
    """
    groups: list[list[SungNote]] = [[]]
    for n in notes:
        cur = groups[-1]
        length = (cur[-1].start + cur[-1].dur - cur[0].start) if cur else 0.0
        if cur and n.kind in (ONSET, REST) and (length >= target or length + n.dur > limit):
            groups.append([])
        groups[-1].append(n)
    # Fold a short last phrase into the one before it, if that still fits.
    if len(groups) > 1 and groups[-1] and groups[-2]:
        last, prev = groups[-1], groups[-2]
        if last[-1].start + last[-1].dur - last[0].start < 2.5 and \
                last[-1].start + last[-1].dur - prev[0].start <= limit:
            groups[-2] = prev + last
            groups.pop()
    segments = []
    for g in groups:
        while g and g[0].kind == REST:
            g = g[1:]
        while g and g[-1].kind == REST:
            g = g[:-1]
        if not g:
            continue
        start = lead + g[0].start - pad
        items = [("<SP>", "<SP>", 0, REST, pad)] + [(n.word, n.phones, n.midi, n.kind, n.dur) for n in g] + \
                [("<SP>", "<SP>", 0, REST, pad)]
        end = start + sum(i[4] for i in items)
        segments.append({
            "index": f"copyist_{round(start * 1000)}_{round(end * 1000)}",
            "language": "English",
            "time": [round(start * 1000), round(end * 1000)],
            "duration": " ".join(f"{i[4]:.3f}" for i in items),
            "text": " ".join(i[0] for i in items),
            "phoneme": " ".join(i[1] for i in items),
            "note_pitch": " ".join(str(i[2]) for i in items),
            "note_type": " ".join(str(i[3]) for i in items),
        })
    return segments


# ---------------------------------------------------------------- running SoulX-Singer

@dataclass
class SoulX:
    root: Path        # the SoulX-Singer checkout, with pretrained_models/ inside
    python: Path      # a Python with SoulX-Singer's requirements installed

    @classmethod
    def find(cls, root: str | None = None, python: str | None = None) -> "SoulX":
        root_s = root or os.environ.get("COPYIST_SOULX_DIR")
        if not root_s:
            raise SongError("Where is SoulX-Singer? Pass --soulx PATH or set COPYIST_SOULX_DIR "
                            "(see docs/singing.md).")
        r = Path(root_s).expanduser().resolve()
        py = python or os.environ.get("COPYIST_SOULX_PYTHON")
        if not py:
            for candidate in (r / ".venv/bin/python", r / "venv/bin/python", r.parent / "venv/bin/python"):
                if candidate.exists():
                    py = str(candidate)
                    break
        if not py:
            raise SongError(f"No Python environment found for SoulX-Singer in {r}. "
                            "Set COPYIST_SOULX_PYTHON (see docs/singing.md).")
        if not (r / "pretrained_models/SoulX-Singer/model.pt").exists():
            raise SongError(f"SoulX-Singer's model weights aren't in {r}/pretrained_models (see docs/singing.md).")
        return cls(r, Path(py))

    def example_voice(self) -> tuple[Path, Path]:
        """The English prompt that ships with SoulX-Singer, for testing only."""
        return self.root / "example/audio/en_prompt.mp3", self.root / "example/audio/en_prompt.json"

    def best_device(self) -> str:
        probe = ("import torch;print('cuda' if torch.cuda.is_available() else "
                 "'mps' if getattr(torch.backends,'mps',None) and torch.backends.mps.is_available() else 'cpu')")
        r = subprocess.run([str(self.python), "-c", probe], capture_output=True, text=True)
        return (r.stdout.strip() or "cpu") if r.returncode == 0 else "cpu"

    def sing(self, segments: list[dict], voice_wav: Path, voice_meta: Path, out_dir: Path,
             device: str = "auto") -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / "soulx-target.json"
        target.write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
        if device == "auto":
            device = self.best_device()
        work = out_dir / "soulx"
        cmd = [str(self.python), "-m", "cli.inference",
               "--device", device,
               "--model_path", "pretrained_models/SoulX-Singer/model.pt",
               "--config", "soulxsinger/config/soulxsinger.yaml",
               "--prompt_wav_path", str(Path(voice_wav).resolve()),
               "--prompt_metadata_path", str(Path(voice_meta).resolve()),
               "--target_metadata_path", str(target.resolve()),
               "--phoneset_path", "soulxsinger/utils/phoneme/phone_set.json",
               "--save_dir", str(work.resolve()),
               "--pitch_shift", "0",
               "--control", "score"]
        if device.startswith("cuda"):
            cmd.append("--fp16")
        env = {**os.environ, "PYTHONPATH": str(self.root)}
        if device == "mps":
            env.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        print(f"Singing {len(segments)} phrase(s) with SoulX-Singer on {device}...", file=sys.stderr)
        r = subprocess.run(cmd, cwd=self.root, env=env)
        if r.returncode != 0:
            raise RuntimeError(f"SoulX-Singer failed (exit {r.returncode}). Its output is above.")
        wav = out_dir / "vocal.wav"
        shutil.move(str(work / "generated.wav"), wav)
        return wav
