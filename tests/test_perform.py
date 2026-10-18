import tempfile
import unittest
from collections import Counter
from pathlib import Path

import mido

from copyist import arrange, engrave, perform
from copyist.song import load_song

ROOT = Path(__file__).resolve().parents[1]


class PerformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.song = load_song(ROOT / "songs" / "amazing-grace.yaml")
        cls.tmp = Path(tempfile.mkdtemp(prefix="copyist-perform-"))
        cls.plain = engrave.write_midi(arrange.arrange_band(cls.song).performance(), cls.tmp / "plain.mid")
        cls.pickup = float(perform.pickup_of(cls.song))
        cls.out = cls.tmp / "performed.mid"
        cls.info = perform.perform(cls.plain, cls.out, cls.song.meter, cls.pickup, seed=1)
        cls.before, _ = perform.read(mido.MidiFile(str(cls.plain)))
        cls.after, cls.others = perform.read(mido.MidiFile(str(cls.out)))
        cls.roles = perform.roles(mido.MidiFile(str(cls.out)), cls.after)
        cls.tpq = mido.MidiFile(str(cls.plain)).ticks_per_beat

    def test_no_note_is_added_lost_or_changed(self):
        key = lambda ns: Counter((n.track, n.channel, n.pitch) for n in ns)
        self.assertEqual(key(self.before), key(self.after))
        self.assertEqual(self.info["notes"], len(self.before))

    def test_the_same_seed_gives_the_same_performance(self):
        again = self.tmp / "again.mid"
        other = self.tmp / "other.mid"
        perform.perform(self.plain, again, self.song.meter, self.pickup, seed=1)
        perform.perform(self.plain, other, self.song.meter, self.pickup, seed=2)
        self.assertEqual(again.read_bytes(), self.out.read_bytes())
        self.assertNotEqual(other.read_bytes(), self.out.read_bytes())

    def test_timing_stays_close_to_the_score(self):
        ticks_per_ms = self.tpq * 80 / 60000          # 80 BPM
        limit = (perform.SIGMA_MS["melody"] * 2.5 + perform.MELODY_LEAD_MS + perform.ROLL_MS * 4) * ticks_per_ms
        before = sorted((n.track, n.pitch, n.start) for n in self.before)
        after = sorted((n.track, n.pitch, n.start) for n in self.after)
        for (t1, p1, s1), (t2, p2, s2) in zip(before, after):
            self.assertLessEqual(abs(s1 - s2), limit + 1, (t1, p1))

    def test_velocities_vary_and_stay_in_range(self):
        vels = [n.velocity for n in self.after]
        self.assertTrue(all(1 <= v <= 127 for v in vels))
        melody = [n.velocity for n in self.after if self.roles[n.track] == "melody"]
        self.assertGreater(len(set(melody)), 8)       # the plain MIDI has one velocity for the melody

    def test_downbeats_lean(self):
        """Accompaniment on a downbeat gets louder, relative to its plain velocity, than off it."""
        shape = perform.shape_for(self.song.meter, self.pickup, self.tpq)
        order = lambda ns: sorted(ns, key=lambda n: (n.track, n.pitch, n.start))
        strong, weak = [], []
        for b, a in zip(order(self.before), order(self.after)):
            if self.roles.get(b.track) in ("piano_rh", "piano_lh", "bass"):
                (strong if shape.strength(b.start) == "down" else weak).append(a.velocity / b.velocity)
        self.assertGreater(sum(strong) / len(strong), sum(weak) / len(weak))

    def test_the_piano_pedals_with_the_harmony(self):
        cc = [m for track in self.others for _, m in track if m.type == "control_change" and m.control == 64]
        self.assertGreater(len(cc), 10)
        self.assertEqual(cc[-1].value, 0)               # the pedal comes up at the end
        self.assertEqual(self.info["pedal_changes"], len(cc) // 2)

    def test_the_ending_slows_and_rings(self):
        tempos = sorted((t, m.tempo) for t, m in self.others[0] if m.type == "set_tempo")
        base = tempos[0][1]
        self.assertGreater(tempos[-1][1], base * 1.2)    # 80% speed at the end means a 25% longer beat
        last_plain = max(n.end for n in self.before if self.roles.get(n.track) != "drums")
        last_performed = max(n.end for n in self.after if self.roles.get(n.track) != "drums")
        self.assertGreater(last_performed, last_plain)

    def test_compound_meters_count_dotted_beats(self):
        s = perform.shape_for("6/8", 0, 480)
        self.assertEqual((s.beats, s.beat_q), (2, 1.5))
        self.assertEqual(s.strength(720), "beat")       # the second dotted-quarter beat
        self.assertEqual(s.strength(240), "off")

    def test_piano_melody_does_not_overlap_hammers(self):
        """Voice-style legato overlaps notes; on a piano sample that clicks."""
        out = self.tmp / "piano-touch.mid"
        perform.perform(self.plain, out, self.song.meter, self.pickup, seed=1, melody_legato=False)
        notes, _ = perform.read(mido.MidiFile(str(out)))
        roles = perform.roles(mido.MidiFile(str(out)), notes)
        line = sorted((n for n in notes if roles.get(n.track) == "melody"), key=lambda n: n.start)
        for a, b in zip(line, line[1:]):
            self.assertLessEqual(a.end, b.start, (a.pitch, b.pitch, a.end, b.start))


if __name__ == "__main__":
    unittest.main()
