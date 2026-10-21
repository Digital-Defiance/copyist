"""Where work runs: CPU jobs at once, and the device a tool's PyTorch can use."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from copyist import compute, stems


class CpuWorkerTests(unittest.TestCase):
    def test_copyist_jobs_caps_the_workers_and_tasks_cap_them_again(self):
        with mock.patch.dict(os.environ, {"COPYIST_JOBS": "3"}):
            self.assertEqual(compute.cpu_workers(), 3)
            self.assertEqual(compute.cpu_workers(10), 3)
            self.assertEqual(compute.cpu_workers(2), 2)
        with mock.patch.dict(os.environ, {"COPYIST_JOBS": "nonsense"}):
            self.assertEqual(compute.cpu_workers(), compute.performance_cores())
        self.assertGreaterEqual(compute.performance_cores(), 1)


class DeviceTests(unittest.TestCase):
    def setUp(self):
        compute.torch_device.cache_clear()

    def tearDown(self):
        compute.torch_device.cache_clear()

    def test_without_an_nvidia_gpu_linux_uses_the_cpu(self):
        with mock.patch.object(sys, "platform", "linux"), mock.patch.object(compute.shutil, "which", lambda name: None):
            self.assertEqual(compute.torch_device("/no/python"), "cpu")

    def test_with_an_nvidia_gpu_it_asks_the_tools_own_pytorch(self):
        folder = Path(tempfile.mkdtemp(prefix="copyist-venv-")) / "bin"
        folder.mkdir()
        (folder / "demucs").write_text("")
        python = folder / "python"
        python.write_text("#!/bin/sh\necho cuda\n")
        python.chmod(0o755)
        self.assertEqual(compute.python_beside(str(folder / "demucs")), str(python))
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(compute.shutil, "which", lambda name: "/usr/bin/nvidia-smi"):
            self.assertEqual(compute.torch_device(str(python)), "cuda")
            self.assertEqual(stems.demucs_device(str(folder / "demucs")), "cuda")
            with mock.patch.dict(os.environ, {"COPYIST_DEMUCS_DEVICE": "cpu"}):
                self.assertEqual(stems.demucs_device(str(folder / "demucs")), "cpu")

    def test_a_mac_uses_metal(self):
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(compute.torch_device(None), "mps")


if __name__ == "__main__":
    unittest.main()
