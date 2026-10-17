"""Mixing the parts into one recording (docs/sound-set.md): balance, a room, and a gentle master.

numpy only, so it runs wherever Copyist does.

- Balance by loudness, not by peak: each part is measured the way broadcast
  meters do (ITU-R BS.1770: K-weighted, gated) and set relative to the melody,
  so a quiet clarinet and a loud piano sit where they should.
- One shared room: a short, natural reverb (a synthetic impulse response,
  about 1.1 s, darker as it decays), with more of it on the melody and piano
  than on the bass, so the parts sound like they were played together.
- The master: the whole mix to -16 LUFS, then a look-ahead limiter that keeps
  peaks under -1 dBFS. If that would need more than a few dB of limiting, the
  mix is left quieter instead: gentle, not loud.
"""
from __future__ import annotations

import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

TARGET_LUFS = -16.0
CEILING_DB = -1.0
MAX_LIMIT_DB = 4.0


# ------------------------------------------------------------------ files

def read(path: Path) -> tuple[np.ndarray, int]:
    """A 16- or 24-bit PCM WAV as float32 [frames, 2]."""
    with wave.open(str(path), "rb") as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        i = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        x = (np.where(i >= 1 << 23, i - (1 << 24), i)).astype(np.float32) / 8388608.0
    else:
        raise ValueError(f"{path}: {8 * width}-bit WAV isn't supported")
    x = x.reshape(-1, ch)
    if ch == 1:
        x = np.repeat(x, 2, axis=1)
    return x[:, :2], sr


def write(path: Path, x: np.ndarray, sr: int, bits: int = 16, seed: int = 0) -> Path:
    """Write float audio as PCM; 16-bit gets a little TPDF dither."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if bits == 16:
        rng = np.random.default_rng(seed)
        lsb = 1 / 32768.0
        x = x + (rng.random(x.shape) - rng.random(x.shape)) * lsb
        data = (np.clip(x, -1, 1 - lsb) * 32768.0).round().astype("<i2").tobytes()
        width = 2
    elif bits == 24:
        i = (np.clip(x, -1, 1 - 2 ** -23) * 8388608.0).round().astype("<i4")
        data = i.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
        width = 3
    else:
        raise ValueError(bits)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(x.shape[1])
        w.setsampwidth(width)
        w.setframerate(sr)
        w.writeframes(data)
    return path


# ------------------------------------------------------------------ loudness

def _biquad_response(b, a, freqs, sr):
    z = np.exp(-2j * np.pi * freqs / sr)
    return (b[0] + b[1] * z + b[2] * z ** 2) / (a[0] + a[1] * z + a[2] * z ** 2)


def _k_weighting(freqs: np.ndarray, sr: int) -> np.ndarray:
    """|H| of the BS.1770 K-weighting filter (high shelf, then high-pass) at these frequencies."""
    # Stage 1: high shelf, +4 dB above about 1.5 kHz
    db, f0, q = 3.999843853973347, 1681.974450955533, 0.7071752369554196
    k = np.tan(np.pi * f0 / sr)
    vh = 10 ** (db / 20)
    vb = vh ** 0.4996667741545416
    a0 = 1 + k / q + k * k
    b = [(vh + vb * k / q + k * k) / a0, 2 * (k * k - vh) / a0, (vh - vb * k / q + k * k) / a0]
    a = [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    h1 = _biquad_response(b, a, freqs, sr)
    # Stage 2: high-pass at about 38 Hz
    f0, q = 38.13547087602444, 0.5003270373238773
    k = np.tan(np.pi * f0 / sr)
    a0 = 1 + k / q + k * k
    a = [1, 2 * (k * k - 1) / a0, (1 - k / q + k * k) / a0]
    h2 = _biquad_response([1, -2, 1], a, freqs, sr)
    return np.abs(h1 * h2)


def loudness(x: np.ndarray, sr: int) -> float:
    """Integrated loudness in LUFS (BS.1770-4, gated); -inf for silence."""
    if len(x) < int(0.4 * sr):
        return float("-inf")
    spec = np.fft.rfft(x, axis=0)
    spec *= _k_weighting(np.fft.rfftfreq(len(x), 1 / sr), sr)[:, None]
    y = np.fft.irfft(spec, n=len(x), axis=0)
    block, hop = int(0.4 * sr), int(0.1 * sr)
    power = np.cumsum(np.concatenate([[0.0], (y.astype(np.float64) ** 2).sum(axis=1)]))
    starts = np.arange(0, len(y) - block + 1, hop)
    ms = (power[starts + block] - power[starts]) / block
    lk = -0.691 + 10 * np.log10(ms + 1e-20)
    gated = ms[lk > -70]
    if not len(gated):
        return float("-inf")
    rel = -0.691 + 10 * np.log10(gated.mean()) - 10
    gated = ms[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(gated.mean()))


# ------------------------------------------------------------------ the room

def room_impulse(sr: int, seed: int = 7, rt60: float = 1.1, length: float = 1.6) -> np.ndarray:
    """A stereo impulse response for a small hall: early reflections, then a tail that darkens."""
    rng = np.random.default_rng(seed)
    n = int(length * sr)
    t = np.arange(n) / sr
    ir = np.zeros((n, 2))
    for ch in range(2):
        noise = rng.standard_normal(n)
        spec = np.fft.rfft(noise)
        freqs = np.fft.rfftfreq(n, 1 / sr)
        bands = []
        for lo, hi, decay in ((0, 300, rt60 * 1.2), (300, 3000, rt60), (3000, sr / 2 + 1, rt60 * 0.5)):
            part = np.where((freqs >= lo) & (freqs < hi), spec, 0)
            bands.append(np.fft.irfft(part, n=n) * np.exp(-6.91 * t / decay))
        tail = sum(bands)
        tail[: int(0.012 * sr)] = 0                                   # pre-delay
        tail *= np.minimum(1, np.maximum(0, t - 0.012) / 0.03)        # swell in
        for delay, gain in zip(rng.uniform(0.004, 0.03, 6), rng.uniform(0.2, 0.5, 6)):
            tail[int(delay * sr)] += gain * rng.choice([-1, 1])
        ir[:, ch] = tail
    # Keep the low end out of the room so it doesn't muddy the bass.
    spec = np.fft.rfft(ir, axis=0)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    spec *= (1 / np.sqrt(1 + (150 / np.maximum(freqs, 1)) ** 4))[:, None]
    ir = np.fft.irfft(spec, n=n, axis=0)
    return (ir / np.sqrt((ir ** 2).sum(axis=0).mean())).astype(np.float32)


def convolve(x: np.ndarray, ir: np.ndarray, block: int = 1 << 16) -> np.ndarray:
    """The room's response to x (summed to mono going in, stereo coming out), by overlap-add."""
    mono = x.mean(axis=1)
    m = len(ir)
    size = 1 << int(np.ceil(np.log2(block + m - 1)))
    h = np.fft.rfft(ir, n=size, axis=0)
    out = np.zeros((len(mono) + m - 1, 2), dtype=np.float32)
    for start in range(0, len(mono), block):
        seg = mono[start:start + block]
        y = np.fft.irfft(np.fft.rfft(seg, n=size)[:, None] * h, n=size, axis=0)
        end = min(start + size, len(out))
        out[start:end] += y[: end - start]
    return out


# ------------------------------------------------------------------ the master

def limit(x: np.ndarray, sr: int, ceiling_db: float = CEILING_DB, lookahead: float = 0.005,
          release: float = 0.15) -> tuple[np.ndarray, float]:
    """Keep peaks under the ceiling; returns (audio, the most gain reduction used, in dB)."""
    ceiling = 10 ** (ceiling_db / 20)
    peak = np.abs(x).max(axis=1)
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    hop = max(1, int(0.001 * sr))
    nb = int(np.ceil(len(need) / hop))
    padded = np.ones(nb * hop)
    padded[: len(need)] = need
    blocks = padded.reshape(nb, hop).min(axis=1)
    ahead = int(np.ceil(lookahead * sr / hop))
    ext = np.concatenate([blocks, np.ones(ahead)])
    window = np.lib.stride_tricks.sliding_window_view(ext, ahead + 1).min(axis=1)[:nb]
    coef = 1 - np.exp(-hop / (release * sr))
    g = np.empty(nb)
    level = 1.0
    for i, want in enumerate(window):
        level = want if want < level else level + (1 - level) * coef
        g[i] = level
    gain = np.interp(np.arange(len(need)), np.arange(nb) * hop, g)
    gain = np.minimum(gain, need)
    return x * gain[:, None], float(-20 * np.log10(gain.min()))


@dataclass
class Mixed:
    audio: np.ndarray
    stems: dict[str, np.ndarray]     # each part as it sits in the mix (reverb included), before the limiter
    gains_db: dict[str, float]
    loudness: float
    limited_db: float


def mix(parts: dict[str, np.ndarray], sr: int, balance_db: dict[str, float], reverb: dict[str, float],
        reference: str = "melody") -> Mixed:
    """Balance the parts by loudness, put them in one room, and master the sum."""
    length = max(len(a) for a in parts.values())
    ir = room_impulse(sr)
    measured = {name: loudness(a, sr) for name, a in parts.items()}
    ref = reference if np.isfinite(measured.get(reference, float("-inf"))) else None
    stems, gains = {}, {}
    for name, a in parts.items():
        if not np.isfinite(measured[name]):
            continue
        offset = balance_db.get(name, -6.0) - (balance_db.get(ref, 0.0) if ref else 0.0)
        gain_db = -23.0 + offset - measured[name]
        dry = a * np.float32(10 ** (gain_db / 20))
        stem = np.zeros((length + len(ir) - 1, 2), dtype=np.float32)
        stem[: len(dry)] += dry
        wet = convolve(dry, ir) * reverb.get(name, 0.1)
        stem[: len(wet)] += wet
        stems[name] = stem
        gains[name] = gain_db
    total = sum(stems.values())
    # Trim the room's silent tail.
    level = np.abs(total).max(axis=1)
    last = int(np.nonzero(level > 10 ** (-80 / 20))[0][-1]) + 1 if (level > 0).any() else len(total)
    end = min(len(total), last + int(0.2 * sr))
    total = total[:end]
    stems = {k: v[:end] for k, v in stems.items()}
    master = 10 ** ((TARGET_LUFS - loudness(total, sr)) / 20)
    peak_db = 20 * np.log10(np.abs(total * master).max() + 1e-12)
    excess = peak_db - CEILING_DB - MAX_LIMIT_DB
    if excess > 0:
        master *= 10 ** (-excess / 20)
    out, reduced = limit(total * master, sr)
    # Fade the last 50 ms so the file ends in silence.
    fade = min(len(out), int(0.05 * sr))
    out[-fade:] *= np.linspace(1, 0, fade)[:, None]
    return Mixed(out, {k: v * master for k, v in stems.items()}, gains, loudness(out, sr), reduced)
