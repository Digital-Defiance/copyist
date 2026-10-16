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


def song_from(**fields) -> Song:
    data = {**BASE, **fields}
    tmp = Path(tempfile.mkdtemp(prefix="copyist-test-"))
    path = tmp / "test-song.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return load_song(path)


def severities(findings, check: str) -> set[str]:
    return {f.severity for f in findings if f.check == check}
