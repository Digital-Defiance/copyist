"""Separating the vocal with Demucs: offline once its model is downloaded."""
from __future__ import annotations

import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import stems

FAKE_DEMUCS = """#!{python}
# Stands in for demucs: logs whether it ran offline; fails offline until the model is "downloaded".
import os, sys
from pathlib import Path
here = Path(sys.argv[0]).parent
offline = os.environ.get("HF_HUB_OFFLINE") == "1"
with open(here / "runs.txt", "a") as f:
    f.write("offline\\n" if offline else "online\\n")
model = here / "model-downloaded"
if offline and not model.exists():
    sys.exit(1)
model.write_text("yes")
args = sys.argv[1:]
src = Path(args[-1]); out = Path(args[args.index("-o") + 1]) / "htdemucs" / src.stem
out.mkdir(parents=True, exist_ok=True)
(out / "vocals.wav").write_bytes(b"v"); (out / "no_vocals.wav").write_bytes(b"n")
"""


class DemucsTests(unittest.TestCase):
    def test_offline_once_the_model_is_downloaded(self):
        tmp = Path(tempfile.mkdtemp(prefix="copyist-demucs-"))
        demucs = tmp / "demucs"
        demucs.write_text(FAKE_DEMUCS.replace("{python}", sys.executable))
        demucs.chmod(demucs.stat().st_mode | stat.S_IEXEC)
        song = tmp / "song.wav"
        song.write_bytes(b"RIFF")
        with mock.patch.dict(os.environ, {"COPYIST_DEMUCS_DEVICE": "cpu"}):
            stems.split_vocals(song, tmp / "first", binary=str(demucs))
            self.assertEqual((tmp / "runs.txt").read_text().split(), ["offline", "online"])  # downloads once
            stems.split_vocals(song, tmp / "second", binary=str(demucs))
        self.assertEqual((tmp / "runs.txt").read_text().split(), ["offline", "online", "offline"])
        self.assertTrue((tmp / "second" / "htdemucs" / "song" / "vocals.wav").is_file())


if __name__ == "__main__":
    unittest.main()
