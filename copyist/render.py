"""The score as audio: each part on its sampled instrument, mixed (docs/sound-set.md).

`render_band` splits the arrangement's MIDI into its parts (melody, piano,
bass, drums), plays each one through sfizz with its sampled instrument, and
mixes them (copyist/mixdown.py), keeping each part as a stem. When sfizz or the
instruments aren't installed yet, it falls back to the GeneralUser GS
SoundFont through TinySoundFont, which is exact but sounds like old MIDI, and
says so.
"""
from __future__ import annotations

import subprocess
import tempfile
import urllib.request
import wave
from dataclasses import dataclass, field
from pathlib import Path

SOUNDFONT_URL = "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2"
SOUNDFONT_NAME = "GeneralUser-GS.sf2"
DRUM_CHANNEL = 9


class AudioUnavailable(RuntimeError):
    """TinySoundFont isn't installed, or the SoundFont couldn't be fetched."""


# ------------------------------------------------------------------ sampled instruments

SAMPLE_RATE = 48000
PART_OF_ROLE = {"melody": "melody", "piano_rh": "piano", "piano_lh": "piano", "bass": "bass",
                "drums": "drums", "other": "other"}
PART_ORDER = ["melody", "piano", "other", "bass", "drums"]
BALANCE_DB = {"melody": 0.0, "piano": -4.0, "other": -6.0, "bass": -6.0, "drums": -9.0}   # loudness vs. the melody
REVERB = {"melody": 0.18, "piano": 0.14, "other": 0.14, "bass": 0.04, "drums": 0.08}      # send to the room
# When the melody is also on the piano (piano-vocal preview), the accompaniment sits further back.
PIANO_VOCAL_BALANCE_DB = {"melody": 0.0, "piano": -8.0, "other": -6.0, "bass": -7.0, "drums": -12.0}
PIANO_VOCAL_REVERB = {"melody": 0.12, "piano": 0.10, "other": 0.10, "bass": 0.03, "drums": 0.06}
POLYPHONY = 256        # the piano with its pedal down needs plenty

# Leads whose midrange harmonics fight piano shells at the normal -4 dB balance.
SOFT_ACCOMP_MELODY = frozenset({"piano", "organ", "musicbox", "sax", "flute", "clarinet", "fiddle"})


def mix_levels(plan: dict[str, str]) -> tuple[dict[str, float], dict[str, float]]:
    """Balance and room sends for this instrument plan."""
    if plan.get("melody") in SOFT_ACCOMP_MELODY:
        return dict(PIANO_VOCAL_BALANCE_DB), dict(PIANO_VOCAL_REVERB)
    return dict(BALANCE_DB), dict(REVERB)


@dataclass
class BandAudio:
    wav: Path
    engine: str                                   # "sampled" or "soundfont"
    instruments: dict[str, str] = field(default_factory=dict)   # part -> instrument id
    stems: dict[str, Path] = field(default_factory=dict)
    credits: list[str] = field(default_factory=list)
    note: str = ""                                # why the SoundFont played instead
    loudness: float | None = None
    limited_db: float | None = None

    def summary(self) -> dict:
        """What played, for out/<song>/audio.json (the page reads it)."""
        from . import instruments
        parts = [{"part": part, "instrument": self.instruments[part],
                  "label": instruments.CATALOG[self.instruments[part]].label,
                  "licence": instruments.CATALOG[self.instruments[part]].licence,
                  "stem": self.stems[part].name if part in self.stems else None}
                 for part in PART_ORDER if part in self.instruments] if self.engine == "sampled" else []
        return {"engine": self.engine, "parts": parts, "credits": self.credits, "note": self.note,
                "loudness": self.loudness, "limited_db": self.limited_db}

    def report_lines(self) -> list[str]:
        from . import instruments
        if self.engine != "sampled":
            return [f"Played with the GeneralUser GS SoundFont, because {self.note}"]
        lines = ["Played on sampled instruments with sfizz, one part at a time, then mixed:", ""]
        for part in PART_ORDER:
            if part in self.instruments:
                inst = instruments.CATALOG[self.instruments[part]]
                lines.append(f"- {part.title()}: {inst.label} ({inst.licence})")
        limiting = (f"the limiter took off at most {self.limited_db:.1f} dB" if self.limited_db >= 0.05
                    else "no limiting needed")
        lines += ["", f"Mastered to {self.loudness:.1f} LUFS with peaks under -1 dBFS ({limiting})."]
        if self.stems:
            lines.append("Each part is also in `stems/`, as it sits in the mix.")
        if self.credits:
            lines += ["", "Credits: " + "; ".join(self.credits) + "."]
        return lines


def sfizz_program() -> Path | None:
    from . import paths
    return paths.find_program("sfizz_render", "COPYIST_SFIZZ")


def split_parts(midi_path: Path, folder: Path) -> dict[str, Path]:
    """One MIDI file per part, each keeping every track's tempo and meter events."""
    import mido
    from . import perform
    mid = mido.MidiFile(str(midi_path))
    notes, _ = perform.read(mid)
    role = perform.roles(mid, notes)
    tracks: dict[str, set[int]] = {}
    for ti, r in role.items():
        tracks.setdefault(PART_OF_ROLE.get(r, "other"), set()).add(ti)
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for part in [p for p in PART_ORDER if p in tracks]:
        new = mido.MidiFile(type=1, ticks_per_beat=mid.ticks_per_beat)
        for ti, track in enumerate(mid.tracks):
            kept, carry = mido.MidiTrack(), 0
            for msg in track:
                if ti in tracks[part] or msg.is_meta:
                    kept.append(msg.copy(time=msg.time + carry))
                    carry = 0
                else:
                    carry += msg.time
            new.tracks.append(kept)
        path = folder / f"{part}.mid"
        new.save(str(path))
        out[part] = path
    return out


def transpose_midi(midi: Path, semitones: int, dest: Path | None = None) -> Path:
    """Raise or lower every note in a MIDI file by `semitones` (in place if `dest` is None)."""
    import mido
    mid = mido.MidiFile(str(midi))
    for track in mid.tracks:
        for msg in track:
            if msg.type in ("note_on", "note_off"):
                msg.note = max(0, min(127, msg.note + semitones))
    out = dest or midi
    mid.save(str(out))
    return out


def play_part(program: Path, sfz: Path, midi: Path, wav: Path) -> Path:
    """Render one part's MIDI through one SFZ instrument."""
    cmd = [str(program), "--sfz", str(sfz), "--midi", str(midi), "--wav", str(wav),
           "-s", str(SAMPLE_RATE), "-p", str(POLYPHONY)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise AudioUnavailable(f"sfizz couldn't play the {midi.stem} part: {e}") from e
    if r.returncode != 0 or not wav.is_file():
        detail = (r.stderr or r.stdout).strip().splitlines()[-1:] or ["no output"]
        raise AudioUnavailable(f"sfizz couldn't play the {midi.stem} part: {detail[0]}")
    return wav


def sampled_plan(parts, style: str | None) -> tuple[dict[str, str], str]:
    """(part -> instrument id, and why the sampled instruments can't play, or "")."""
    from . import instruments
    plan = {part: instruments.instrument_for(part, style) for part in parts}
    if sfizz_program() is None:
        return plan, ("sfizz isn't installed yet (scripts/setup-sfizz.sh, or the desktop app, which "
                      "bundles it).")
    missing = sorted({i for i in plan.values() if instruments.sfz_path(i) is None})
    if missing:
        return plan, ("these instruments aren't downloaded yet: " + ", ".join(missing) +
                      " (`copyist models download band`, or the Download button on the Sound tab).")
    return plan, ""


def render_band(midi_path: Path, wav_path: Path, style: str | None = None, cache_dir: Path = Path(".cache"),
                stems_dir: Path | None = None) -> BandAudio:
    """The arrangement as audio: sampled instruments when they're installed, else the SoundFont."""
    from . import instruments, mixdown
    with tempfile.TemporaryDirectory(prefix="copyist-parts-") as tmp:
        work = Path(tmp)
        parts = split_parts(midi_path, (stems_dir or work) / "midi")
        plan, why_not = sampled_plan(parts, style)
        if not parts:
            why_not = "the arrangement has no notes to play."
        if not why_not:
            try:
                program = sfizz_program()
                audio = {}
                for part, midi in parts.items():
                    shift = instruments.play_shift(plan[part])
                    play = transpose_midi(midi, shift, work / f"{part}-play.mid") if shift else midi
                    raw = play_part(program, instruments.sfz_path(plan[part]), play, work / f"{part}.wav")
                    audio[part], sr = mixdown.read(raw)
                    if sr != SAMPLE_RATE:
                        raise AudioUnavailable(f"sfizz played the {part} part at {sr} Hz, not {SAMPLE_RATE}")
                balance, reverb = mix_levels(plan)
                mixed = mixdown.mix(audio, SAMPLE_RATE, balance, reverb)
            except AudioUnavailable as e:
                why_not = str(e)
        if why_not:
            soundfont = soundfont_path(cache_dir)
            render_midi(midi_path, wav_path, soundfont)
            return BandAudio(wav_path, "soundfont", note=why_not)
        mixdown.write(wav_path, mixed.audio, SAMPLE_RATE, bits=16)
        stems = {}
        if stems_dir:
            for part, a in mixed.stems.items():
                stems[part] = mixdown.write(stems_dir / f"{part}.wav", a, SAMPLE_RATE, bits=24)
        return BandAudio(wav_path, "sampled", instruments=plan, stems=stems,
                         credits=instruments.credits(plan.values()), loudness=mixed.loudness,
                         limited_db=mixed.limited_db)


def soundfont_path(cache_dir: Path) -> Path:
    """Return the SoundFont path, downloading it on first use (about 32 MB)."""
    path = cache_dir / SOUNDFONT_NAME
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    cache_dir.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    print(f"Downloading the GeneralUser GS SoundFont into {cache_dir} (one time, about 32 MB)...")
    try:
        urllib.request.urlretrieve(SOUNDFONT_URL, tmp)
    except OSError as e:
        raise AudioUnavailable(f"Couldn't download the SoundFont from {SOUNDFONT_URL}: {e}") from e
    tmp.rename(path)
    return path


def render_midi(midi_path: Path, wav_path: Path, soundfont: Path,
                samplerate: int = 44100, tail_seconds: float = 2.5) -> Path:
    """Play a MIDI file through the SoundFont, offline, and write a 16-bit stereo WAV."""
    try:
        import numpy as np
        import tinysoundfont
        import tinysoundfont.midi as tm
    except ImportError as e:
        raise AudioUnavailable("Audio needs TinySoundFont: pip install --no-deps tinysoundfont") from e

    synth = tinysoundfont.Synth(gain=-6, samplerate=samplerate)
    sfid = synth.sfload(str(soundfont))
    for ch in range(16):
        drums = ch == DRUM_CHANNEL
        synth.program_select(ch, sfid, 128 if drums else 0, 0, is_drums=drums)

    events = sorted(tm.load(str(midi_path)), key=lambda e: e.t)
    chunks = []
    position = 0  # samples rendered so far
    for event in events:
        target = int(round(event.t * samplerate))
        if target > position:
            chunks.append(np.frombuffer(synth.generate(target - position), dtype=np.float32).copy())
            position = target
        apply(synth, event)
    chunks.append(np.frombuffer(synth.generate(int(tail_seconds * samplerate)), dtype=np.float32).copy())

    audio = np.concatenate(chunks) if chunks else np.zeros(2, dtype=np.float32)
    peak = float(np.max(np.abs(audio))) or 1.0
    audio = audio * (0.89 / peak)  # normalise to about -1 dBFS
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(samplerate)
        w.writeframes(pcm.tobytes())
    return wav_path


def apply(synth, event) -> None:
    import tinysoundfont.midi as tm
    a, ch = event.action, event.channel
    if isinstance(a, tm.NoteOn):
        if a.velocity:
            synth.noteon(ch, a.key, a.velocity)
        else:
            synth.noteoff(ch, a.key)
    elif isinstance(a, tm.NoteOff):
        synth.noteoff(ch, a.key)
    elif isinstance(a, tm.ProgramChange):
        synth.program_change(ch, a.program, is_drums=ch == DRUM_CHANNEL)
    elif isinstance(a, tm.ControlChange):
        synth.control_change(ch, a.control, a.control_value)
    elif isinstance(a, tm.PitchBend):
        synth.pitchbend(ch, a.pitch_bend)


def wav_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def read_wav(path: Path):
    """(float32 samples shaped [frames, channels], sample rate)."""
    import numpy as np
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype="<i2").astype(np.float32) / 32768.0
    return data.reshape(-1, ch), sr


def write_wav(path: Path, audio, sr: int) -> Path:
    import numpy as np
    peak = float(np.max(np.abs(audio))) or 1.0
    pcm = (np.clip(audio * (0.89 / peak), -1, 1) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(audio.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return path


def mix_vocal(band_wav: Path, vocal_wav: Path, out: Path, band_start: float, lead: float,
              length: float, vocal_db: float = 0.0, band_db: float = -5.0) -> Path:
    """Lay a sung vocal over the band.

    `band_start` is where the excerpt starts in the band recording (seconds);
    the vocal recording starts `lead` seconds before that point.
    """
    import numpy as np
    import soundfile as sf
    import librosa
    band, sr = read_wav(band_wav)
    voc, vsr = sf.read(str(vocal_wav), dtype="float32", always_2d=True)
    voc = voc.mean(axis=1)
    if vsr != sr:
        voc = librosa.resample(voc, orig_sr=vsr, target_sr=sr)
    voc = voc / (float(np.max(np.abs(voc))) or 1.0)
    band = band / (float(np.max(np.abs(band))) or 1.0)
    first = int(round((band_start - lead) * sr))
    total = int(round((lead + length + 1.5) * sr))
    seg = np.zeros((total, 2), dtype=np.float32)
    src_a, dst_a = max(first, 0), max(-first, 0)
    take = max(0, min(total - dst_a, band.shape[0] - src_a))
    seg[dst_a:dst_a + take] = band[src_a:src_a + take, :2] if band.shape[1] >= 2 else band[src_a:src_a + take]
    v = voc[:total]
    seg[:len(v)] = seg[:len(v)] * 10 ** (band_db / 20) + (v * 10 ** (vocal_db / 20))[:, None]
    return write_wav(out, seg, sr)
