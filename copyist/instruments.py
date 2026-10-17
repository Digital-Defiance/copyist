"""The sampled instruments Copyist plays a score with, and their downloader (docs/sound-set.md).

Each instrument is an SFZ library in a public git repository, pinned to one
commit. Only the files the instrument actually plays are downloaded, and each is
checked against its git object id at that commit (copyist/sound/manifest.json),
so what lands on disk is byte for byte what the library's authors published.
A file is only moved into place once it checks out, so an interrupted download
picks up where it stopped.

The clarinet is the one exception to "as published": VSCO ships it as WAV files
only, so Copyist writes its SFZ (copyist/sound/clarinet.sfz, made by
scripts/instruments/clarinet.py) next to the samples.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable
from urllib.parse import quote
from urllib.request import Request, urlopen

from . import paths

SOUND = Path(__file__).parent / "sound"
COMPLETE = ".copyist-complete"


@dataclass(frozen=True)
class Instrument:
    id: str
    label: str
    repo: str          # owner/name on GitHub
    revision: str
    sfz: str           # the instrument's SFZ, relative to its folder
    licence: str
    credit: str        # the credit line its licence asks for ("" when none is needed)
    home: str
    generated: bool = False   # Copyist writes the SFZ (from copyist/sound/)


CATALOG = {i.id: i for i in (
    Instrument("piano", "Salamander Grand Piano V3 (a Yamaha C5)", "sfzinstruments/SalamanderGrandPiano",
               "3382bf9496bba2486f5ab0de55a264d1dfc38404", "Salamander Grand Piano V3.sfz", "CC BY 3.0",
               "Salamander Grand Piano V3 by Alexander Holm (CC BY 3.0)",
               "https://github.com/sfzinstruments/SalamanderGrandPiano"),
    Instrument("electric-bass", "Karoryfer Growlybass (a Squier Jazz Bass)", "sfzinstruments/karoryfer.growlybass",
               "4f483268fc66b5a6d5781d421c0d11b8d08d3fc6", "growlybass_clean.sfz", "CC0", "",
               "https://github.com/sfzinstruments/karoryfer.growlybass"),
    Instrument("upright-bass", "Karoryfer Meatbass (a 1958 double bass), pizzicato",
               "sfzinstruments/karoryfer.meatbass", "ac9e859564bda286ab5ec672d00ff1aa2fef2895",
               "Programs/04_pizz.sfz", "CC0", "", "https://github.com/sfzinstruments/karoryfer.meatbass"),
    Instrument("drums", "AVL Drumkits: Black Pearl 4-piece", "studiorack/avl-drumkits",
               "b06cb2c27359cbc68a830a82bddced05bd73d1a0", "Black_Pearl_4pc.sfz", "CC BY-SA 3.0",
               "AVL Drumkits by Glen MacArthur (CC BY-SA 3.0)", "https://www.bandshed.net/avldrumkits/"),
    Instrument("clarinet", "VSCO 2 Community Edition clarinet", "sgossner/VSCO-2-CE",
               "440300901dfe9275fd84e0b7763af1f8443ae62e", "clarinet.sfz", "CC0", "",
               "https://versilian-studios.com/vsco-community/", generated=True),
)}

# What a person downloads, in packs, so nobody fetches an orchestra they won't use.
PACKS = {
    "band": {"label": "The band", "why": "plays the score preview and the parts: a grand piano, two basses, "
                                          "a drum kit, and a clarinet for the melody",
             "instruments": ["piano", "electric-bass", "upright-bass", "drums", "clarinet"]},
}

# Which instrument plays each part of the arrangement (roles from perform.roles).
ROLE_INSTRUMENT = {"melody": "clarinet", "piano_rh": "piano", "piano_lh": "piano", "piano": "piano",
                   "drums": "drums", "other": "piano"}
UPRIGHT_STYLES = {"waltz", "ballad"}


def bass_for(style: str | None) -> str:
    """The upright bass for waltzes and ballads, the electric bass for everything else."""
    return "upright-bass" if style in UPRIGHT_STYLES else "electric-bass"


def instrument_for(role: str, style: str | None = None) -> str:
    return bass_for(style) if role == "bass" else ROLE_INSTRUMENT.get(role, "piano")


@lru_cache(maxsize=1)
def manifest() -> dict:
    """{instrument id: [(path, size, git blob id), ...]}"""
    data = json.loads((SOUND / "manifest.json").read_text(encoding="utf-8"))
    return {k: [tuple(f) for f in v["files"]] for k, v in data["instruments"].items()}


def size_of(instrument_id: str) -> int:
    return sum(f[1] for f in manifest()[instrument_id])


# ------------------------------------------------------------------ where they are

def install_dir() -> Path:
    return paths.data_home() / "instruments"


def folder_of(instrument_id: str) -> Path | None:
    """The instrument's folder if it's completely downloaded: the data folder, then the developer copy."""
    env = os.environ.get("COPYIST_INSTRUMENTS")
    roots = ([Path(env).expanduser()] if env else []) + [install_dir(), Path(".cache/instruments")]
    inst = CATALOG[instrument_id]
    for root in roots:
        folder = root / instrument_id
        marker = folder / COMPLETE
        if marker.is_file() and marker.read_text(encoding="utf-8").strip() == inst.revision:
            return folder.resolve()
    return None


def sfz_path(instrument_id: str) -> Path | None:
    """The SFZ to give sfizz, or None if the instrument isn't downloaded."""
    folder = folder_of(instrument_id)
    if folder is None:
        return None
    inst = CATALOG[instrument_id]
    if inst.generated:
        place_generated(inst, folder)
    return folder / inst.sfz


def place_generated(inst: Instrument, folder: Path) -> None:
    src, dest = SOUND / inst.sfz, folder / inst.sfz
    text = src.read_text(encoding="utf-8")
    if not dest.is_file() or dest.read_text(encoding="utf-8") != text:
        dest.write_text(text, encoding="utf-8")


def status(instrument_id: str) -> dict:
    inst = CATALOG[instrument_id]
    files = manifest()[instrument_id]
    size = sum(f[1] for f in files)
    if folder_of(instrument_id):
        state, have = "ready", size
    else:
        folder = install_dir() / instrument_id
        have = sum(f[1] for f in files if (folder / f[0]).is_file()) if folder.is_dir() else 0
        state = "partial" if have else "missing"
    return {"id": inst.id, "label": inst.label, "file": inst.sfz, "repo": inst.repo, "revision": inst.revision,
            "size": size, "licence": inst.licence, "credit": inst.credit, "home": inst.home,
            "state": state, "have": have}


def pack_status(pack: str) -> dict:
    p = PACKS[pack]
    items = [status(i) for i in p["instruments"]]
    return {"id": f"instruments-{pack}", "kind": "instruments", "label": p["label"], "why": p["why"],
            "size": sum(i["size"] for i in items), "have": sum(i["have"] for i in items),
            "ready": all(i["state"] == "ready" for i in items), "models": items}


def credits(instrument_ids) -> list[str]:
    """The credit lines owed for these instruments, in catalog order."""
    wanted = set(instrument_ids)
    return [i.credit for i in CATALOG.values() if i.id in wanted and i.credit]


# ------------------------------------------------------------------ downloading

def url(inst: Instrument, path: str) -> str:
    return f"https://raw.githubusercontent.com/{inst.repo}/{inst.revision}/{quote(path)}"


def git_blob_id(data: bytes) -> str:
    """The id git gives a file's contents: SHA-1 of "blob <size>\\0" and the bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


Progress = Callable[[int, int], None]


def fetch(inst: Instrument, path: str, size: int, blob: str, folder: Path, opener=urlopen,
          recheck: bool = False) -> int:
    """Download one file and move it into place if it matches; returns the bytes downloaded.

    A file already in place was checked when it arrived, so it's kept as is,
    unless `recheck` (the catalog moved to a new revision since).
    """
    final = folder / path
    if final.is_file() and final.stat().st_size == size:
        if not recheck or git_blob_id(final.read_bytes()) == blob:
            return 0
    req = Request(url(inst, path), headers={"User-Agent": "copyist"})
    last = None
    for _attempt in range(3):
        try:
            with opener(req, timeout=60) as r:
                data = r.read()
            break
        except OSError as e:          # a dropped connection: try again
            last = e
    else:
        raise OSError(f"Couldn't download {path} from {inst.repo}: {last}")
    if len(data) != size or git_blob_id(data) != blob:
        raise ValueError(f"{inst.repo}: {path} didn't match the pinned version; nothing was kept. "
                         "Try the download again.")
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(final.name + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, final)
    return size


def download(instrument_id: str, progress: Progress | None = None, opener=urlopen, workers: int = 6) -> Path:
    """Download one instrument into the data folder (only the files it plays), checking every file."""
    inst = CATALOG[instrument_id]
    have = folder_of(instrument_id)
    if have:
        return have
    folder = install_dir() / instrument_id
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / COMPLETE
    recheck = marker.is_file()            # complete, but for an older revision
    if recheck:
        marker.unlink()
    files = manifest()[instrument_id]
    total = sum(f[1] for f in files)
    done = sum(f[1] for f in files if (folder / f[0]).is_file() and (folder / f[0]).stat().st_size == f[1])
    lock = threading.Lock()
    if progress:
        progress(done, total)

    def one(f):
        nonlocal done
        got = fetch(inst, f[0], f[1], f[2], folder, opener, recheck)
        if got:
            with lock:
                done += got
                if progress:
                    progress(done, total)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for fut in [pool.submit(one, f) for f in files]:
            fut.result()
    if inst.generated:
        place_generated(inst, folder)
    (folder / COMPLETE).write_text(inst.revision + "\n", encoding="utf-8")
    return folder


def download_pack(pack: str, progress: Progress | None = None, opener=urlopen) -> list[Path]:
    """Download every instrument in a pack, reporting progress across all of them."""
    ids = PACKS[pack]["instruments"]
    total = sum(size_of(i) for i in ids)
    base = 0
    out = []
    for i in ids:
        b = base
        out.append(download(i, (lambda d, _t, b=b: progress(b + d, total)) if progress else None, opener))
        base += size_of(i)
    return out
