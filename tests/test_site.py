"""The GitHub Pages site stays a static advert with install steps."""

from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class SiteFiles(unittest.TestCase):
    def test_required_files_exist(self) -> None:
        for name in (
            "index.html",
            "styles.css",
            "script.js",
            "README.md",
            "CNAME",
            "fonts/instrument-serif.woff2",
            "fonts/instrument-serif-italic.woff2",
            "fonts/instrument-sans.woff2",
            "fonts/source-serif-4.woff2",
            "fonts/source-serif-4-italic.woff2",
            "fonts/OFL.txt",
        ):
            path = SITE / name
            self.assertTrue(path.is_file(), f"missing {path.relative_to(ROOT)}")
        self.assertFalse(
            (SITE / "fonts" / "shantell-sans.woff2").exists(),
            "public site must not ship the handwritten display face",
        )

    def test_typography_uses_instrument_faces(self) -> None:
        css = (SITE / "styles.css").read_text(encoding="utf-8")
        self.assertIn("Instrument Serif", css)
        self.assertIn("Instrument Sans", css)
        self.assertNotIn("shantell", css.lower())
        self.assertNotIn("--pencil", css)

    def test_custom_domain(self) -> None:
        cname = (SITE / "CNAME").read_text(encoding="utf-8").strip()
        self.assertEqual(cname, "copyist.digitaldefiance.org")
        html = (SITE / "index.html").read_text(encoding="utf-8")
        self.assertIn("https://copyist.digitaldefiance.org/", html)

    def test_pages_workflow_deploys_site(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")
        self.assertIn("path: site", workflow)
        self.assertIn("actions/deploy-pages", workflow)


class SiteContent(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.html = (SITE / "index.html").read_text(encoding="utf-8")

    def test_brand_and_tagline(self) -> None:
        self.assertIn("Copyist", self.html)
        self.assertIn("the song, the score, the sound", self.html.lower())

    def test_explains_score_first(self) -> None:
        lower = self.html.lower()
        self.assertIn("score", lower)
        self.assertIn("source of truth", lower)

    def test_features_named(self) -> None:
        lower = self.html.lower()
        for needle in (
            "lead sheet",
            "styles",
            "write",
            "transcribe",
            "yuE2".lower(),
            "copyist serve",
        ):
            self.assertIn(needle, lower)

    def test_install_commands(self) -> None:
        for needle in (
            "brew install --cask digital-defiance/tap/copyist",
            "releases/latest",
            "git clone https://github.com/Digital-Defiance/copyist.git",
            "pip install -e .",
            "scripts/package/run-app.sh",
            "copyist serve",
            'id="make"',
        ):
            self.assertIn(needle, self.html)

    def test_make_music_path(self) -> None:
        lower = self.html.lower()
        self.assertIn("make some music", lower)
        self.assertIn("write a song", lower)
        self.assertIn("install extras", lower)

    def test_relative_assets(self) -> None:
        self.assertIn('href="styles.css"', self.html)
        self.assertIn('src="script.js"', self.html)
        self.assertNotIn('href="/styles.css"', self.html)

    def test_licence_and_org(self) -> None:
        self.assertIn("MIT", self.html)
        self.assertIn("Digital Defiance", self.html)
        self.assertIn("https://github.com/Digital-Defiance/copyist", self.html)


if __name__ == "__main__":
    unittest.main()
