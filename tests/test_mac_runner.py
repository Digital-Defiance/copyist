"""The Mac job runner (scripts/mac/runner.py): order, GPU windows, power, limits, recovery."""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "mac_runner", Path(__file__).resolve().parents[1] / "scripts" / "mac" / "runner.py")
runner = importlib.util.module_from_spec(SPEC)
sys.modules["mac_runner"] = runner
SPEC.loader.exec_module(runner)


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.f = runner.folders(self.root)
        self.notes = []

    def queue(self, name: str, body: str, header: str = "") -> Path:
        path = self.f["queue"] / f"{name}.sh"
        path.write_text((f"# runner: {header}\n" if header else "") + body + "\n", encoding="utf-8")
        return path

    def once(self, power=True):
        return runner.run_once(self.root, notify_fn=self.notes.append, power=lambda: power)

    def grant(self, minutes: float):
        until = runner.now() + timedelta(minutes=minutes)
        (runner.runner_dir(self.root) / "window.json").write_text(json.dumps({"until": until.isoformat()}))

    def test_jobs_run_in_order_in_the_checkout(self):
        self.queue("002-second", "echo two >> order.txt")
        self.queue("001-first", "echo one >> order.txt; echo \"$COPYIST_RUNNER_JOB\"")
        first = self.once()
        second = self.once()
        self.assertEqual((first["job"], first["exit"]), ("001-first", 0))
        self.assertEqual(second["job"], "002-second")
        self.assertEqual((self.root / "order.txt").read_text().split(), ["one", "two"])
        self.assertIn("001-first", (self.f["logs"] / "001-first.log").read_text())
        self.assertTrue((self.f["done"] / "001-first.sh").is_file())
        self.assertEqual(json.loads((self.f["done"] / "001-first.json").read_text())["exit"], 0)
        self.assertIsNone(self.once())
        self.assertEqual(self.notes, ["Started 001-first", "001-first finished", "Started 002-second",
                                      "002-second finished"])

    def test_a_failing_job_is_recorded(self):
        self.queue("001-bad", "exit 3")
        self.assertEqual(self.once()["exit"], 3)
        self.assertEqual(self.notes[-1], "001-bad failed")

    def test_gpu_jobs_wait_for_a_window_and_mains_power(self):
        self.queue("001-gpu", "echo gpu", header="gpu hours=1")
        self.assertIsNone(self.once())
        self.assertIn("waiting for a GPU window",
                      json.loads((runner.runner_dir(self.root) / "heartbeat.json").read_text())["note"])
        self.grant(-5)                                       # a window that has ended
        self.assertIsNone(self.once())
        self.grant(30)
        self.assertIsNone(self.once(power=False))
        result = self.once()
        self.assertEqual((result["exit"], result["gpu"]), (0, True))

    def test_a_job_is_stopped_at_its_limit(self):
        self.queue("001-long", "sleep 30", header="hours=0.0003")
        result = self.once()
        self.assertEqual(result["stopped"], "time limit")
        self.assertNotEqual(result["exit"], 0)
        self.assertLess(result["seconds"], 15)

    def test_header_parsing(self):
        job = runner.read_job(self.queue("001-x", "true", header="gpu hours=6.5"))
        self.assertEqual((job.gpu, job.hours), (True, 6.5))
        self.assertEqual(runner.read_job(self.queue("002-y", "true")).hours, runner.DEFAULT_HOURS)

    def test_a_job_left_running_goes_back_to_the_queue(self):
        (self.f["running"] / "001-interrupted.sh").write_text("true\n")
        runner.recover(self.root)
        self.assertEqual([p.name for p in self.f["queue"].iterdir()], ["001-interrupted.sh"])


if __name__ == "__main__":
    unittest.main()
