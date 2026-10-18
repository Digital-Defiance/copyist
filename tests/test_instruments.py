import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import instruments

SAMPLE = b"RIFF fake sample " * 100
SFZ = b"<region> sample=s/one.wav\n"


def fake_instrument(generated=False):
    return instruments.Instrument("test", "A test instrument", "someone/lib", "a" * 40, "test.sfz", "CC0", "",
                                  "https://example.org", generated)


def fake_files(sample=SAMPLE):
    return [("test.sfz", len(SFZ), instruments.git_blob_id(SFZ)),
            ("s/one.wav", len(sample), instruments.git_blob_id(sample))]


class Server:
    """Stands in for raw.githubusercontent.com: serves the files by path, counting requests."""

    def __init__(self, files):
        self.files, self.asked = files, []

    def __call__(self, req, timeout=None):
        path = req.full_url.split("/" + "a" * 40 + "/", 1)[1]
        self.asked.append(path)
        return io.BytesIO(self.files[path])


class ManifestTests(unittest.TestCase):
    def test_every_instrument_has_its_files_listed_with_git_ids(self):
        m = instruments.manifest()
        self.assertEqual(set(m), set(instruments.CATALOG))
        for inst_id, files in m.items():
            paths = {f[0] for f in files}
            inst = instruments.CATALOG[inst_id]
            if inst.synthetic:
                self.assertEqual(files, [])
                continue
            if not inst.generated:
                self.assertIn(inst.sfz, paths)
            for path, size, blob in files:
                self.assertGreater(size, 0, path)
                self.assertRegex(blob, r"^[0-9a-f]{40}$")

    def test_the_clarinet_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "clarinet.sfz").read_text()
        folder = re.search(r"default_path=(\S+)", text).group(1)
        listed = {f[0] for f in instruments.manifest()["clarinet"]}
        names = re.findall(r"sample=(\S+)", text)
        self.assertEqual(len(names), 33)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_organ_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "organ.sfz").read_text()
        listed = {f[0] for f in instruments.manifest()["organ"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertGreaterEqual(len(names), 30)
        for n in names:
            self.assertIn(n, listed)

    def test_the_harp_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "harp.sfz").read_text()
        folder = re.search(r"default_path=(\S+)", text).group(1)
        listed = {f[0] for f in instruments.manifest()["harp"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 23)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_musicbox_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "musicbox.sfz").read_text()
        folder = re.search(r"default_path=(.+)", text).group(1).strip()
        listed = {f[0] for f in instruments.manifest()["musicbox"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 18)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_steel_guitar_sfz_names_samples_in_its_linked_folder(self):
        text = (instruments.SOUND / "steel-guitar.sfz").read_text()
        listed = {f[0] for f in instruments.manifest()["steel-guitar"]}
        target = instruments.SAMPLE_LINKS["steel-guitar"]
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 15)
        for n in names:
            self.assertIn(f"{target}/{n}", listed)

    def test_the_fiddle_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "fiddle.sfz").read_text()
        folder = re.search(r"default_path=(.+)", text).group(1).strip()
        listed = {f[0] for f in instruments.manifest()["fiddle"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 30)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_flute_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "flute.sfz").read_text()
        folder = re.search(r"default_path=(.+)", text).group(1).strip()
        listed = {f[0] for f in instruments.manifest()["flute"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 10)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_oboe_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "oboe.sfz").read_text()
        folder = re.search(r"default_path=(.+)", text).group(1).strip()
        listed = {f[0] for f in instruments.manifest()["oboe"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 18)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_the_sax_sfz_only_names_samples_that_are_downloaded(self):
        text = (instruments.SOUND / "sax.sfz").read_text()
        folder = re.search(r"default_path=(.+)", text).group(1).strip()
        listed = {f[0] for f in instruments.manifest()["sax"]}
        names = [line.split("sample=", 1)[1].strip()
                 for line in text.splitlines() if "sample=" in line]
        self.assertEqual(len(names), 64)
        for n in names:
            self.assertIn(folder + n, listed)

    def test_instruments_that_ask_for_credit_have_a_credit_line(self):
        for inst in instruments.CATALOG.values():
            if "BY" in inst.licence:
                self.assertIn(inst.licence, inst.credit)
        self.assertEqual(instruments.credits(["clarinet", "piano", "drums"]),
                         [instruments.CATALOG["piano"].credit, instruments.CATALOG["drums"].credit])

    def test_git_blob_id_matches_git(self):
        self.assertEqual(instruments.git_blob_id(b"hello\n"), "ce013625030ba8dba906f756967f9e9ca394464a")

    def test_which_instrument_plays_which_part(self):
        self.assertEqual(instruments.instrument_for("melody"), "clarinet")
        self.assertEqual(instruments.instrument_for("melody", "waltz"), "piano")
        self.assertEqual(instruments.instrument_for("melody", "hymn"), "organ")
        self.assertEqual(instruments.instrument_for("piano", "hymn"), "organ")
        self.assertEqual(instruments.instrument_for("melody", "gospel"), "piano")
        self.assertEqual(instruments.instrument_for("piano", "gospel"), "tonewheel")
        self.assertEqual(instruments.instrument_for("piano", "broadway-ballad"), "harp")
        self.assertEqual(instruments.instrument_for("melody", "music-box"), "musicbox")
        self.assertEqual(instruments.instrument_for("guitar", "folk"), "nylon-guitar")
        self.assertEqual(instruments.instrument_for("melody", "country"), "fiddle")
        self.assertEqual(instruments.instrument_for("guitar", "country"), "steel-guitar")
        self.assertEqual(instruments.instrument_for("melody", "country-waltz"), "fiddle")
        self.assertEqual(instruments.instrument_for("guitar", "country-waltz"), "steel-guitar")
        self.assertEqual(instruments.instrument_for("melody", "celtic-jig"), "fiddle")
        self.assertEqual(instruments.instrument_for("melody", "broadway-ballad"), "oboe")
        self.assertEqual(instruments.instrument_for("melody", "broadway-uptempo"), "flute")
        self.assertEqual(instruments.instrument_for("melody", "march"), "flute")
        self.assertEqual(instruments.instrument_for("melody", "swing"), "sax")
        self.assertEqual(instruments.instrument_for("melody", "jazz-waltz"), "sax")
        self.assertEqual(instruments.instrument_for("melody", "blues-shuffle"), "sax")
        self.assertEqual(instruments.instrument_for("melody", "bossa-nova"), "sax")
        self.assertEqual(instruments.instrument_for("guitar", "pop"), "electric-guitar")
        self.assertEqual(instruments.instrument_for("guitar", "rock"), "electric-guitar")
        self.assertEqual(instruments.instrument_for("guitar", "power-ballad"), "electric-guitar")
        self.assertEqual(instruments.instrument_for("guitar", "blues-shuffle"), "electric-guitar")
        self.assertEqual(instruments.instrument_for("piano"), "piano")
        self.assertEqual(instruments.instrument_for("bass", "waltz"), "upright-bass")
        self.assertEqual(instruments.instrument_for("bass", "straight"), "electric-bass")
        self.assertEqual(instruments.instrument_for("drums"), "drums")

    def test_every_pack_lists_real_instruments(self):
        for pack in instruments.PACKS.values():
            for i in pack["instruments"]:
                self.assertIn(i, instruments.CATALOG)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="copyist-home-"))
        self.here = os.getcwd()
        os.chdir(tempfile.mkdtemp(prefix="copyist-cwd-"))       # no developer .cache/ here
        env = {"COPYIST_HOME": str(self.home)}
        self.patches = [mock.patch.dict(os.environ, env),
                        mock.patch.dict(instruments.CATALOG, {"test": fake_instrument()}),
                        mock.patch.object(instruments, "manifest", lambda: {"test": fake_files()})]
        for p in self.patches:
            p.start()
        os.environ.pop("COPYIST_INSTRUMENTS", None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        os.chdir(self.here)

    def test_download_places_and_checks_every_file(self):
        server = Server({"test.sfz": SFZ, "s/one.wav": SAMPLE})
        seen = []
        folder = instruments.download("test", lambda d, t: seen.append((d, t)), opener=server)
        self.assertEqual((folder / "s" / "one.wav").read_bytes(), SAMPLE)
        self.assertEqual(instruments.sfz_path("test"), (folder / "test.sfz").resolve())
        self.assertEqual(instruments.status("test")["state"], "ready")
        self.assertEqual(seen[-1], (len(SFZ) + len(SAMPLE),) * 2)
        instruments.download("test", opener=server)         # already there: nothing fetched again
        self.assertEqual(len(server.asked), 2)

    def test_a_file_that_doesnt_match_is_not_kept(self):
        server = Server({"test.sfz": SFZ, "s/one.wav": SAMPLE[:-1] + b"!"})
        with self.assertRaises(ValueError):
            instruments.download("test", opener=server)
        folder = instruments.install_dir() / "test"
        self.assertFalse((folder / "s" / "one.wav").exists())
        self.assertIsNone(instruments.sfz_path("test"))
        self.assertEqual(instruments.status("test")["state"], "partial")     # the SFZ arrived and stays

    def test_an_interrupted_download_picks_up_where_it_stopped(self):
        folder = instruments.install_dir() / "test"
        folder.mkdir(parents=True)
        (folder / "test.sfz").write_bytes(SFZ)
        server = Server({"test.sfz": SFZ, "s/one.wav": SAMPLE})
        instruments.download("test", opener=server)
        self.assertEqual(server.asked, ["s/one.wav"])

    def test_a_generated_sfz_is_written_next_to_the_samples(self):
        with mock.patch.dict(instruments.CATALOG, {"test": fake_instrument(generated=True)}), \
                mock.patch.object(instruments, "SOUND", Path(tempfile.mkdtemp())) as sound:
            (sound / "test.sfz").write_bytes(b"<region> sample=s/one.wav // ours\n")
            files = [("s/one.wav", len(SAMPLE), instruments.git_blob_id(SAMPLE))]
            with mock.patch.object(instruments, "manifest", lambda: {"test": files}):
                folder = instruments.download("test", opener=Server({"s/one.wav": SAMPLE}))
            self.assertIn(b"// ours", (folder / "test.sfz").read_bytes())

    def test_pack_status_adds_up_its_instruments(self):
        with mock.patch.dict(instruments.PACKS, {"t": {"label": "T", "why": "w", "instruments": ["test"]}}):
            s = instruments.pack_status("t")
        self.assertEqual(s["id"], "instruments-t")
        self.assertEqual(s["size"], len(SFZ) + len(SAMPLE))
        self.assertFalse(s["ready"])


if __name__ == "__main__":
    unittest.main()
