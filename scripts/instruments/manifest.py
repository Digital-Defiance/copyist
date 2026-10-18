"""Write copyist/sound/manifest.json: the files each instrument plays, with their git object ids.

Run it with a local clone of each library at its pinned revision (a
`git clone --filter=blob:none` is enough; files are checked out as needed):

    python scripts/instruments/manifest.py /path/to/clones

where /path/to/clones/<repo name> is each clone (SalamanderGrandPiano,
karoryfer.growlybass, ...). Every file is hashed and compared with the object
id git has for it at the pinned commit, so the manifest can't drift from the
libraries.
"""
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from copyist.instruments import CATALOG, SAMPLE_LINKS, SOUND, git_blob_id  # noqa: E402

# Beyond what each SFZ plays: the licence and readme travel with the samples.
EXTRA = {
    "piano": ["LICENSE", "README.md", "Data/", "Samples/"],   # its SFZ builds sample names from #defines
    "electric-bass": ["LICENSE", "readme.txt"],
    "upright-bass": ["LICENSE", "readme.txt"],
    "drums": ["LICENSE", "README.md", "AVL-Drumkits CC-BY-SA License.pdf"],
    "clarinet": ["LICENSE", "README.md", "Woodwinds/Clarinet/susLong/"],
    "organ": ["LICENSE", "README.md",
              "Aerophones/Edge-blown Aerophones/Pipe Organ/Quiet/",
              "Aerophones/Edge-blown Aerophones/Pipe Organ/Loud/"],
    "harp": ["LICENSE", "README.md", "Strings/Harp/"],
    "musicbox": ["LICENSE", "README.md", "Idiophones/Struck Idiophones/Glockenspiel/"],
    "nylon-guitar": ["LICENSE", "README.md", "samples/"],
    "steel-guitar": ["Discord GM/Melodic/026-Acoustic Guitar (steel)/"],
    "electric-guitar": ["LICENSE", "readme.txt"],
    "fiddle": ["LICENSE", "README.md", "Strings/Solo Violin/Arco Vib/"],
    "flute": ["LICENSE", "README.md", "Woodwinds/Flute/susvib/"],
    "sax": ["LICENSE", "readme.txt"],   # samples come from the SFZ (rr1 dynamic only, ~48 MB)
}


def tree(clone: Path, rev: str) -> dict[str, str]:
    out = subprocess.run(["git", "-C", str(clone), "ls-tree", "-r", "-z", rev], check=True,
                         capture_output=True).stdout.decode()
    files = {}
    for entry in filter(None, out.split("\0")):
        meta, path = entry.split("\t", 1)
        mode, kind, oid = meta.split()
        if kind == "blob":
            files[path] = oid
    return files


def checkout(clone: Path, rev: str, paths: list[str]) -> None:
    missing = [p for p in paths if not (clone / p).is_file()]
    for i in range(0, len(missing), 200):
        subprocess.run(["git", "-C", str(clone), "checkout", "-q", rev, "--", *missing[i:i + 200]], check=True)


def played(clone: Path, rev: str, sfz: str, known: dict) -> set[str]:
    """The SFZ, the files it #includes, and the samples its regions name (repeated as includes arrive)."""
    found: set[str] = {sfz}
    base = posixpath.dirname(sfz)
    for _ in range(6):
        checkout(clone, rev, [p for p in found if p in known])
        before = len(found)
        default = ""
        for rel in sorted(p for p in found if p.endswith(".sfz")):
            text = re.sub(r"//[^\n]*", "", (clone / rel).read_text(errors="replace"))
            for inc in re.findall(r'#include\s+"([^"]+)"', text):
                found.add(posixpath.normpath(posixpath.join(base, inc)))
            for m in re.finditer(r"(default_path|sample)=(.+?)(?=\s+\w+=|\s*<|\s*$)", text, re.M):
                key, val = m.group(1), m.group(2).strip().replace("\\", "/")
                if key == "default_path":
                    default = val
                elif "$" not in val:
                    found.add(posixpath.normpath(posixpath.join(base, default + val)))
        if len(found) == before:
            break
    return found


def main(clones: Path) -> None:
    result = {"format": 1, "instruments": {}}
    for inst in CATALOG.values():
        if inst.synthetic:
            result["instruments"][inst.id] = {"repo": inst.repo, "revision": inst.revision, "files": []}
            print(f"{inst.id}: synthetic (no sample files)", file=sys.stderr)
            continue
        clone = clones / inst.repo.split("/")[1]
        known = tree(clone, inst.revision)
        wanted = set() if inst.generated else played(clone, inst.revision, inst.sfz, known)
        # SAMPLE_LINKS instruments point the SFZ at a local samples/ symlink; the real
        # files are listed under EXTRA (the nested folder in the clone).
        if inst.generated and inst.id not in SAMPLE_LINKS:
            text = (SOUND / inst.sfz).read_text()
            default = re.search(r"default_path=(.+)", text)
            prefix = (default.group(1).strip() if default else "")
            if prefix and not prefix.endswith("/"):
                prefix += "/"
            names = [line.split("sample=", 1)[1].strip()
                     for line in text.splitlines() if "sample=" in line
                     and not line.split("sample=", 1)[1].strip().startswith("*")]
            wanted |= {prefix + n for n in names}
        for extra in EXTRA.get(inst.id, []):
            wanted |= {p for p in known if p == extra or (extra.endswith("/") and p.startswith(extra))}
        absent = sorted(p for p in wanted if p not in known)
        if absent:
            raise SystemExit(f"{inst.id}: not in {inst.repo}@{inst.revision[:8]}: {absent[:5]}")
        files = sorted(wanted)
        checkout(clone, inst.revision, files)
        rows = []
        for p in files:
            data = (clone / p).read_bytes()
            if git_blob_id(data) != known[p]:
                raise SystemExit(f"{inst.id}: {p} on disk isn't the committed file")
            rows.append([p, len(data), known[p]])
        result["instruments"][inst.id] = {"repo": inst.repo, "revision": inst.revision, "files": rows}
        print(f"{inst.id}: {len(rows)} files, {sum(r[1] for r in rows) / 1e6:.0f} MB", file=sys.stderr)
    text = json.dumps(result, indent=0, separators=(",", ":"))
    (SOUND / "manifest.json").write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
