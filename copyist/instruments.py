"""The sampled instruments Copyist plays a score with, and their downloader (docs/sound-set.md).

Each instrument is an SFZ library in a public git repository, pinned to one
commit. Only the files the instrument actually plays are downloaded, and each is
checked against its git object id at that commit (copyist/sound/manifest.json),
so what lands on disk is byte for byte what the library's authors published.
A file is only moved into place once it checks out, so an interrupted download
picks up where it stopped.

The clarinet, flute, sax, pipe organ, harp, music box, steel guitar and fiddle
are exceptions to "as published": VSCO/VCSL/Discord/Karoryfer ship WAV-only or
awkward paths, so Copyist writes their SFZs (copyist/sound/*.sfz) next to the
samples. The tonewheel organ is fully synthetic (sfizz *sine oscillators).
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


def git_blob_id(data: bytes) -> str:
    """The id git gives a file's contents: SHA-1 of "blob <size>\\0" and the bytes."""
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


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
    synthetic: bool = False   # no sample download; SFZ uses sfizz oscillators (*sine, …)


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
    Instrument("organ", "VCSL pipe organ (manuals, Quiet and Loud)", "sgossner/VCSL",
               "c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e", "organ.sfz", "CC0", "",
               "https://github.com/sgossner/VCSL", generated=True),
    Instrument("harp", "VSCO 2 Community Edition concert harp", "sgossner/VSCO-2-CE",
               "440300901dfe9275fd84e0b7763af1f8443ae62e", "harp.sfz", "CC0", "",
               "https://versilian-studios.com/vsco-community/", generated=True),
    Instrument("tonewheel", "Tonewheel organ (sfizz sine drawbars)", "copyist/synthetic",
               git_blob_id((SOUND / "tonewheel.sfz").read_bytes()), "tonewheel.sfz", "MIT", "",
               "https://sfz.tools/sfizz/", generated=True, synthetic=True),
    Instrument("musicbox", "VCSL glockenspiel (music-box stand-in)", "sgossner/VCSL",
               "c1ea7bcc3c7309650ab0da9d15c9cd1fbc4a4c7e", "musicbox.sfz", "CC0", "",
               "https://github.com/sgossner/VCSL", generated=True),
    Instrument("nylon-guitar", "FreePats Spanish classical guitar (nylon)", "freepats/spanish-classical-guitar",
               "6f4eb1b092acc88f5448cea1a0001bd07b971af8", "SpanishClassicalGuitar-20190618.sfz", "CC0", "",
               "https://freepats.zenvoid.org/Guitar/acoustic-guitar.html"),
    Instrument("steel-guitar", "Discord GM Martin HD28 steel-string guitar", "sfzinstruments/Discord-SFZ-GM-Bank",
               "7a9c478fe331f94f246d33332f0adedb25bbbe27", "steel-guitar.sfz", "CC0", "",
               "https://github.com/sfzinstruments/Discord-SFZ-GM-Bank", generated=True),
    Instrument("electric-guitar", "Karoryfer Emilyguitar (Epiphone, clean)", "sfzinstruments/karoryfer.emilyguitar",
               "b4920dc662fd9cad6dcaccdeecffdd91c8725d8c", "emily_clean.sfz", "CC0", "",
               "https://github.com/sfzinstruments/karoryfer.emilyguitar"),
    Instrument("fiddle", "VSCO 2 Community Edition solo violin (fiddle)", "sgossner/VSCO-2-CE",
               "440300901dfe9275fd84e0b7763af1f8443ae62e", "fiddle.sfz", "CC0", "",
               "https://versilian-studios.com/vsco-community/", generated=True),
    Instrument("flute", "VSCO 2 Community Edition flute (sustained vibrato)", "sgossner/VSCO-2-CE",
               "440300901dfe9275fd84e0b7763af1f8443ae62e", "flute.sfz", "CC0", "",
               "https://versilian-studios.com/vsco-community/", generated=True),
    Instrument("sax", "Karoryfer Weresax alto saxophone", "sfzinstruments/karoryfer.weresax",
               "a4d756b21d2a573aca0d840cce7e71ba5effd4c6", "sax.sfz", "CC0", "",
               "https://github.com/sfzinstruments/karoryfer.weresax", generated=True),
)}

# What a person downloads, in packs, so nobody fetches an orchestra they won't use.
PACKS = {
    "band": {"label": "The band", "why": "plays the score preview and the parts: a grand piano, two basses, "
                                          "a drum kit, and a clarinet for the melody",
             "instruments": ["piano", "electric-bass", "upright-bass", "drums", "clarinet"]},
    "keys": {"label": "Keys", "why": "pipe organ, concert harp, and a synthetic tonewheel for gospel",
             "instruments": ["organ", "harp", "tonewheel"]},
    "bells": {"label": "Music box and bells", "why": "a tinkling music-box stand-in (VCSL glockenspiel) for lullabies "
                                                      "and the musical",
              "instruments": ["musicbox"]},
    "folk": {"label": "Folk and country", "why": "nylon and steel guitars, and a fiddle (solo violin) for country "
                                                  "and Celtic melodies",
             "instruments": ["nylon-guitar", "steel-guitar", "fiddle"]},
    "electric": {"label": "Electric guitar", "why": "clean electric for pop, rock, blues and power-ballad chord "
                                                     "patterns",
                 "instruments": ["electric-guitar"]},
    "winds": {"label": "Winds", "why": "flute for Broadway and march; alto sax for swing, jazz waltz, blues "
                                        "and bossa nova (clarinet stays in the band pack)",
              "instruments": ["flute", "sax"]},
}

# Generated SFZs that need a space-free samples/ link into a nested folder in the clone.
SAMPLE_LINKS = {
    "steel-guitar": "Discord GM/Melodic/026-Acoustic Guitar (steel)",
}

# Which instrument plays each part of the arrangement (roles from perform.roles), unless the
# style chooses (the `instruments:` of a style file, copyist/styles/).
ROLE_INSTRUMENT = {"melody": "clarinet", "piano_rh": "piano", "piano_lh": "piano", "piano": "piano",
                   "bass": "electric-bass", "drums": "drums", "other": "piano"}

# Semitones to shift a part when rendering (score stays as written). The music-box stand-in's
# samples sit high; sung melodies in C4–C5 sound dull when stretched down from G4.
PLAY_SHIFT = {"musicbox": 12}


def instrument_for(role: str, style: str | None = None) -> str:
    from . import styles
    chosen = styles.get(style)
    part = "piano" if role.startswith("piano") else role
    if chosen and part in chosen.instruments:
        return chosen.instruments[part]
    return ROLE_INSTRUMENT.get(role, "piano")


def play_shift(instrument_id: str) -> int:
    """How many semitones to raise this instrument when playing a part (0 = as written)."""
    return PLAY_SHIFT.get(instrument_id, 0)


@lru_cache(maxsize=1)
def manifest() -> dict:
    """{instrument id: [(path, size, git blob id), ...]}"""
    data = json.loads((SOUND / "manifest.json").read_text(encoding="utf-8"))
    return {k: [tuple(f) for f in v["files"]] for k, v in data["instruments"].items()}


def size_of(instrument_id: str) -> int:
    if CATALOG[instrument_id].synthetic:
        return 0
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
    target = SAMPLE_LINKS.get(inst.id)
    if target:
        link, real = folder / "samples", folder / target
        if real.is_dir() and (not link.exists() or (link.is_symlink() and link.resolve() != real.resolve())):
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(real)


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
    if inst.synthetic:
        place_generated(inst, folder)
        (folder / COMPLETE).write_text(inst.revision + "\n", encoding="utf-8")
        if progress:
            progress(1, 1)
        return folder
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
