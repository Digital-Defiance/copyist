"""Desktop-app path helpers."""
import os
import unittest

from copyist import paths


class DesktopFlag(unittest.TestCase):
    def test_off_by_default(self):
        os.environ.pop("COPYIST_DESKTOP", None)
        self.assertFalse(paths.desktop_app())

    def test_on_when_set(self):
        os.environ["COPYIST_DESKTOP"] = "1"
        try:
            self.assertTrue(paths.desktop_app())
        finally:
            os.environ.pop("COPYIST_DESKTOP", None)


if __name__ == "__main__":
    unittest.main()
