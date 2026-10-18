import json
import os
import stat
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

import mido
import numpy as np

from copyist import instruments, mixdown, render

FAKE_SFIZZ = textwrap.dedent('''\
    #!{python}
    """Stands in for sfizz_render: a second of a tone per note in the MIDI, and a log of what it was asked."""
    import json, sys, wave
    import numpy as np
    args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
    with open(args["--wav"] + ".args.json", "w") as f:
        json.dump(args, f)
    sr = int(args["-s"])
    t = np.arange(sr) / sr
    tone = (0.1 * np.sin(2 * np.pi * 440 * t) * 32767).astype("<i2")
    with wave.open(args["--wav"], "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes(np.repeat(tone, 2).tobytes())
''')


def band_midi(path: Path) -> Path:
    """A conductor track and four parts, as music21 writes them."""
    mid = mido.MidiFile(type=1, ticks_per_beat=480)
    conductor = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=600000, time=0),
                                mido.MetaMessage("time_signature", numerator=3, denominator=4, time=0)])
    mid.tracks.append(conductor)
    for name, channel, pitches in (("Voice", 0, [67, 69]), ("Piano", 1, [72, 76]), ("Piano", 1, [48]),
                                   ("Bass", 2, [36]), ("Drums", 9, [36, 42])):
        tr = mido.MidiTrack([mido.MetaMessage("track_name", name=name, time=0)])
        for p in pitches:
            tr.append(mido.Message("note_on", channel=channel, note=p, velocity=80, time=0))
            tr.append(mido.Message("note_off", channel=channel, note=p, velocity=0, time=480))
        if name == "Piano" and pitches[0] == 72:
            tr.append(mido.Message("control_change", channel=1, control=64, value=127, time=0))
        mid.tracks.append(tr)
    mid.save(str(path))
    return path


class SplitTests(unittest.TestCase):
    def test_each_part_keeps_the_tempo_and_only_its_own_notes(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-split-"))
        parts = render.split_parts(band_midi(tmp / "band.mid"), tmp / "parts")
        self.assertEqual(list(parts), ["melody", "piano", "bass", "drums"])
        for part, path in parts.items():
            mid = mido.MidiFile(str(path))
            tempos = [m for m in mid if m.type == "set_tempo"]
            self.assertEqual([m.tempo for m in tempos], [600000], part)
            self.assertAlmostEqual(mid.length, 1.2, places=3)     # every part runs the song's length
            notes = sorted(m.note for m in mid if m.type == "note_on")
            expected = {"melody": [67, 69], "piano": [48, 72, 76], "bass": [36], "drums": [36, 42]}[part]
            self.assertEqual(notes, expected, part)
        pedal = [m for m in mido.MidiFile(str(parts["piano"])) if m.type == "control_change"]
        self.assertEqual(len(pedal), 1)


class RenderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="copyist-render-"))
        self.sfizz = self.tmp / "sfizz_render"
        self.sfizz.write_text(FAKE_SFIZZ.format(python=sys.executable))
        self.sfizz.chmod(self.sfizz.stat().st_mode | stat.S_IEXEC)
        lib = self.tmp / "instruments"
        for inst in instruments.CATALOG.values():
            folder = lib / inst.id
            (folder / inst.sfz).parent.mkdir(parents=True, exist_ok=True)
            (folder / inst.sfz).write_text("<region> sample=*sine\n")
            (folder / instruments.COMPLETE).write_text(inst.revision)
        self.env = mock.patch.dict(os.environ, {"COPYIST_SFIZZ": str(self.sfizz), "COPYIST_INSTRUMENTS": str(lib),
                                                "COPYIST_HOME": str(self.tmp / "home")})
        self.env.start()
        self.generated = mock.patch.object(instruments, "place_generated", lambda inst, folder: None)
        self.generated.start()
        self.midi = band_midi(self.tmp / "band.mid")

    def tearDown(self):
        self.generated.stop()
        self.env.stop()

    def test_each_part_plays_on_its_instrument_and_is_mixed(self):
        audio = render.render_band(self.midi, self.tmp / "out" / "song.wav", "waltz", stems_dir=self.tmp / "out" / "stems")
        self.assertEqual(audio.engine, "sampled")
        # Waltz is piano-vocal; this fixture MIDI still has a drums track, so drums still play.
        self.assertEqual(audio.instruments, {"melody": "piano", "piano": "piano", "bass": "upright-bass",
                                             "drums": "drums"})
        self.assertEqual(sorted(p.name for p in audio.stems.values()),
                         ["bass.wav", "drums.wav", "melody.wav", "piano.wav"])
        x, sr = mixdown.read(audio.wav)
        self.assertEqual(sr, render.SAMPLE_RATE)
        self.assertLessEqual(np.abs(x).max(), 10 ** (-1 / 20) + 1e-3)
        self.assertAlmostEqual(audio.loudness, mixdown.TARGET_LUFS, delta=1.0)
        self.assertIn(instruments.CATALOG["piano"].credit, audio.credits)
        summary = json.loads(json.dumps(audio.summary()))
        self.assertEqual([p["part"] for p in summary["parts"]], ["melody", "piano", "bass", "drums"])
        self.assertTrue(any("Salamander" in line for line in audio.report_lines()))

    def test_without_sfizz_the_soundfont_plays_and_says_why(self):
        with mock.patch.dict(os.environ, {"COPYIST_SFIZZ": ""}), \
                mock.patch.object(render, "sfizz_program", lambda: None), \
                mock.patch.object(render, "soundfont_path", lambda cache: Path("GeneralUser-GS.sf2")), \
                mock.patch.object(render, "render_midi", lambda midi, wav, sf: wav) as fake:
            audio = render.render_band(self.midi, self.tmp / "song.wav", "waltz")
        self.assertEqual(audio.engine, "soundfont")
        self.assertIn("sfizz isn't installed", audio.note)
        self.assertIn("SoundFont", audio.report_lines()[0])

    def test_missing_instruments_are_named(self):
        (Path(os.environ["COPYIST_INSTRUMENTS"]) / "drums" / instruments.COMPLETE).unlink()
        with mock.patch.object(render, "soundfont_path", lambda cache: Path("GeneralUser-GS.sf2")), \
                mock.patch.object(render, "render_midi", lambda midi, wav, sf: wav):
            audio = render.render_band(self.midi, self.tmp / "song.wav", "waltz")
        self.assertEqual(audio.engine, "soundfont")
        self.assertIn("drums", audio.note)


class MixdownTests(unittest.TestCase):
    sr = 48000

    def tone(self, db, seconds=3.0, freq=1000.0):
        t = np.arange(int(seconds * self.sr)) / self.sr
        x = (10 ** (db / 20) * np.sin(2 * np.pi * freq * t)).astype(np.float32)
        return np.stack([x, x], axis=1)

    def test_loudness_of_a_sine_matches_bs1770(self):
        # A 1 kHz sine at -20 dBFS in both channels measures about -20 LUFS.
        self.assertAlmostEqual(mixdown.loudness(self.tone(-20), self.sr), -20.0, delta=0.3)
        self.assertEqual(mixdown.loudness(np.zeros((self.sr, 2), np.float32), self.sr), float("-inf"))

    def test_the_limiter_holds_the_ceiling(self):
        x = self.tone(-12)
        x[self.sr: self.sr + 2000] *= 8                 # a loud burst, +6 dBFS
        out, reduced = mixdown.limit(x, self.sr)
        self.assertLessEqual(np.abs(out).max(), 10 ** (mixdown.CEILING_DB / 20) + 1e-6)
        self.assertGreater(reduced, 6.0)
        self.assertAlmostEqual(float(np.abs(out[:self.sr // 2]).max()), 10 ** (-12 / 20), places=3)

    def test_parts_are_balanced_by_loudness(self):
        parts = {"melody": self.tone(-30, freq=440), "piano": self.tone(-10, freq=330)}
        m = mixdown.mix(parts, self.sr, {"melody": 0.0, "piano": -6.0}, {"melody": 0.0, "piano": 0.0})
        diff = mixdown.loudness(m.stems["melody"], self.sr) - mixdown.loudness(m.stems["piano"], self.sr)
        self.assertAlmostEqual(diff, 6.0, delta=0.5)
        self.assertAlmostEqual(m.loudness, mixdown.TARGET_LUFS, delta=0.5)

    def test_parts_sit_in_the_stereo_field(self):
        x = self.tone(-20, seconds=1.0)
        left = mixdown.pan(x, -1.0)
        right = mixdown.pan(x, 1.0)
        centre = mixdown.pan(x, 0.0)
        self.assertGreater(np.abs(left[:, 0]).mean(), np.abs(left[:, 1]).mean() * 8)
        self.assertGreater(np.abs(right[:, 1]).mean(), np.abs(right[:, 0]).mean() * 8)
        self.assertAlmostEqual(float(np.abs(centre[:, 0]).mean()), float(np.abs(centre[:, 1]).mean()), delta=1e-4)
        parts = {"melody": self.tone(-20, freq=440), "piano": self.tone(-20, freq=330),
                 "drums": self.tone(-20, freq=200)}
        m = mixdown.mix(parts, self.sr, {k: 0.0 for k in parts}, {k: 0.0 for k in parts})
        piano_l = float(np.abs(m.stems["piano"][:, 0]).mean())
        piano_r = float(np.abs(m.stems["piano"][:, 1]).mean())
        drums_l = float(np.abs(m.stems["drums"][:, 0]).mean())
        drums_r = float(np.abs(m.stems["drums"][:, 1]).mean())
        self.assertGreater(piano_l, piano_r)
        self.assertGreater(drums_r, drums_l)

    def test_room_keeps_a_panned_part_on_its_side(self):
        # Wet used to collapse to mono; broadband left-panned dry must stay left (sines
        # can hit a null on one IR channel and lie).
        rng = np.random.default_rng(0)
        noise = (rng.standard_normal((self.sr, 2)) * 0.05).astype(np.float32)
        left = mixdown.pan(noise, -1.0)
        wet = mixdown.convolve(left, mixdown.room_impulse(self.sr))
        self.assertGreater(float(np.abs(wet[:, 0]).mean()), float(np.abs(wet[:, 1]).mean()) * 1.8)

    def test_wav_round_trip_in_24_bits(self):
        path = Path(tempfile.mkdtemp()) / "x.wav"
        x = self.tone(-6, seconds=0.1)
        mixdown.write(path, x, self.sr, bits=24)
        y, sr = mixdown.read(path)
        self.assertEqual(sr, self.sr)
        self.assertLess(np.abs(y - x).max(), 1e-6)


if __name__ == "__main__":
    unittest.main()
