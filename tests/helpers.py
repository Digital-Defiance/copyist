"""Small helpers for building test songs."""
from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from copyist.song import Song, load_song

BASE = {
    "format": "copyist-song/0",
    "title": "Test Song",
    "key": "C",
    "meter": "4/4",
    "tempo": 100,
    "voice": {"name": "Melody", "range": ["C4", "C5"]},
}


# tests/data/plans/key-change.abc, SheetSage2's layout: C major, a `K:D` line in both voices before
# bar 3, and `[K:Bb]` in the middle of bar 5. The written MIDI pitches, an octave above the singing.
KEY_CHANGE_VOCAL = [
    72, 76, 79, 78,         # bar 1, C: C E G F#
    77, 81, 84, 81,         # bar 2: F A C A; bar 1's F# stops at the bar line
    74, 78, 81, 86,         # bar 3, D: D F# A D
    79, 77, 77, 73,         # bar 4: G F F C#; the natural holds for the next F, and C is C# in D
    80, 81, 79, 82,         # bar 5: G# A, then [K:Bb]: G Bb (the G# stops at the key change)
    75, 82,                 # bar 6, Bb: Eb Bb
]
KEY_CHANGE_INS = [
    48, 52,                 # bar 1, C: C E
    53, 54,                 # bar 2: F F#
    50, 54,                 # bar 3, D: D F#
    55, 53,                 # bar 4: G F (written natural)
    52, 55,                 # bar 5: E, then [K:Bb]: G
    51, 46,                 # bar 6, Bb: Eb Bb
]


def la(n: int) -> str:
    """Lyrics for tests: n syllables of "la"."""
    return " ".join(["la"] * n)


def song_from(**fields) -> Song:
    data = {**BASE, **fields}
    tmp = Path(tempfile.mkdtemp(prefix="copyist-test-"))
    path = tmp / "test-song.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_song(path)


def severities(findings, check: str) -> set[str]:
    return {f.severity for f in findings if f.check == check}
