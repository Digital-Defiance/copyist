"""Demo audio: MIDI → WAV with TinySoundFont and the GeneralUser GS SoundFont.

This is the M0 "sound": exact and predictable, but it sounds like a demo.
See SPEC.md section 6 for what comes next.
"""
from __future__ import annotations

import urllib.request
import wave
from pathlib import Path

SOUNDFONT_URL = "https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2"
SOUNDFONT_NAME = "GeneralUser-GS.sf2"
DRUM_CHANNEL = 9


class AudioUnavailable(RuntimeError):
    """TinySoundFont isn't installed, or the SoundFont couldn't be fetched."""


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
