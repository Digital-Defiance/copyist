import json
import tempfile
import unittest
from pathlib import Path

from copyist import lora

SHEET = """# June Snow

**Act One · #8**

## Demo style (Broadway pit)

```
Theatrical female Broadway lead smooth alto vocal. Broadway cast recording: acoustic guitar, about 100 BPM.
```

## Full production style

```
Light acoustic folk, about 100 BPM.
```

## Lyrics

```
[Intro]

[Verse 1]
[Female Lead (Jennifer)]
Every day when I go out,
the cottonwoods dance [Train whistle] for me.

[Pre-Chorus]
The birds pick up (the melody).

[Chorus]
The cottonwoods dance for me!

[Instrumental break: hot fiddle, then steel]

[Spoken Word: Female Lead (Jennifer)]
I spend an hour every day watching the dance.

[Strings out; voice and piano]
[End]
```
"""


class LyricsTests(unittest.TestCase):
    def test_sections_become_yue_tags(self):
        self.assertEqual(lora.section_tag("Verse 2"), "verse")
        self.assertEqual(lora.section_tag("Pre-Chorus"), "prechorus")
        self.assertEqual(lora.section_tag("Final Chorus"), "chorus")
        self.assertEqual(lora.section_tag("Coda"), "outro")
        self.assertEqual(lora.section_tag("Instrumental break"), "interlude")
        self.assertEqual(lora.section_tag("Spoken Word"), "spoken")
        self.assertIsNone(lora.section_tag("Female Lead (Jennifer)"))
        self.assertIsNone(lora.section_tag("Strings out; voice and piano"))

    def test_lyrics_keep_words_and_sections_and_drop_cues(self):
        out = lora.yue_lyrics(lora.read_prompt_sheet(self.sheet()).lyrics)
        self.assertEqual(out, "[intro]\n\n[verse]\nEvery day when I go out,\nthe cottonwoods dance for me.\n\n"
                              "[prechorus]\nThe birds pick up (the melody).\n\n[chorus]\nThe cottonwoods dance for me!\n\n"
                              "[interlude]\n\n[spoken]\nI spend an hour every day watching the dance.")

    def test_caption_starts_with_the_trigger(self):
        self.assertEqual(lora.caption("lightson", "Broadway  cast\nrecording."),
                         "lightson, in the style of lightson. Broadway cast recording.")

    def test_sheets_pair_with_audio_by_number(self):
        d = Path(tempfile.mkdtemp(prefix="copyist-lora-"))
        (d / "sheets").mkdir(); (d / "audio").mkdir()
        (d / "sheets" / "08 - June Snow.md").write_text(SHEET, encoding="utf-8")
        (d / "sheets" / "P - Prologue.md").write_text(SHEET.replace("# June Snow", "# Prologue"), encoding="utf-8")
        for name in ("08 - Lights On - June Snow.mp3", "08 - Lights On - June Snow.wav", "00 - Lights On - Prologue.wav",
                     "09 - Lights On - The Party.wav"):
            (d / "audio" / name).write_bytes(b"")
        songs = lora.build_songs([d / "sheets"], d / "audio", "lightson")
        self.assertEqual([(s.name, s.audio) for s in songs],
                         [("08-june-snow", "08 - Lights On - June Snow.wav"), ("00-prologue", "00 - Lights On - Prologue.wav")])
        self.assertTrue(songs[0].style.startswith("lightson, in the style of lightson. Theatrical female"))
        out = d / "songs.jsonl"
        lora.write_songs(songs, out)
        self.assertEqual(lora.read_songs(out), songs)
        self.assertEqual(json.loads(out.read_text().splitlines()[0])["name"], "08-june-snow")

    def sheet(self) -> Path:
        p = Path(tempfile.mkdtemp(prefix="copyist-lora-")) / "08 - June Snow.md"
        p.write_text(SHEET, encoding="utf-8")
        return p


if __name__ == "__main__":
    unittest.main()
