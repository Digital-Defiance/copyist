"""How well the lyric fitter places syllables, against songs placed by hand.

Each song's own words, with its syllables (hyphens) but without its holds, are refitted to its
melody with `copyist refit`, and the notes where a syllable starts are compared with the
hand-placed file. So this measures placement only; `--plain` drops the hyphens too (as the page's
lyric editor shows the words), which also tests Copyist's own syllable counts. Run from the repo root:

    python scripts/fit/evaluate.py [-v] [--plain] [songs/NAME.yaml ...]

`-v` shows every miss in context. The default set is the public-domain songs placed by hand.
"""
from __future__ import annotations

import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from copyist import refit  # noqa: E402
from copyist.song import load_song  # noqa: E402

HAND_PLACED = ("amazing-grace", "silent-night", "when-the-saints", "major-general")


def sung_notes(song) -> list:
    """Note onsets (tie continuations left out)."""
    return [n for n in song.melody.recurse().notes
            if n.isNote and not (n.tie is not None and n.tie.type in ("stop", "continue"))]


def starts(song, notes: list) -> list[set[int]]:
    """Per verse, the indices of the notes where a syllable starts."""
    return [{i for i, n in enumerate(notes)
             if any(l.number == v + 1 and (l.text or "").strip() for l in n.lyrics)}
            for v in range(len(song.verses))]


def label(note, verse: int) -> str:
    texts = [l.text for l in note.lyrics if l.number == verse + 1 and (l.text or "").strip()]
    return texts[0] if texts else "_"


def words_of(verses: list[str], plain: bool) -> str:
    """The song's verses as words to refit: holds removed, hyphens kept unless `plain`."""
    if plain:
        return refit.plain_for_edit(verses)
    return "\n\n".join("\n".join(re.sub(r"-\s+", "-", line.replace("_", "").replace("*", "")).strip()
                                  for line in str(v).splitlines() if line.strip())
                        for v in verses)


def evaluate(path: Path, verbose: bool, plain: bool = False) -> tuple[int, int]:
    hand = load_song(path)
    hand_notes = sung_notes(hand)
    tmp = Path(tempfile.mkdtemp(prefix="copyist-fit-eval-")) / path.name
    shutil.copy(path, tmp)
    refit.refit(tmp, words_of(hand.verses, plain))
    fitted = load_song(tmp)
    fit_notes = sung_notes(fitted)
    if len(fit_notes) != len(hand_notes):
        print(f"{path.stem}: the fit split notes ({len(hand_notes)} -> {len(fit_notes)}); not compared")
        return 0, 0
    missed = total = 0
    for v, (want, got) in enumerate(zip(starts(hand, hand_notes), starts(fitted, fit_notes))):
        total += len(want)
        missed += len(want - got)
        if want != got:
            print(f"{path.stem} verse {v + 1}: {len(want - got)} of {len(want)} syllable starts moved")
            if verbose:
                diff = sorted(want ^ got)
                for i in range(max(0, diff[0] - 2), min(len(hand_notes), diff[-1] + 3)):
                    n = hand_notes[i]
                    mark = "*" if i in diff else " "
                    print(f"  {mark} bar {n.measureNumber} beat {float(n.beat):<6.3g} {n.nameWithOctave:4s} "
                          f"hand: {label(n, v):10s} fit: {label(fit_notes[i], v)}")
    return missed, total


def main(argv: list[str]) -> int:
    verbose, plain = "-v" in argv, "--plain" in argv
    paths = [Path(a) for a in argv if not a.startswith("-")] or [ROOT / "songs" / f"{s}.yaml" for s in HAND_PLACED]
    missed = total = 0
    for path in paths:
        m, t = evaluate(path, verbose, plain)
        missed += m
        total += t
    print(f"Missed {missed} of {total} hand-placed syllable starts ({100 * missed / max(total, 1):.1f}%).")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
