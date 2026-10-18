"""A local web front end for Copyist: `copyist serve` (docs/web.md).

It reads the project folder (songs/, out/, .cache/lora/) and runs the copyist
command for anything that makes something, one job at a time, since the GPU
can only do one. It listens on 127.0.0.1 only, and refuses requests that come
from other sites or other host names.
"""
from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import yaml

STATIC = Path(__file__).parent / "static"
AUDIO = (".wav", ".mp3", ".flac", ".m4a", ".ogg")
SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,99}")
TAKE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
UPLOAD_LIMIT = 400 * 1024 * 1024                 # a long lossless recording, with room to spare
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/markdown", ".md")


# ------------------------------------------------------------------- reading

def read_yaml(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def report_checks(path: Path) -> dict | None:
    """The validation report's verdict and its table of checks."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    verdict = re.search(r"\*\*Finished:\*\*\s*(.+)", text)
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[1] in ("pass", "fail", "warn", "warning"):
            rows.append({"check": cells[0], "result": cells[1], "where": cells[2], "details": cells[3]})
    return {"verdict": verdict.group(1).strip() if verdict else None, "checks": rows}


def follow_summary(folder: Path) -> str | None:
    """The first line of any `follow` report under a take's folder."""
    for md in sorted(folder.rglob("*-follow.md")):
        for line in md.read_text(encoding="utf-8").splitlines():
            if re.match(r"\d+ of \d+ sung notes", line):
                return line
    return None


DEMO = Path(__file__).resolve().parents[1] / "demo"


class Project:
    def __init__(self, root: Path, demo: bool = False):
        self.root = Path(root).expanduser().resolve()
        self.songs_dir = self.root / "songs"
        self.out = self.root / "out"
        self.loras = self.root / ".cache" / "lora"
        self.songs_dir.mkdir(parents=True, exist_ok=True)
        self.out.mkdir(parents=True, exist_ok=True)
        if demo and not any(self.songs_dir.glob("*.yaml")):   # a new library starts with a song to hear
            for song in DEMO.glob("*.yaml"):
                shutil.copy(song, self.songs_dir / song.name)

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root).as_posix()

    def song_path(self, slug: str) -> Path | None:
        if not SLUG.fullmatch(slug):
            return None
        p = self.songs_dir / f"{slug}.yaml"
        return p if p.is_file() else None

    def songs(self) -> list[dict]:
        items = []
        for p in sorted(self.songs_dir.glob("*.yaml")):
            d = read_yaml(p)
            items.append({"slug": p.stem, "title": d.get("title", p.stem), "key": d.get("key"),
                          "meter": d.get("meter"), "tempo": d.get("tempo")})
        return items

    def song(self, slug: str) -> dict | None:
        path = self.song_path(slug)
        if not path:
            return None
        d = read_yaml(path)
        out = self.out / slug
        sheets = []
        for name, label in (("lead-sheet.pdf", "Lead sheet"), ("score.pdf", "Full score")):
            if (out / name).is_file():
                sheets.append({"label": label, "path": self.rel(out / name)})
        for part in sorted((out / "parts").glob("*.pdf")):
            sheets.append({"label": f"{part.stem.capitalize()} part", "path": self.rel(part)})
        return {"slug": slug, "title": d.get("title", slug), "credits": d.get("credits") or {},
                "key": d.get("key"), "meter": d.get("meter"), "tempo": d.get("tempo"),
                "style": d.get("style"), "production": d.get("production"),
                "instruments": d.get("instruments"), "verses": d.get("lyrics") or [],
                "report": report_checks(out / "report.md"), "sheets": sheets,
                "recordings": self.recordings(slug), "built": (out / "lead-sheet.pdf").is_file(),
                "band": self.band(slug), "gallery": self.gallery(slug), "styles": styles_for(d.get("meter")),
                "style_in_use": d.get("style") or default_style_for(d.get("meter")),
                "default_style": default_style(path)}

    def recordings(self, slug: str) -> list[dict]:
        out = self.out / slug
        found = []
        takes = out / "takes"
        for folder in sorted(takes.iterdir() if takes.is_dir() else [], key=lambda p: p.stat().st_mtime, reverse=True):
            audio = next((folder / f"production{e}" for e in AUDIO if (folder / f"production{e}").is_file()), None)
            if not audio:
                continue
            req = read_json(folder / "yue-request.json") or {}
            found.append({"kind": "take", "name": folder.name, "path": self.rel(audio),
                          "when": datetime.fromtimestamp(audio.stat().st_mtime).isoformat(timespec="minutes"),
                          "style": req.get("style"), "seed": req.get("seed"),
                          "voice": [a.get("name") for a in req.get("adapters") or []],
                          "follow": follow_summary(folder)})
        first = out / "production" / "production.wav"
        if first.is_file():
            req = read_json(out / "production" / "yue-request.json") or {}
            found.append({"kind": "take", "name": "production", "path": self.rel(first),
                          "when": datetime.fromtimestamp(first.stat().st_mtime).isoformat(timespec="minutes"),
                          "style": req.get("style"), "seed": req.get("seed"), "voice": [],
                          "follow": follow_summary(out / "production")})
        sung = out / "sung"
        for folder in sorted(sung.iterdir() if sung.is_dir() else []):
            if (folder / "mix.wav").is_file():
                found.append({"kind": "sung", "name": folder.name, "path": self.rel(folder / "mix.wav")})
        if (out / f"{slug}.wav").is_file():
            found.append({"kind": "preview", "name": "preview", "path": self.rel(out / f"{slug}.wav")})
        return found

    def band(self, slug: str) -> dict | None:
        """The score played by the band: the recording, what played it, and the stems."""
        out = self.out / slug
        wav = out / f"{slug}.wav"
        if not wav.is_file():
            return None
        info = read_json(out / "audio.json") or {"engine": "soundfont", "parts": [], "credits": [], "note": ""}
        for part in info.get("parts", []):
            stem = out / "stems" / (part.get("stem") or "")
            part["path"] = self.rel(stem) if part.get("stem") and stem.is_file() else None
        return {**info, "path": self.rel(wav),
                "when": datetime.fromtimestamp(wav.stat().st_mtime).isoformat(timespec="minutes")}

    def gallery(self, slug: str) -> list[dict]:
        """The song played in each style (`copyist gallery`), newest render of each."""
        from ..gallery import read
        folder = self.out / slug / "gallery"
        out = []
        for e in read(folder):
            wav, take = folder / str(e.get("file", "-")), folder / str(e.get("take", "-"))
            if wav.is_file() or take.is_file():
                out.append({**e, "path": self.rel(wav) if wav.is_file() else None,
                            "take_path": self.rel(take) if take.is_file() else None})
        return out

    def writings(self) -> list[dict]:
        """Songs being written (`copyist write`): out/<slug>/write/candidates.json, newest first."""
        from ..write import INDEX
        found = []
        for index in self.out.glob(f"*/write/{INDEX}"):
            d = read_json(index) or {}
            cands = d.get("candidates") or []
            found.append({"slug": index.parent.parent.name, "title": d.get("title") or index.parent.parent.name,
                          "candidates": len(cands), "usable": sum(bool(c.get("ok")) for c in cands),
                          "kept": d.get("kept"), "when": index.stat().st_mtime})
        return sorted(found, key=lambda w: w["when"], reverse=True)

    def writing(self, slug: str) -> dict | None:
        """One song being written: its candidates, best first, with paths the page can play."""
        from ..write import INDEX, VOICES
        if not SLUG.fullmatch(slug):
            return None
        folder = self.out / slug / "write"
        d = read_json(folder / INDEX)
        if d is None:
            return None
        for c in d.get("candidates") or []:
            for key in ("preview", "take", "song"):
                f = folder / str(c.get(key) or "-")
                c[f"{key}_path"] = self.rel(f) if c.get(key) and f.is_file() else None
            report = folder / c["folder"] / "report.md"
            c["report_path"] = self.rel(report) if report.is_file() else None
        lyrics = folder / "lyrics.txt"
        d["lyrics"] = lyrics.read_text(encoding="utf-8") if lyrics.is_file() else ""
        d["song_exists"] = (self.songs_dir / f"{slug}.yaml").is_file()
        d["voices"] = list(VOICES)
        d["next_seed"] = max([c["seed"] for c in d.get("candidates") or []] + [0]) + 1
        return d

    def transcriptions(self) -> list[dict]:
        """Recordings transcribed (`copyist transcribe`), newest first."""
        from ..transcribe import INDEX
        found = []
        for index in self.out.glob(f"*/transcribe/{INDEX}"):
            d = read_json(index) or {}
            found.append({"slug": index.parent.parent.name, "title": d.get("title") or index.parent.parent.name,
                          "kept": (self.songs_dir / f"{index.parent.parent.name}.yaml").is_file(),
                          "when": index.stat().st_mtime})
        return sorted(found, key=lambda w: w["when"], reverse=True)

    def transcription(self, slug: str) -> dict | None:
        """One transcription: its facts, doubts and notes, and the two recordings to compare."""
        from ..transcribe import INDEX
        if not SLUG.fullmatch(slug):
            return None
        folder = self.out / slug / "transcribe"
        d = read_json(folder / INDEX)
        if d is None:
            return {"slug": slug, "title": slug, "pending": True} if folder.is_dir() else None
        for key, name in (("source_path", d.get("source")), ("preview_path", d.get("preview")),
                          ("report_path", "report.md"), ("song_path", d.get("song"))):
            f = folder / str(name or "-")
            d[key] = self.rel(f) if name and f.is_file() else None
        target = self.songs_dir / f"{slug}.yaml"
        song = folder / str(d.get("song") or "-")
        d["kept"] = target.is_file() and song.is_file() and target.read_bytes() == song.read_bytes()
        d["song_exists"] = target.is_file()
        return d

    def voices(self) -> list[dict]:
        """Trained LoRAs, newest checkpoint first, with the style line their songs trained under."""
        voices = []
        for run in sorted(self.loras.glob("*/lora")) if self.loras.is_dir() else []:
            name = run.parent.name
            style = common_style(run.parent / "songs.jsonl")
            steps = sorted(run.glob("step-*.safetensors"), key=lambda p: int(re.sub(r"\D", "", p.stem) or 0), reverse=True)
            for ck in steps:
                voices.append({"id": self.rel(ck), "label": f"{name}, step {ck.stem.split('-')[1]}", "style": style})
        return voices

    def training(self) -> list[dict]:
        runs = []
        for out in sorted(self.loras.glob("*/train-output.txt")) if self.loras.is_dir() else []:
            runs.append(parse_training(out))
        return runs

    def pages(self, rel: str) -> list[str] | None:
        """A PDF's pages as PNGs (rendered once per version of the PDF, kept in out/.pages/)."""
        pdf = self.file(rel)
        if not pdf or pdf.suffix.lower() != ".pdf":
            return None
        stamp = int(pdf.stat().st_mtime)
        folder = self.out / ".pages" / pdf.relative_to(self.out).with_suffix("") / str(stamp)
        if not folder.is_dir():
            import pymupdf as fitz
            tmp = folder.with_name(folder.name + ".tmp")
            tmp.mkdir(parents=True, exist_ok=True)
            with fitz.open(pdf) as doc:
                for i, page in enumerate(doc, 1):
                    page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False).save(tmp / f"page-{i}.png")
            tmp.replace(folder)
        return [self.rel(p) for p in sorted(folder.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[1]))]

    def file(self, rel: str) -> Path | None:
        """A file the browser may fetch: anything under out/."""
        p = (self.root / unquote(rel)).resolve()
        try:
            p.relative_to(self.out.resolve())
        except ValueError:
            return None
        return p if p.is_file() else None


_STYLE_CACHE: dict[Path, tuple[float, str | None]] = {}


def default_style(path: Path) -> str | None:
    """The style `copyist produce` uses for this song when given none (parsing the song once per change)."""
    mtime = path.stat().st_mtime
    hit = _STYLE_CACHE.get(path)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        from .. import yue
        from ..song import load_song
        song = load_song(path)
        style = yue.song_production_style(song) or yue.default_style(song)
    except Exception:   # a song that doesn't parse still opens; its checks say what's wrong
        style = None
    _STYLE_CACHE[path] = (mtime, style)
    return style


def common_style(songs_jsonl: Path) -> str | None:
    """The opening the training songs' styles share (trigger word and voice line), cut at a sentence end."""
    try:
        styles = [json.loads(line)["style"] for line in songs_jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError, KeyError):
        return None
    if not styles:
        return None
    prefix = os.path.commonprefix(styles)
    cut = prefix.rfind(". ")
    return prefix[:cut + 1] if cut > 0 else prefix.strip() or None


def parse_training(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    run = {"name": path.parent.name, "step": 0, "steps": None, "per_step": None, "hours_left": None,
           "evals": [], "done": "Done. Adapters" in text, "error": None, "updated": path.stat().st_mtime}
    for m in re.finditer(r"step (\d+)/(\d+) loss [\d.]+ ([\d.]+) s/step, about ([\d.]+) h to go", text):
        run.update(step=int(m.group(1)), steps=int(m.group(2)), per_step=float(m.group(3)),
                   hours_left=float(m.group(4)))
    for m in re.finditer(r"EVAL step (\d+) (\{.*\})", text):
        try:
            run["evals"].append({"step": int(m.group(1)), **json.loads(m.group(2).replace("'", '"'))})
        except ValueError:
            pass
    if "Traceback" in text and not run["done"]:
        run["error"] = text[text.rfind("Traceback"):][-1500:]
    run["checkpoints"] = sorted(p.stem for p in (path.parent / "lora").glob("step-*.safetensors"))
    run["stale_minutes"] = round((time.time() - run["updated"]) / 60)
    return run


# ---------------------------------------------------------------------- jobs

class Jobs:
    """Runs one copyist command at a time and keeps its output."""

    def __init__(self, project: Project):
        self.project = project
        self.lock = threading.Lock()
        self.jobs: list[dict] = []
        self.logs = project.out / ".jobs"

    def running(self) -> dict | None:
        return next((j for j in self.jobs if j["status"] == "running"), None)

    def start(self, label: str, song: str | None, args: list[str]) -> dict:
        with self.lock:
            busy = self.running()
            if busy:
                raise ValueError(f"Wait for “{busy['label']}” to finish first.")
            self.logs.mkdir(parents=True, exist_ok=True)
            job_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            job = {"id": job_id, "label": label, "song": song, "status": "running", "started": time.time(),
                   "ended": None, "code": None, "log": str(self.logs / f"{job_id}.log")}
            self.jobs.insert(0, job)
            del self.jobs[20:]
        threading.Thread(target=self._run, args=(job, args), daemon=True).start()
        return job

    def start_task(self, label: str, task) -> dict:
        """Run `task(job, log)` in this process (downloads), with `job["progress"]` = [done, total]."""
        with self.lock:
            busy = self.running()
            if busy:
                raise ValueError(f"Wait for “{busy['label']}” to finish first.")
            self.logs.mkdir(parents=True, exist_ok=True)
            job_id = datetime.now().strftime("%Y%m%d-%H%M%S")
            job = {"id": job_id, "label": label, "song": None, "status": "running", "started": time.time(),
                   "ended": None, "code": None, "progress": None, "log": str(self.logs / f"{job_id}.log")}
            self.jobs.insert(0, job)
            del self.jobs[20:]

        def run():
            with open(job["log"], "w", encoding="utf-8") as log:
                try:
                    task(job, log)
                    job["code"] = 0
                except Exception as e:   # the page shows what went wrong; the server keeps running
                    log.write(f"{e}\n")
                    job["code"] = 1
            job["status"] = "done" if job["code"] == 0 else "failed"
            job["ended"] = time.time()

        threading.Thread(target=run, daemon=True).start()
        return job

    def _run(self, job: dict, args: list[str]) -> None:
        with open(job["log"], "w", encoding="utf-8") as log:
            log.write("$ copyist " + " ".join(args) + "\n")
            log.flush()
            try:
                p = subprocess.run([sys.executable, "-m", "copyist", *args], cwd=self.project.root,
                                   stdout=log, stderr=subprocess.STDOUT)
                job["code"] = p.returncode
            except OSError as e:
                log.write(f"Couldn't start: {e}\n")
                job["code"] = -1
        job["status"] = "done" if job["code"] == 0 else "failed"
        job["ended"] = time.time()

    def view(self, job: dict) -> dict:
        try:
            text = Path(job["log"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        return {k: v for k, v in job.items() if k != "log"} | {"output": text[-6000:]}

    def find(self, job_id: str) -> dict | None:
        return next((j for j in self.jobs if j["id"] == job_id), None)


def start_download(jobs: Jobs, body: dict) -> dict:
    """Download a pack of instruments, or a group of models once the person has accepted their licence."""
    from .. import instruments, models
    group = body.get("group")
    pack = group[len("instruments-"):] if isinstance(group, str) and group.startswith("instruments-") else None
    if pack in instruments.PACKS:
        label = f"Downloading the instruments: {instruments.PACKS[pack]['label'].lower()}"

        def fetch(job, log):
            def progress(done, total):
                job["progress"] = [done, total]
            log.write(f"{label}\n")
            log.flush()
            for p in instruments.download_pack(pack, progress):
                log.write(f"Ready: {p}\n")
                log.flush()

        return jobs.start_task(label, fetch)
    if group not in models.GROUPS:
        raise ValueError("No such download.")
    if body.get("accept_licence") is not True:
        raise ValueError("Accept the licence first.")
    label = f"Downloading {models.GROUPS[group]['label'].lower()}"

    def task(job, log):
        def progress(done, total):
            job["progress"] = [done, total]
        log.write(f"{label}\n")
        log.flush()
        for p in models.download_group(group, progress):
            log.write(f"Ready: {p}\n")
            log.flush()

    return jobs.start_task(label, task)


def voice_args(project: Project, body: dict, prefix: bool = False) -> list[str]:
    """--lora for the trained voice the page chose (and, for a gallery, its trigger line as --prefix)."""
    voice = body.get("voice")
    if not voice:
        return []
    found = next((v for v in project.voices() if v["id"] == voice), None)
    if not found:
        raise ValueError("No such voice.")
    strength = float(body.get("strength") or 1.0)
    if not 0 < strength <= 2:
        raise ValueError("Voice strength is between 0 and 2.")
    args = ["--lora", f"{voice}:{strength:g}"]
    if prefix and found.get("style"):
        args += ["--prefix", found["style"]]
    return args


def default_style_for(meter) -> str | None:
    from .. import styles
    return styles.default_for(str(meter)) if meter else None


def styles_for(meter) -> list[dict]:
    from .. import styles
    return [{"id": s.id, "name": s.name, "family": s.family, "about": s.about, "feel": s.feel}
            for s in styles.for_meter(str(meter))] if meter else []


def write_args(project: Project, body: dict) -> tuple[str, str | None, list[str]]:
    """Writing melodies for new lyrics (`copyist write`): a new song, more candidates, or keeping one."""
    from .. import styles
    from ..write import VOICES, slug as slug_of
    action = body.get("action")
    if action == "write":
        title = str(body.get("title") or "").strip()
        lyrics = str(body.get("lyrics") or "").strip()
        if not 1 <= len(title) <= 120 or not re.search(r"[A-Za-z0-9]", title):
            raise ValueError("Give the song a title.")
        if not lyrics or len(lyrics) > 20000:
            raise ValueError("Paste the lyrics (up to 20,000 characters).")
        slug = slug_of(title)
        if project.writing(slug) and body.get("seed") is None:
            seed = project.writing(slug)["next_seed"]
        else:
            seed = int(body.get("seed") or 1)
        folder = project.out / slug / "write"
        style, words, voice = body.get("style") or None, (body.get("words") or "").strip()[:300] or None, \
            body.get("voice") or "alto"
    elif action == "write-more":
        slug = body.get("slug")
        d = project.writing(slug) if isinstance(slug, str) else None
        if not d:
            raise ValueError("No such song being written.")
        title, style, words, voice, seed = d.get("title") or slug, d.get("style"), d.get("words"), \
            d.get("voice") or "alto", d["next_seed"]
        folder = project.out / slug / "write"
    elif action == "keep":
        slug = body.get("slug")
        d = project.writing(slug) if isinstance(slug, str) else None
        seed = body.get("seed")
        if not d or not any(c["seed"] == seed and c.get("ok") for c in d.get("candidates") or []):
            raise ValueError("No such candidate.")
        args = ["write", "--title", d.get("title") or slug, "--keep", str(int(seed)), "--build"]
        if body.get("replace") is True:
            args.append("--replace")
        return f"Keeping candidate {seed} and writing its score", slug, args
    else:
        raise ValueError("Unknown action.")
    if style and not styles.get(style):
        raise ValueError("No such style.")
    if voice not in VOICES:
        raise ValueError("No such voice.")
    count = int(body.get("candidates") or 4)
    if not (1 <= count <= 8 and 0 < seed < 2**31):
        raise ValueError("Between 1 and 8 candidates at a time.")
    if action == "write":                             # only once everything is known to be good
        from ..write import INDEX, write_index
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "lyrics.txt").write_text(lyrics + "\n", encoding="utf-8")
        if not (folder / INDEX).is_file():            # so the page can open it before the first melody lands
            write_index(folder, {"title": title, "slug": slug, "style": style, "words": words, "voice": voice,
                                 "candidates": []})
    args = ["write", project.rel(folder / "lyrics.txt"), "--title", title, "--voice", voice,
            "--candidates", str(count), "--seed", str(seed)]
    if style:
        args += ["--style", style]
    if words:
        args += ["--words", words]
    return f"Writing melodies for “{title}”", slug, args


def sheetsage_ready() -> bool:
    from .. import paths
    return bool(paths.find_program("yue-transcribe", "COPYIST_YUE_TRANSCRIBE")
                and (os.environ.get("COPYIST_SHEETSAGE") or paths.find_model("SheetSage2-Q8_0.gguf", "COPYIST_SHEETSAGE")))


def transcribe_args(project: Project, body: dict) -> tuple[str, str | None, list[str]]:
    """Transcribing an uploaded recording, or keeping a transcription."""
    from ..write import slug as slug_of
    action = body.get("action")
    if action == "keep-transcription":
        slug = body.get("slug")
        d = project.transcription(slug) if isinstance(slug, str) else None
        if not d or d.get("pending"):
            raise ValueError("No such transcription.")
        args = ["transcribe", "--title", d.get("title") or slug, "--keep", "--build"]
        if body.get("replace") is True:
            args.append("--replace")
        return "Keeping the transcription and writing its score", slug, args
    title = str(body.get("title") or "").strip()
    if not 1 <= len(title) <= 120 or not re.search(r"[A-Za-z0-9]", title):
        raise ValueError("Give the song a title.")
    upload = project.root / str(body.get("upload") or "-")
    try:
        upload.resolve().relative_to((project.out / "uploads").resolve())
    except ValueError:
        raise ValueError("Choose the recording first.") from None
    if not upload.is_file():
        raise ValueError("The recording didn't arrive; choose it again.")
    engine = body.get("engine") or "open"
    if engine not in ("open", "sheetsage"):
        raise ValueError("No such engine.")
    if engine == "sheetsage" and not sheetsage_ready():
        raise ValueError("SheetSage2 isn't installed here.")
    if engine == "sheetsage" and body.get("accept_licence") is not True:
        raise ValueError("SheetSage2 is for non-commercial use only; accept that first.")
    slug = slug_of(title)
    folder = project.out / slug / "transcribe"
    lyrics = str(body.get("lyrics") or "").strip()
    if len(lyrics) > 20000:
        raise ValueError("The lyrics are too long (up to 20,000 characters).")
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "transcription.json").unlink(missing_ok=True)       # the page shows it as in progress
    args = ["transcribe", project.rel(upload), "--title", title, "--engine", engine]
    if lyrics:
        (folder / "lyrics-given.txt").write_text(lyrics + "\n", encoding="utf-8")
        args += ["--lyrics", project.rel(folder / "lyrics-given.txt")]
    return f"Transcribing “{title}”", slug, args


def job_args(project: Project, body: dict) -> tuple[str, str | None, list[str]]:
    """Turn a request from the page into a copyist command. Only these actions exist."""
    action = body.get("action")
    if action in ("write", "write-more", "keep"):
        return write_args(project, body)
    if action in ("transcribe", "keep-transcription"):
        return transcribe_args(project, body)
    slug = body.get("song")
    path = project.song_path(slug) if isinstance(slug, str) else None
    if not path:
        raise ValueError("No such song.")
    song = project.rel(path)
    if action == "build":
        return "Writing the score", slug, ["build", song]
    if action == "gallery":
        return "Playing it in every style", slug, ["gallery", song]
    if action == "gallery-takes":
        args = ["gallery", song, "--takes"]
        args += voice_args(project, body, prefix=True)
        return "Making a finished take in every style", slug, args
    if action == "use-style":
        from .. import styles
        style = styles.get(body.get("style"))
        meter = read_yaml(path).get("meter")
        if not style or str(meter) not in style.meters:
            raise ValueError("No such style for this song.")
        args = ["use-style", song, style.id]
        if body.get("tempo") is not None:
            tempo = float(body["tempo"])
            if not 20 <= tempo <= 300:
                raise ValueError("Tempo out of range.")
            args += ["--tempo", f"{tempo:g}"]
        return f"Changing the style to {style.name}", slug, args
    if action == "produce":
        args = ["produce", song, "--take", datetime.now().strftime("take-%Y%m%d-%H%M%S")]
        verses = int(body.get("verses") or 1)
        seed = int(body.get("seed") or 831001)
        if not (1 <= verses <= 20 and 0 <= seed < 2**31):
            raise ValueError("Verses or seed out of range.")
        args += ["--verses", str(verses), "--seed", str(seed)]
        style = (body.get("style") or "").strip()
        if style:
            args += ["--style", style[:1500]]
        args += voice_args(project, body)
        return "Making a take", slug, args
    if action == "follow":
        take = body.get("take")
        rec = next((r for r in project.recordings(slug) if r["kind"] == "take" and r["name"] == take), None)
        if not rec or not TAKE.fullmatch(take):
            raise ValueError("No such take.")
        return "Checking the melody", slug, ["follow", song, rec["path"], "--separate"]
    raise ValueError("Unknown action.")


# ---------------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    project: Project
    jobs: Jobs
    port: int
    server_version = "Copyist"

    def log_message(self, fmt, *args):   # quiet; jobs keep their own logs
        pass

    # -- guards
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return urlparse(origin).hostname in ("127.0.0.1", "localhost") and urlparse(origin).port == self.port

    # -- replies
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, data, status=200):
        self._send(status, json.dumps(data).encode(), "application/json")

    def _error(self, status, message):
        self._json({"error": message}, status)

    def _file(self, path: Path):
        size = path.stat().st_size
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range") or "")
        start, end = 0, size - 1
        status = HTTPStatus.OK
        if rng and (rng.group(1) or rng.group(2)):
            if rng.group(1):
                start = int(rng.group(1))
                end = min(int(rng.group(2)), size - 1) if rng.group(2) else size - 1
            else:
                start = max(0, size - int(rng.group(2)))
            if start > end or start >= size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("X-Content-Type-Options", "nosniff")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1 << 16, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    return
                left -= len(chunk)

    # -- routes
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "Open Copyist at http://127.0.0.1.")
        path = urlparse(self.path).path
        p = self.project
        if path in ("/", "/index.html"):
            return self._file(STATIC / "index.html")
        if path.startswith("/static/"):
            f = (STATIC / path[len("/static/"):]).resolve()
            if f.is_file() and STATIC.resolve() in f.parents:
                return self._file(f)
            return self._error(404, "Not found.")
        if path.startswith("/files/"):
            f = p.file(path[len("/files/"):])
            return self._file(f) if f else self._error(404, "Not found.")
        if path == "/api/songs":
            return self._json(p.songs())
        m = re.fullmatch(r"/api/songs/([^/]+)", path)
        if m:
            song = p.song(unquote(m.group(1)))
            return self._json(song) if song else self._error(404, "No such song.")
        if path == "/api/pages":
            q = parse_qs(urlparse(self.path).query).get("file", [""])[0]
            pages = p.pages(q)
            return self._json({"pages": pages}) if pages is not None else self._error(404, "No such sheet.")
        if path == "/api/health":
            from .. import __version__, instruments, models
            from ..render import sfizz_program
            return self._json({"ok": True, "version": __version__, "root": str(p.root),
                               "models": {g: models.group_status(g)["ready"] for g in models.GROUPS},
                               "instruments": {k: instruments.pack_status(k)["ready"] for k in instruments.PACKS},
                               "sfizz": sfizz_program() is not None})
        if path == "/api/models":
            from .. import instruments, models
            from ..render import sfizz_program
            return self._json({"licence": models.LICENCE, "licence_url": models.LICENCE_URL,
                               "folder": str(models.paths.models_dir()),
                               "groups": [models.group_status(g) for g in models.GROUPS],
                               "instruments": [instruments.pack_status(k) for k in instruments.PACKS],
                               "instruments_folder": str(instruments.install_dir()),
                               "sfizz": sfizz_program() is not None})
        if path == "/api/voices":
            return self._json(p.voices())
        if path == "/api/styles":
            from .. import styles
            return self._json([{"id": s.id, "name": s.name, "family": s.family, "about": s.about,
                                "meters": list(s.meters)}
                               for s in sorted(styles.catalog().values(),
                                               key=lambda s: (styles.FAMILIES.index(s.family), s.name))])
        if path == "/api/writing":
            return self._json(p.writings())
        if path == "/api/transcriptions":
            return self._json({"items": p.transcriptions(), "sheetsage": sheetsage_ready()})
        m = re.fullmatch(r"/api/transcriptions/([^/]+)", path)
        if m:
            t = p.transcription(unquote(m.group(1)))
            return self._json(t) if t else self._error(404, "No such transcription.")
        m = re.fullmatch(r"/api/writing/([^/]+)", path)
        if m:
            w = p.writing(unquote(m.group(1)))
            return self._json(w) if w else self._error(404, "No such song being written.")
        if path == "/api/training":
            return self._json(p.training())
        if path == "/api/jobs":
            return self._json([self.jobs.view(j) for j in self.jobs.jobs[:10]])
        m = re.fullmatch(r"/api/jobs/([\w-]+)", path)
        if m:
            job = self.jobs.find(m.group(1))
            return self._json(self.jobs.view(job)) if job else self._error(404, "No such job.")
        return self._error(404, "Not found.")

    def do_POST(self):
        if not (self._host_ok() and self._origin_ok()) or self.headers.get("X-Copyist") != "1":
            return self._error(403, "Requests come from the Copyist page only.")
        if urlparse(self.path).path == "/api/upload":
            return self._upload()
        if urlparse(self.path).path != "/api/jobs":
            return self._error(404, "Not found.")
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(min(length, 65536)) or b"{}")
            if body.get("action") == "download":
                job = start_download(self.jobs, body)
            else:
                label, song, args = job_args(self.project, body)
                job = self.jobs.start(label, song, args)
        except (ValueError, TypeError) as e:
            return self._error(400, str(e))
        return self._json(self.jobs.view(job), 202)


    def _upload(self):
        """A recording from the page, streamed into out/uploads/ (the page can't hand over a path)."""
        name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
        stem, ext = os.path.splitext(os.path.basename(name))
        if ext.lower() not in AUDIO:
            return self._error(400, f"That isn't an audio file Copyist reads ({', '.join(AUDIO)}).")
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if not 0 < length <= UPLOAD_LIMIT:
            return self._error(400, "The recording is empty or too big (up to 400 MB).")
        safe = re.sub(r"[^A-Za-z0-9_-]+", "-", stem).strip("-")[:60] or "recording"
        folder = self.project.out / "uploads"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{safe}{ext.lower()}"
        left = length
        with open(target, "wb") as f:
            while left > 0:
                chunk = self.rfile.read(min(left, 1 << 20))
                if not chunk:
                    break
                f.write(chunk)
                left -= len(chunk)
        if left:
            target.unlink(missing_ok=True)
            return self._error(400, "The recording didn't arrive in full; try again.")
        return self._json({"upload": self.project.rel(target), "name": os.path.basename(name)}, 201)


def make_server(root: Path, port: int = 8765, demo: bool = False) -> ThreadingHTTPServer:
    project = Project(root, demo=demo)
    handler = type("CopyistHandler", (Handler,), {"project": project, "jobs": Jobs(project)})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    handler.port = server.server_address[1]
    return server


def serve(root: Path, port: int = 8765, open_browser: bool = False, machine: bool = False, demo: bool = False) -> None:
    """Serve the page. `machine` prints one JSON line first, for the desktop app to read."""
    from .. import __version__
    server = make_server(root, port, demo=demo)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    if machine:
        print(json.dumps({"copyist": "ready", "url": url, "port": server.server_address[1],
                          "version": __version__, "root": str(server.RequestHandlerClass.project.root)}), flush=True)
    else:
        print(f"Copyist is at {url} (Ctrl-C to stop)", flush=True)
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
