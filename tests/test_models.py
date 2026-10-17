import hashlib
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from copyist import models, paths

ORIGINAL_URL = models.url
BLOB = bytes(range(256)) * 300            # 76,800 bytes
SHA = hashlib.sha256(BLOB).hexdigest()


class RangeServer(BaseHTTPRequestHandler):
    """Serves BLOB, honouring Range like Hugging Face's CDN does."""
    requests: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        RangeServer.requests.append(self.headers.get("Range"))
        start = int(self.headers["Range"][6:-1]) if self.headers.get("Range") else 0
        body = BLOB[start:]
        self.send_response(206 if start else 200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fake_model(sha=SHA, size=len(BLOB)):
    return models.Model("blob", "blob.gguf", "someone/repo", "abc", size, sha, "a test model")


class ModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), RangeServer)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/blob.gguf"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.home = Path(tempfile.mkdtemp(prefix="copyist-home-"))
        self.here = os.getcwd()
        os.chdir(tempfile.mkdtemp(prefix="copyist-cwd-"))     # no developer .cache/ here
        env = {"COPYIST_HOME": str(self.home)}
        self.patches = [mock.patch.dict(os.environ, env),
                        mock.patch.dict(models.CATALOG, {"blob": fake_model()}),
                        mock.patch.dict(models.GROUPS, {"test": {"label": "Test", "why": "testing", "models": ["blob"]}}),
                        mock.patch.object(models, "url", lambda m: self.url)]
        for p in self.patches:
            p.start()
        RangeServer.requests = []

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        os.chdir(self.here)

    def test_data_folder_follows_copyist_home(self):
        self.assertEqual(paths.models_dir(), self.home / "models")

    def test_download_verifies_and_reports_progress(self):
        seen = []
        p = models.download("blob", lambda d, t: seen.append((d, t)))
        self.assertEqual(p.read_bytes(), BLOB)
        self.assertEqual(seen[-1], (len(BLOB), len(BLOB)))
        self.assertEqual(models.status("blob")["state"], "ready")

    def test_an_interrupted_download_resumes(self):
        (self.home / "models").mkdir(parents=True)
        (self.home / "models" / "blob.gguf.part").write_bytes(BLOB[:1000])
        self.assertEqual(models.status("blob")["state"], "partial")
        models.download("blob")
        self.assertEqual(RangeServer.requests, ["bytes=1000-"])
        self.assertEqual((self.home / "models" / "blob.gguf").read_bytes(), BLOB)

    def test_a_wrong_checksum_is_thrown_away(self):
        with mock.patch.dict(models.CATALOG, {"blob": fake_model(sha="0" * 64)}):
            with self.assertRaises(ValueError):
                models.download("blob")
        self.assertFalse(list((self.home / "models").iterdir()))
        self.assertEqual(models.status("blob")["state"], "missing")

    def test_a_group_reports_progress_over_all_its_files(self):
        seen = []
        models.download_group("test", lambda d, t: seen.append((d, t)))
        self.assertTrue(models.group_status("test")["ready"])
        self.assertEqual(seen[-1], (len(BLOB), len(BLOB)))

    def test_developer_copies_count_as_installed(self):
        Path(".cache/yue").mkdir(parents=True)
        Path(".cache/yue/blob.gguf").write_bytes(BLOB)
        self.assertEqual(models.status("blob")["state"], "ready")

    def test_programs_come_from_copyist_bin(self):
        bin_dir = Path(tempfile.mkdtemp())
        (bin_dir / "yue-synth").write_bytes(b"")
        with mock.patch.dict(os.environ, {"COPYIST_BIN": str(bin_dir)}):
            self.assertEqual(paths.find_program("yue-synth"), (bin_dir / "yue-synth").resolve())
        with mock.patch.dict(os.environ, {"COPYIST_YUE_SYNTH": "/opt/yue-synth"}):
            self.assertEqual(paths.find_program("yue-synth", "COPYIST_YUE_SYNTH"), Path("/opt/yue-synth"))

    def test_the_catalog_is_pinned(self):
        for m in models.CATALOG.values():
            if m.id == "blob":
                continue
            self.assertEqual(len(m.revision), 40)
            self.assertEqual(len(m.sha256), 64)
        self.assertEqual(ORIGINAL_URL(models.CATALOG["yue2"]),
                         "https://huggingface.co/Serveurperso/YuE2-GGUF/resolve/e630f2b8f6aedf8254c3186438633c1b5eeaf80a/YuE2-3B-Q6_K.gguf")


if __name__ == "__main__":
    unittest.main()
