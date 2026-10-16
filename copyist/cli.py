"""The `copyist` command.

    copyist build songs/amazing-grace.yaml   # every output into out/amazing-grace/
    copyist check songs/amazing-grace.yaml   # validators only; exit code 1 if anything fails
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import arrange, engrave, render
from .song import SongError, load_song
from .validate import is_finished, report_markdown, validate

ROOT = Path.cwd()


def cmd_check(args) -> int:
    song = load_song(args.song)
    findings = validate(song)
    print(report_markdown(song, findings))
    return 0 if is_finished(findings) else 1


def cmd_build(args) -> int:
    song = load_song(args.song)
    out = Path(args.out) / song.slug
    out.mkdir(parents=True, exist_ok=True)
    findings = validate(song)
    finished = is_finished(findings)

    made: list[Path] = []
    lead = engrave.engrave(song.score, out, "lead-sheet", song.title, song.credits, subtitle="Lead sheet")
    made += [lead["pdf"], lead["musicxml"]]
    made.append(engrave.write_midi(arrange.performance(song.score), out / "lead-sheet.mid"))

    band = arrange.arrange_band(song)
    full = engrave.engrave(band.score, out, "score", song.title, song.credits, subtitle="Full score",
                           options={"scale": 38})
    made += [full["pdf"], full["musicxml"]]
    for name, part in band.parts.items():
        p = engrave.engrave(part, out / "parts", name, song.title, song.credits, subtitle=name.title())
        made.append(p["pdf"])
    midi = engrave.write_midi(band.performance(), out / f"{song.slug}.mid")
    made.append(midi)

    audio_note = None
    if not args.no_audio:
        try:
            sf = render.soundfont_path(Path(args.cache))
            wav = render.render_midi(midi, out / f"{song.slug}.wav", sf)
            made.append(wav)
        except render.AudioUnavailable as e:
            audio_note = str(e)

    if args.images:
        for pdf in [p for p in made if p.suffix == ".pdf"]:
            engrave.pdf_page_images(pdf)

    report = report_markdown(song, findings)
    extra = ["", "## Arrangement", "", f"Template `band`, style `{band.style}`.", "",
             "| Direction | Result |", "|---|---|",
             f"| Instruments included: {', '.join(band.included) or 'none'} | each has a part ✓ |"]
    for name in band.excluded:
        extra.append(f"| Excluded: {name} | no {name} part, so nothing plays it ✓ |")
    extra += [f"- {n}" for n in band.notes]
    if audio_note:
        extra += ["", "## Audio", "", f"Skipped: {audio_note}"]
    extra += ["", "## Files", ""] + [f"- `{p.relative_to(out)}`" for p in made]
    (out / "report.md").write_text(report + "\n".join(extra) + "\n", encoding="utf-8")

    status = "finished" if finished else "NOT finished (see report.md)"
    print(f"{song.title}: {status}. Wrote {len(made) + 1} files to {out}/")
    if audio_note:
        print(f"Audio skipped: {audio_note}")
    return 0 if finished else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="copyist", description="The song, the score, the sound.")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build every output for a song")
    b.add_argument("song", help="path to a song file (.yaml)")
    b.add_argument("--out", default="out", help="output folder (default: out)")
    b.add_argument("--cache", default=".cache", help="where downloaded assets live (default: .cache)")
    b.add_argument("--no-audio", action="store_true", help="skip rendering the WAV")
    b.add_argument("--images", action="store_true", help="also write a PNG of every PDF page, for checking")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("check", help="run the validators and print the report")
    c.add_argument("song", help="path to a song file (.yaml)")
    c.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SongError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
