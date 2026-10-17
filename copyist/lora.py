"""Training data for a YuE2 voice/style LoRA (docs/voice-lora.md).

A LoRA teaches YuE2 how one artist sounds: the singer, the band, the mix. Each
training song needs its audio, its full lyrics with section tags, and a style
caption that starts with a trigger word. This module turns Suno/Mozart-style
prompt sheets (a demo style and tagged lyrics per song) into that form and
pairs each sheet with its audio. Tokenizing the audio and training happen on a
machine with a GPU: scripts/yue-lora/.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

# Suno/Mozart section names -> the tags YuE2 was trained on (lowercase, unnumbered)
SECTIONS = [
    (r"pre[- ]?chorus", "prechorus"),
    (r"post[- ]?chorus|chorus|hook|refrain", "chorus"),
    (r"verse", "verse"),
    (r"bridge|middle 8", "bridge"),
    (r"intro", "intro"),
    (r"outro|coda|tag|ending", "outro"),
    (r"interlude|instrumental|instrumental break|solo|break|breakdown", "interlude"),
]
DROP_SECTIONS = re.compile(r"^(end|fade out)$", re.I)


@dataclass
class PromptSheet:
    title: str
    demo_style: str | None
    production_style: str | None
    lyrics: str


@dataclass
class TrainingSong:
    name: str          # short id, also the file stem of its tokens
    audio: str         # file name inside the audio folder
    style: str         # caption, trigger word first
    lyrics: str        # YuE2 form


def _code_block_after(text: str, heading: str) -> str | None:
    m = re.search(rf"^##\s*{heading}[^\n]*\n(.*?)```[^\n]*\n(.*?)```", text, re.M | re.S | re.I)
    return m.group(2).strip() if m else None


def read_prompt_sheet(path: Path) -> PromptSheet:
    """A sheet: '# Title', then '## Demo style', '## Full production style' and '## Lyrics' code blocks."""
    text = Path(path).read_text(encoding="utf-8")
    title = re.search(r"^#\s+(.+)$", text, re.M)
    lyrics = _code_block_after(text, "Lyrics")
    if lyrics is None:
        raise ValueError(f"{path}: no '## Lyrics' code block")
    return PromptSheet(title.group(1).strip() if title else Path(path).stem,
                       _code_block_after(text, "Demo style"), _code_block_after(text, "Full production style"),
                       lyrics)


def section_tag(name: str) -> str | None:
    """'Verse 2' -> 'verse', 'Pre-Chorus' -> 'prechorus'; None for tags that aren't sections.

    Spoken passages get a tag of their own, 'spoken', which YuE2 hasn't seen: a
    LoRA learns it from the songs that use it.
    """
    name = re.sub(r"\s*\d+\s*$", "", name.strip()).strip()
    if re.match(r"spoken", name, re.I):
        return "spoken"
    for pattern, tag in SECTIONS:
        if re.fullmatch(rf"(final |last |first )?({pattern})", name, re.I):
            return tag
    return None


def yue_lyrics(text: str) -> str:
    """Suno/Mozart-tagged lyrics -> YuE2 lyrics.

    Section tags become YuE2's ([Verse 2] -> [verse]); spoken passages become
    [spoken]. Voice tags and production cues are dropped: everything left in
    the lyrics is something the recording says or sings. Parentheses stay
    (backing vocals).
    """
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        whole = re.fullmatch(r"\[([^\]]*)\]", line)
        if whole:
            inner = whole.group(1)
            tag = section_tag(inner.split(":")[0])
            if tag:
                if out and out[-1] != "":
                    out.append("")
                out.append(f"[{tag}]")
            elif DROP_SECTIONS.match(inner.strip()) and out and out[-1] != "":
                out.append("")
            continue
        line = " ".join(re.sub(r"\[[^\]]*\]", " ", line).split())   # inline cues
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    # A section with no lyrics keeps its tag (intro, interlude); a blank line separates sections.
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def caption(trigger: str, style: str) -> str:
    """The style line a song trains under. The trigger word is what calls the LoRA up later."""
    style = " ".join(style.split())
    return f"{trigger}, in the style of {trigger}. {style}"


def number_of(name: str) -> int | None:
    """'08 - June Snow.md' -> 8; 'P - Prologue.md' -> 0 (the prologue)."""
    m = re.match(r"\s*(\d+)\b", name)
    if m:
        return int(m.group(1))
    return 0 if re.match(r"\s*P\b", name) else None


def pair_sheets_with_audio(sheet_dirs: list[Path], audio_dir: Path, exts=(".wav", ".flac", ".mp3")) -> list[tuple[Path, Path]]:
    """Match prompt sheets to audio files by their leading number. Prefers WAV, then FLAC, then MP3."""
    audio: dict[int, Path] = {}
    for f in sorted(Path(audio_dir).iterdir()):
        n = number_of(f.name)
        if n is None or f.suffix.lower() not in exts:
            continue
        if n not in audio or exts.index(f.suffix.lower()) < exts.index(audio[n].suffix.lower()):
            audio[n] = f
    pairs = []
    for d in sheet_dirs:
        for sheet in sorted(Path(d).glob("*.md")):
            n = number_of(sheet.name)
            if n is not None and n in audio:
                pairs.append((sheet, audio[n]))
    return pairs


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def build_songs(sheet_dirs: list[Path], audio_dir: Path, trigger: str, use: str = "demo") -> list[TrainingSong]:
    songs = []
    for sheet_path, audio_path in pair_sheets_with_audio(sheet_dirs, audio_dir):
        sheet = read_prompt_sheet(sheet_path)
        style = sheet.demo_style if use == "demo" else sheet.production_style
        style = style or sheet.demo_style or sheet.production_style
        if not style:
            raise ValueError(f"{sheet_path}: no style")
        n = number_of(sheet_path.name)
        songs.append(TrainingSong(f"{n:02d}-{slug(sheet.title)}", audio_path.name, caption(trigger, style),
                                  yue_lyrics(sheet.lyrics)))
    return songs


def write_songs(songs: list[TrainingSong], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for s in songs:
            f.write(json.dumps(asdict(s), ensure_ascii=False) + "\n")


def read_songs(path: Path) -> list[TrainingSong]:
    return [TrainingSong(**json.loads(line)) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
