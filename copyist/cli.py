"""The `copyist` command.

    copyist build songs/amazing-grace.yaml   # every output into out/amazing-grace/
    copyist check songs/amazing-grace.yaml   # validators only; exit code 1 if anything fails
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from music21 import stream

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


def cmd_sing(args) -> int:
    """Sing one verse with SoulX-Singer, check its pitch, and mix it with the band."""
    from . import hear, pitch, sing
    song = load_song(args.song)
    bars = sing.bar_range(args.bars)
    notes = sing.sung_notes(song, args.verse, bars, song.pronunciations)
    lead = 0.5
    segments = sing.soulx_segments(notes, lead=lead)
    sx = sing.SoulX.find(args.soulx, args.soulx_python)
    if args.voice:
        voice_wav, voice_meta = Path(args.voice), Path(args.voice_meta or Path(args.voice).with_suffix(".json"))
    else:
        voice_wav, voice_meta = sx.example_voice()
        print("Using SoulX-Singer's example English voice (for testing only).", file=sys.stderr)
    tag = f"verse{args.verse}" + (f"-bars{bars[0]}-{bars[1]}" if bars else "")
    out = Path(args.out) / song.slug / "sung" / tag
    vocal = sx.sing(segments, voice_wav, voice_meta, out, args.device)

    results = pitch.check(vocal, notes, offset=lead)
    length = notes[-1].start + notes[-1].dur if notes else 0.0
    lines = [f"# {song.title}: sung verse {args.verse}" + (f", bars {bars[0]}–{bars[1]}" if bars else ""), "",
             f"Voice: `{voice_wav.name}`. Engine: SoulX-Singer, score control.", ""]
    lines += pitch.report_lines(results)
    expected = [n.word for n in notes if n.kind == sing.ONSET]
    lines += [""] + hear.report_lines(expected, vocal)

    if not args.no_mix:
        band = arrange.arrange_band(song)
        perf = band.performance()
        for part in list(perf.parts):
            if part.partName == "Voice":
                perf.remove(part)
        midi = engrave.write_midi(perf, out / "band.mid")
        try:
            sf2 = render.soundfont_path(Path(args.cache))
            band_wav = render.render_midi(midi, out / "band.wav", sf2)
            band_start = 0.0
            if bars:
                spq = sing.seconds_per_quarter(song)
                first = next(m for m in song.melody.getElementsByClass(stream.Measure) if m.number >= bars[0])
                band_start = float(first.getOffsetInHierarchy(song.melody)) * spq
            render.mix_vocal(band_wav, vocal, out / "mix.wav", band_start, lead, length)
            lines += ["", "Mix: `mix.wav` (sung vocal over the band)."]
        except render.AudioUnavailable as e:
            lines += ["", f"Mix skipped: {e}"]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(pitch.summary(results))
    print(f"Wrote {out}/")
    return 0


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

    g = sub.add_parser("sing", help="sing a verse with SoulX-Singer and check its pitch (see docs/singing.md)")
    g.add_argument("song", help="path to a song file (.yaml)")
    g.add_argument("--verse", type=int, default=1, help="which verse to sing (default 1)")
    g.add_argument("--bars", help="only these bars, e.g. 0-4 (quicker for trying things)")
    g.add_argument("--soulx", help="SoulX-Singer folder (or set COPYIST_SOULX_DIR)")
    g.add_argument("--soulx-python", help="Python with SoulX-Singer installed (or COPYIST_SOULX_PYTHON)")
    g.add_argument("--voice", help="reference recording of the singer's voice (with a matching .json)")
    g.add_argument("--voice-meta", help="metadata for --voice, if not next to it with a .json suffix")
    g.add_argument("--device", default="auto", help="auto, cuda, mps or cpu (default auto)")
    g.add_argument("--out", default="out")
    g.add_argument("--cache", default=".cache")
    g.add_argument("--no-mix", action="store_true", help="don't mix the vocal with the band")
    g.set_defaults(func=cmd_sing)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SongError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
