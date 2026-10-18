import dataclasses
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import mido
from music21 import harmony, stream

from copyist import arrange, engrave, gallery, perform, render, styles
from copyist.song import load_song

ROOT = Path(__file__).resolve().parents[1]
SONGS = {"3/4": ROOT / "songs" / "amazing-grace.yaml", "4/4": ROOT / "songs" / "when-the-saints.yaml",
         "6/8": ROOT / "songs" / "silent-night.yaml"}


def bar_lengths(part):
    out = []
    for m in part.getElementsByClass(stream.Measure):
        if m.voices:
            out.append(max(sum(e.quarterLength for e in v.notesAndRests) for v in m.voices))
        else:
            out.append(sum(e.quarterLength for e in m.notesAndRests if not isinstance(e, harmony.ChordSymbol)))
    return out


def minimal(**changes) -> dict:
    data = {"format": "copyist-style/0", "name": "T", "family": "Pop and rock", "about": "a", "production": "p",
            "meters": {"4/4": {"rh": [[0, 4, "chord"]], "lh": [[0, 4, "root"]], "bass": [[0, 4, "root"]],
                               "drums": "none"}}}
    data.update(changes)
    return data


class CatalogTests(unittest.TestCase):
    def test_every_style_file_reads(self):
        catalog = styles.catalog()
        self.assertGreaterEqual(len(catalog), 20)
        for s in catalog.values():
            self.assertIn(s.family, styles.FAMILIES)
            self.assertTrue(s.production and s.about and s.meters)

    def test_every_meter_has_a_default_style_that_plays_it(self):
        for meter, style_id in styles.DEFAULT_FOR_METER.items():
            self.assertIn(meter, styles.get(style_id).meters, meter)

    def test_mistakes_in_a_style_file_are_named(self):
        bad = [
            minimal(family="Polka"),
            minimal(feel="lilting"),
            minimal(meters={"4/4": {"rh": [[0, 4, "melody"]], "lh": [], "bass": [], "drums": "none"}}),
            minimal(meters={"4/4": {"rh": [[3, 2, "chord"]], "lh": [], "bass": [], "drums": "none"}}),
            minimal(meters={"4/4": {"rh": [], "lh": [], "bass": [],
                                    "drums": {"hands": [[0, 1, ["cowbell"]]], "feet": [], "fill": [[0, 1, ["snare"]]]}}}),
            minimal(meters={"4/4": {"rh": [], "lh": [], "bass": {"line": ["root", "ninth"], "every": 0.5},
                                    "drums": "none"}}),
            minimal(instruments={"bass": "tuba"}),
        ]
        for data in bad:
            with self.assertRaises(styles.StyleError):
                styles.parse(data, "test")
        self.assertEqual(styles.parse(minimal(), "test").feel, "straight")

    def test_triplets_can_be_written_as_fractions(self):
        s = styles.parse(minimal(meters={"4/4": {"rh": [["1/3", "1/3", "chord"]], "lh": [], "bass": [],
                                                 "drums": "none"}}), "test")
        self.assertAlmostEqual(s.pattern("4/4")["rh"][0][0], 1 / 3)

    def test_a_phrase_of_bars_cycles(self):
        data = minimal(meters={"4/4": {
            "rh": [[[0, 2, "arp1"], [2, 2, "arp2"]], [[0, 4, "chord"]]],
            "lh": [[0, 4, "root"]],
            "bass": [[0, 4, "root"]],
            "drums": "none",
        }})
        s = styles.parse(data, "test")
        rh = s.pattern("4/4")["rh"]
        self.assertTrue(styles.is_cycle(rh))
        self.assertEqual(styles.bar_of(rh, 1)[0][2], "arp1")
        self.assertEqual(styles.bar_of(rh, 2)[0][2], "chord")
        self.assertEqual(styles.bar_of(rh, 3)[0][2], "arp1")

    def test_waltz_is_piano_vocal_without_drums(self):
        w = styles.get("waltz")
        self.assertEqual(w.instruments.get("melody"), "piano")
        self.assertFalse(w.has_drums("3/4"))
        self.assertTrue(styles.is_cycle(w.pattern("3/4")["lh"]))

    def test_piano_vocal_leaves_the_right_hand_open(self):
        song = load_song(SONGS["3/4"])
        band = arrange.arrange_band(song)
        self.assertIn("right hand rests", " ".join(band.notes))
        rh = band.score.parts[1]
        self.assertFalse(any(not isinstance(n, harmony.ChordSymbol) for n in rh.recurse().notes))
        lh = band.score.parts[2]
        full = [m for m in lh.getElementsByClass(stream.Measure)
                if sum(e.quarterLength for e in m.notesAndRests
                       if not isinstance(e, harmony.ChordSymbol)) >= 3]
        # Four-bar bass-clef phrase: root / root+fifth / root / fifth.
        counts = [len([n for n in m.notes if not isinstance(n, harmony.ChordSymbol)]) for m in full[:4]]
        self.assertEqual(counts, [1, 2, 1, 1])

    def test_ballad_is_piano_vocal_without_drums(self):
        b = styles.get("ballad")
        self.assertEqual(b.instruments.get("melody"), "piano")
        self.assertFalse(b.has_drums("4/4"))
        band = arrange.arrange_band(dataclasses.replace(load_song(SONGS["4/4"]), style="ballad"))
        self.assertNotIn("drums", band.parts)
        self.assertIn("right hand rests", " ".join(band.notes))

    def test_folk_fingerpicks_a_guitar_staff_under_a_piano_melody(self):
        f = styles.get("folk")
        self.assertEqual(f.instruments.get("melody"), "piano")
        self.assertEqual(f.instruments.get("guitar"), "nylon-guitar")
        band = arrange.arrange_band(dataclasses.replace(load_song(SONGS["4/4"]), style="folk"))
        self.assertIn("guitar", band.parts)
        self.assertNotIn("piano", band.parts)
        gtr = band.parts["guitar"].parts[0]
        self.assertTrue(any(not isinstance(n, harmony.ChordSymbol) for n in gtr.recurse().notes))

    def test_guitar_shapes_sit_above_the_bass(self):
        band = arrange.arrange_band(dataclasses.replace(load_song(SONGS["4/4"]), style="country"))
        gtr = band.parts["guitar"].parts[0]
        chords = [n for n in gtr.recurse().notes
                  if not isinstance(n, harmony.ChordSymbol) and hasattr(n, "pitches") and len(n.pitches) > 1]
        self.assertTrue(chords)
        self.assertTrue(all(min(p.midi for p in c.pitches) >= arrange.GUITAR_CHORD_LOW - 1 for c in chords))

    def test_straight_cycles_a_two_bar_phrase(self):
        s = styles.get("straight")
        self.assertTrue(styles.is_cycle(s.pattern("4/4")["rh"]))
        band = arrange.arrange_band(dataclasses.replace(load_song(SONGS["4/4"]), style="straight"))
        rh = band.score.parts[1]
        full = [m for m in rh.getElementsByClass(stream.Measure)
                if sum(e.quarterLength for e in m.notesAndRests
                       if not isinstance(e, harmony.ChordSymbol)) >= 4]
        counts = [len([n for n in m.notes if not isinstance(n, harmony.ChordSymbol)]) for m in full[:2]]
        self.assertEqual(counts, [4, 2])   # four beat-chords, then two half-note chords

    def test_keep_rh_without_piano_melody_is_refused(self):
        with self.assertRaises(styles.StyleError):
            styles.parse(minimal(keep_rh=True), "test")

    def test_every_style_cycles_a_phrase_on_some_part(self):
        """No style is stuck on a single bar forever (the arranger-keyboard feel)."""
        for s in styles.catalog().values():
            for meter, pat in s.meters.items():
                cycled = any(styles.is_cycle(pat[p]) for p in ("rh", "lh", "guitar", "bass")
                             if isinstance(pat.get(p), list))
                with self.subTest(style=s.id, meter=meter):
                    self.assertTrue(cycled, f"{s.id} {meter} has no phrase cycle")

    def test_lullaby_keeps_a_right_hand_that_avoids_the_melody(self):
        song = dataclasses.replace(load_song(SONGS["6/8"]), style="lullaby")
        band = arrange.arrange_band(song)
        self.assertIn("leaves the melody", " ".join(band.notes))
        rh = band.score.parts[1]
        self.assertTrue(any(not isinstance(n, harmony.ChordSymbol) for n in rh.recurse().notes))
        timeline = arrange.chord_timeline(song.melody)
        for n in rh.recurse().notes:
            if isinstance(n, harmony.ChordSymbol):
                continue
            t = float(n.getOffsetInHierarchy(rh))
            blocked = arrange.melody_names_at(song, t)
            names = {p.name for p in (n.pitches if hasattr(n, "pitches") else [n.pitch])}
            self.assertFalse(names & blocked, f"{names} doubles melody {blocked} at {t}")
            cs = arrange.chord_at(timeline, t)
            self.assertTrue(names <= {p.name for p in cs.pitches})


class ArrangeEveryStyleTests(unittest.TestCase):
    """Every style, on a song in each of its meters: the parts line up and the piano plays the chords."""

    @classmethod
    def setUpClass(cls):
        cls.songs = {m: load_song(p) for m, p in SONGS.items()}

    def test_every_style_arranges_cleanly(self):
        for s in styles.catalog().values():
            for meter in s.meters:
                song = self.songs[meter]
                band = arrange.arrange_band(dataclasses.replace(song, style=s.id))
                with self.subTest(style=s.id, meter=meter):
                    self.assertEqual(band.style, s.id)
                    want = bar_lengths(song.melody)
                    for part in band.score.parts:
                        self.assertEqual(bar_lengths(part), want, part.partName)
                    timeline = arrange.chord_timeline(song.melody)
                    acc = next((p for p in band.score.parts if p.partName == "Guitar"), None)
                    if acc is None:
                        pianos = [p for p in band.score.parts if p.partName == "Piano"]
                        acc = pianos[0] if pianos else None
                    if acc is not None:
                        for ch in acc.recurse().notes:
                            if isinstance(ch, harmony.ChordSymbol):
                                continue
                            cs = arrange.chord_at(timeline, float(ch.getOffsetInHierarchy(acc)))
                            allowed = {p.name for p in cs.pitches} | {cs.root().transpose("M6").name}
                            self.assertTrue({p.name for p in ch.pitches} <= allowed, f"{ch} over {cs.figure}")
                    self.assertEqual("drums" in band.parts, s.has_drums(meter))
                    self.assertEqual("guitar" in band.parts, arrange.pattern_plays(s.pattern(meter).get("guitar")))

    def test_a_walking_bass_starts_each_chord_on_its_root_and_steps_into_the_next(self):
        song = self.songs["4/4"]
        band = arrange.arrange_band(dataclasses.replace(song, style="swing"))
        bass = band.parts["bass"].parts[0]
        timeline = arrange.chord_timeline(song.melody)
        notes = list(bass.recurse().getElementsByClass("Note"))
        for a, b in zip(notes, notes[1:]):
            off_a = float(a.getOffsetInHierarchy(bass))
            off_b = float(b.getOffsetInHierarchy(bass))
            cs_a = arrange.chord_at(timeline, off_a)
            cs_b = arrange.chord_at(timeline, off_b)
            if float(b.beat) == 1.0:
                self.assertEqual(b.pitch.name, cs_b.bass().name, f"bar {b.measureNumber}")
                # Chromatic approach only when the chord actually changes; same-chord
                # bars stay on chord tones (a half-step into the same root sounded sour).
                if not arrange.same_chord(cs_a, cs_b):
                    self.assertEqual(abs(b.pitch.midi - a.pitch.midi), 1, f"into bar {b.measureNumber}")
                else:
                    allowed = {p.name for p in cs_a.pitches} | {cs_a.root().transpose("M6").name}
                    self.assertIn(a.pitch.name, allowed, f"bar {b.measureNumber} approach {a.pitch.name}")

    def test_walking_bass_avoids_chromatic_approaches_while_a_chord_holds(self):
        song = self.songs["4/4"]  # Saints: long stretches of C
        band = arrange.arrange_band(dataclasses.replace(song, style="swing"))
        bass = band.parts["bass"].parts[0]
        timeline = arrange.chord_timeline(song.melody)
        sour = []
        for n in bass.recurse().getElementsByClass("Note"):
            off = float(n.getOffsetInHierarchy(bass))
            cs = arrange.chord_at(timeline, off)
            nxt = arrange.chord_at(timeline, off + float(n.quarterLength))
            if cs is None or not arrange.same_chord(cs, nxt or cs):
                continue
            chord_names = {p.name for p in cs.pitches} | {cs.root().transpose("M6").name}
            if n.pitch.name not in chord_names:
                sour.append((off, n.pitch.nameWithOctave, cs.figure))
        self.assertEqual(sour, [], f"non-chord tones while harmony holds: {sour[:8]}")

    def test_a_boogie_line_climbs_from_the_root(self):
        band = arrange.arrange_band(dataclasses.replace(self.songs["4/4"], style="blues-shuffle"))
        bass = band.parts["bass"].parts[0]
        first = list(bass.getElementsByClass(stream.Measure))[0]
        line = list(first.getElementsByClass("Note"))
        self.assertEqual([n.pitch.name for n in line], ["C", "E", "G", "A", "B-", "A", "G", "E"])
        self.assertEqual(min(n.pitch.midi for n in line), line[0].pitch.midi)

    def test_a_swing_style_says_so_on_the_score(self):
        band = arrange.arrange_band(dataclasses.replace(self.songs["4/4"], style="swing"))
        words = [e.content for e in band.score.recurse().getElementsByClass("TextExpression")]
        self.assertEqual(words, ["Swing"])

    def test_swing_and_jazz_waltz_leave_the_piano_out_under_a_sax_lead(self):
        # Charleston shells under a bright alto sat on the tune and sounded discordant.
        for style_id in ("swing", "jazz-waltz"):
            song = self.songs["4/4" if style_id == "swing" else "3/4"]
            band = arrange.arrange_band(dataclasses.replace(song, style=style_id))
            self.assertNotIn("piano", band.parts, style_id)


class SwingTests(unittest.TestCase):
    def test_off_beat_eighths_land_two_thirds_through_the_beat(self):
        song = load_song(SONGS["4/4"])
        band = arrange.arrange_band(dataclasses.replace(song, style="swing"))
        tmp = Path(tempfile.mkdtemp())
        midi = engrave.write_midi(band.performance(), tmp / "plain.mid")
        moved = perform.swing_only(midi, tmp / "swung.mid", song.meter, 0.0, 2 / 3)
        self.assertGreater(moved, 30)
        mid = mido.MidiFile(str(tmp / "swung.mid"))
        tpq = mid.ticks_per_beat
        fractions = set()
        for tr in mid.tracks:
            t = 0
            for msg in tr:
                t += msg.time
                if msg.type == "note_on" and msg.velocity and msg.channel == 9 and msg.note == 51:   # the ride
                    fractions.add(round((t / tpq) % 1, 2))
        self.assertEqual(fractions, {0.0, 0.67})

    def test_straight_styles_are_left_alone(self):
        song = load_song(SONGS["4/4"])
        band = arrange.arrange_band(dataclasses.replace(song, style="pop"))
        tmp = Path(tempfile.mkdtemp())
        midi = engrave.write_midi(band.performance(), tmp / "plain.mid")
        self.assertEqual(perform.swing_only(midi, tmp / "same.mid", song.meter, 0.0, 0.5), 0)


class SetStyleTests(unittest.TestCase):
    def copy(self, name):
        path = Path(tempfile.mkdtemp()) / name
        path.write_text((ROOT / "songs" / name).read_text())
        return path

    def test_only_the_style_and_tempo_lines_change(self):
        from copyist.song import set_style
        path = self.copy("when-the-saints.yaml")
        before = path.read_text().splitlines()
        set_style(path, "swing", 132)
        after = path.read_text().splitlines()
        changed = [(a, b) for a, b in zip(before, after) if a != b]
        self.assertEqual(changed, [("tempo: 112", "tempo: 132"), ("style: straight", "style: swing")])
        self.assertEqual(load_song(path).style, "swing")

    def test_a_dotted_quarter_tempo_keeps_its_unit(self):
        from copyist.song import set_style
        path = self.copy("silent-night.yaml")
        set_style(path, "celtic-jig", 110)
        self.assertIn('tempo: "3/8=110"', path.read_text())
        self.assertIn("style: celtic-jig", path.read_text())

    def test_a_song_without_a_style_gets_one(self):
        from copyist.song import set_style
        path = self.copy("when-the-saints.yaml")
        path.write_text(path.read_text().replace("style: straight\n", ""))
        set_style(path, "rock")
        self.assertEqual(load_song(path).style, "rock")


class GalleryTests(unittest.TestCase):
    def test_the_gallery_plays_every_style_for_the_meter_at_a_tempo_that_suits_it(self):
        song = load_song(SONGS["4/4"])
        out = Path(tempfile.mkdtemp(prefix="copyist-gallery-"))
        played = []

        def fake_band(midi, wav, style=None, cache=None, stems_dir=None):
            played.append((style, mido.MidiFile(str(midi)).length))
            wav.write_bytes(b"RIFF")
            return render.BandAudio(wav, "sampled")
        with mock.patch.object(render, "render_band", fake_band):
            entries = gallery.build(song, out, only=["ballad", "rock", "march"])
        self.assertEqual([e["style"] for e in entries], ["ballad", "rock", "march"])
        tempos = {e["style"]: e["tempo"] for e in entries}
        self.assertEqual(tempos, {"ballad": 92, "rock": 112, "march": 112})     # the song is at 112
        lengths = dict(played)
        self.assertGreater(lengths["ballad"], lengths["rock"] * 1.15)            # slowed to a ballad's pace
        index = json.loads((out / song.slug / "gallery" / gallery.INDEX).read_text())
        self.assertEqual([e["style"] for e in index["styles"]], ["ballad", "rock", "march"])


class TakesGalleryTests(unittest.TestCase):
    def test_a_finished_take_in_each_style_uses_its_words_and_tempo(self):
        import os
        import stat
        from copyist.cli import main
        tmp = Path(tempfile.mkdtemp(prefix="copyist-takes-"))
        binary = tmp / "yue-synth"
        binary.write_text("#!/usr/bin/env python3\nimport sys\nfrom pathlib import Path\n"
                          "args = sys.argv[1:]\nPath(args[args.index('--out') + 1]).write_bytes(b'RIFF')\n")
        binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
        (tmp / "m.gguf").write_bytes(b"m")
        (tmp / "v.gguf").write_bytes(b"v")
        env = {"COPYIST_YUE_SYNTH": str(binary), "COPYIST_YUE_MODEL": str(tmp / "m.gguf"),
               "COPYIST_YUE_VAE": str(tmp / "v.gguf")}
        out = tmp / "out"
        with mock.patch.dict(os.environ, env):
            code = main(["gallery", str(SONGS["4/4"]), "--takes", "--styles", "swing,ballad", "--out", str(out),
                         "--prefix", "lightson, in the style of lightson."])
        self.assertEqual(code, 0)
        folder = out / "when-the-saints" / "gallery"
        index = {e["style"]: e for e in json.loads((folder / gallery.INDEX).read_text())["styles"]}
        self.assertEqual(set(index), {"ballad", "swing"})
        swing = json.loads((folder / "takes" / "swing" / "yue-request.json").read_text())
        self.assertTrue(swing["style"].startswith("lightson, in the style of lightson. English, swing jazz"))
        self.assertIn("112 BPM", swing["style"])
        ballad = json.loads((folder / "takes" / "ballad" / "yue-request.json").read_text())
        self.assertIn("92 BPM", ballad["style"])                   # slowed into the ballad's range
        self.assertEqual(index["ballad"]["take"], "takes/ballad/production.wav")
        self.assertEqual(load_song(SONGS["4/4"]).style, "straight")   # the song file itself is untouched


if __name__ == "__main__":
    unittest.main()
