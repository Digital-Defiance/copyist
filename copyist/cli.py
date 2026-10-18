"""The `copyist` command.

    copyist build songs/amazing-grace.yaml   # every output into out/amazing-grace/
    copyist check songs/amazing-grace.yaml   # validators only; exit code 1 if anything fails
    copyist produce songs/amazing-grace.yaml # a YuE2 recording from the score
    copyist write lyrics.txt --title Hope     # melodies for new lyrics, to choose by ear
    copyist rewrite songs/hope.yaml --section verse --how higher
    copyist transcribe song.mp3 --title Hope  # a lead sheet from a recording
"""
from __future__ import annotations

import argparse
import json
import re
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
    performed = None
    from . import perform, styles
    swing = styles.get(band.style).swing if styles.get(band.style) else 0.5
    if not args.plain:
        style = styles.get(band.style)
        piano_melody = bool(style and style.instruments.get("melody") == "piano")
        performed = perform.perform(midi, midi, song.meter, float(perform.pickup_of(song)), seed=args.seed,
                                    swing=swing, melody_legato=not piano_melody)
    elif swing > 0.5:
        perform.swing_only(midi, midi, song.meter, float(perform.pickup_of(song)), swing)

    audio_note = None
    audio = None
    if not args.no_audio:
        try:
            audio = render.render_band(midi, out / f"{song.slug}.wav", band.style, Path(args.cache),
                                       stems_dir=out / "stems")
            made.append(audio.wav)
            made += [audio.stems[p] for p in render.PART_ORDER if p in audio.stems]
            (out / "audio.json").write_text(json.dumps(audio.summary(), indent=1) + "\n", encoding="utf-8")
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
    if performed:
        extra += ["", "## Performance", "",
                  f"Played, not just written (seed {performed['seed']}): phrases rise and settle, the band builds "
                  f"across the song, downbeats lean, the melody sings over the band, timing varies by up to about "
                  f"{performed['timing_ms']:.0f} ms, "
                  f"the piano pedals {performed['pedal_changes']} times with the harmony, and the last "
                  f"{performed['ritardando_bars']} bars slow down into a ringing final chord. Every note is the "
                  "written one. `--plain` writes the MIDI exactly on the grid instead."]
        if performed.get("swing", 0.5) > 0.5:
            extra.append(f"The eighths swing, as the style asks: an off-beat eighth lands {performed['swing']:.0%} "
                         "of the way through its beat, not halfway.")
    if audio:
        extra += ["", "## Audio", ""] + audio.report_lines()
    if audio_note:
        extra += ["", "## Audio", "", f"Skipped: {audio_note}"]
    extra += ["", "## Files", ""] + [f"- `{p.relative_to(out)}`" for p in made]
    (out / "report.md").write_text(report + "\n".join(extra) + "\n", encoding="utf-8")

    status = "finished" if finished else "NOT finished (see report.md)"
    print(f"{song.title}: {status}. Wrote {len(made) + 1} files to {out}/")
    if audio_note:
        print(f"Audio skipped: {audio_note}")
    elif audio and audio.engine != "sampled":
        print(f"Audio: the SoundFont played, because {audio.note}")
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
            band_wav = render.render_band(midi, out / "band.wav", band.style, Path(args.cache)).wav
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


def cmd_produce(args) -> int:
    """Render a production with YuE2 from the song's own score (see docs/production.md)."""
    from . import yue
    song = load_song(args.song)
    octave = yue.SUNG_OCTAVE_BELOW if args.octave is None else args.octave
    req = yue.request(song, verses=args.verses, style=args.style, seed=args.seed, intro_bars=args.intro_bars,
                      octave=octave)
    req["output_format"] = "wav16"
    if args.take and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.take):
        raise SongError("A take name uses letters, digits, - and _ only.")
    out = Path(args.out) / song.slug / (f"takes/{args.take}" if args.take else "production")
    extra = []
    if args.lora:
        req["adapters"], folder = yue.lora_adapters(args.lora)
        extra = ["--adapters", folder]
    audio = yue.run_yue2cpp(req, out, device=args.device, extra=extra)
    offset = yue.vocal_offset(song, args.intro_bars)
    print(f"Wrote {audio}")
    print(f"Verse 1's first note is {offset:.2f} seconds into the recording.")
    return 0


def cmd_follow(args) -> int:
    """Check that a recording sings the song's melody: each phrase's timing is found, any octave counts."""
    from . import pitch, sing, yue
    song = load_song(args.song)
    recording = Path(args.recording)
    if args.separate:
        from .stems import vocal_stem
        recording = vocal_stem(recording)
    tracked = pitch.track(recording)
    lines = [f"# {song.title}: does the recording follow the score?", "",
             f"Recording: `{recording.name}`. The recording may sit up to {args.search:g} s early or late, each phrase"
             f" {pitch.LOCAL_SEARCH:g} s more"
             + ("." if args.written_octave else "; any octave counts."), ""]
    good = total = 0
    for v in range(1, args.verses + 1):
        notes = sing.sung_notes(song, v, pronunciations=song.pronunciations)
        at = yue.verse_offset(song, v, args.intro_bars)
        results = pitch.check(recording, notes, offset=at, search=args.search,
                              any_octave=not args.written_octave, tracked=tracked)
        good += sum(r.ok for r in results)
        total += len(results)
        body = pitch.report_lines(results)
        lines += [f"## Verse {v}"] + body[1:] + [""]
        print(f"Verse {v}: {pitch.summary(results)}")
    out = recording.with_name(recording.stem + "-follow.md")
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0 if total and good / total >= args.pass_share else 1


def cmd_lora_songs(args) -> int:
    """List a song collection for LoRA training: style caption and YuE2 lyrics per song, paired with its audio."""
    from . import lora
    songs = lora.build_songs([Path(d) for d in args.sheets], Path(args.audio), args.trigger, use=args.style)
    out = Path(args.out)
    lora.write_songs(songs, out)
    print(f"{len(songs)} songs, trigger “{args.trigger}”. Wrote {out}")
    print(f"Audio comes from {Path(args.audio).resolve()} (give the same folder to scripts/yue-lora/prepare.py).")
    return 0


def cmd_serve(args) -> int:
    """Open Copyist in a browser (docs/web.md)."""
    from .web.server import serve
    serve(Path(args.root), port=args.port, open_browser=not (args.no_open or args.machine),
          machine=args.machine, demo=args.demo)
    return 0


def cmd_models(args) -> int:
    """List the downloadable models and instruments, or download a group of them."""
    from . import instruments, models
    if args.what == "download":
        last = [-1]

        def progress(done, total):
            pct = int(100 * done / total)
            if pct != last[0]:
                last[0] = pct
                print(f"\r{pct}% of {total / 1e9:.1f} GB", end="", file=sys.stderr, flush=True)
        if args.group in instruments.PACKS:
            for p in instruments.download_pack(args.group, progress):
                print(f"\nReady: {p}")
            return 0
        if args.group not in models.GROUPS:
            names = ", ".join([*models.GROUPS, *instruments.PACKS])
            print(f"No download called {args.group!r}. These exist: {names}.", file=sys.stderr)
            return 2
        if not args.accept_licence:
            print(models.LICENCE, "\n\nRun again with --accept-licence to download.", file=sys.stderr)
            return 2
        for p in models.download_group(args.group, progress):
            print(f"\nReady: {p}")
        return 0
    print(f"Models folder: {models.paths.models_dir()}")
    for g in models.GROUPS:
        s = models.group_status(g)
        print(f"{g}: {s['label']} ({s['why']}), {s['size'] / 1e9:.1f} GB: "
              f"{'ready' if s['ready'] else 'not downloaded'}")
        for m in s["models"]:
            print(f"  {m['file']}: {m['state']}" + (f" ({m['path']})" if m["path"] else ""))
    print(f"\nInstruments folder: {instruments.install_dir()}")
    for pack in instruments.PACKS:
        s = instruments.pack_status(pack)
        print(f"{pack}: {s['label']} ({s['why']}), {s['size'] / 1e9:.1f} GB: "
              f"{'ready' if s['ready'] else 'not downloaded'}")
        for i in s["models"]:
            print(f"  {i['label']} ({i['licence']}): {i['state']}")
    return 0


def cmd_gallery(args) -> int:
    """The song in every style that fits its meter, as audio, to choose a style by ear."""
    from . import gallery
    song = load_song(args.song)
    only = [s.strip() for s in args.styles.split(",")] if args.styles else None

    def progress(done, total, name):
        if name:
            print(f"[{done + 1}/{total}] {name}", flush=True)
    if args.takes:
        made = gallery.build_takes(Path(args.song), Path(args.out), seed=args.take_seed, verses=args.verses,
                                   only=only, lora=args.lora, prefix=args.prefix or "", device=args.device,
                                   progress=progress)
        folder = Path(args.out) / song.slug / "gallery"
        for m in made:
            print(f"  {m['style']}: {folder / m['take']}")
        return 0
    entries = gallery.build(song, Path(args.out), Path(args.cache), seed=args.seed, only=only, progress=progress)
    folder = Path(args.out) / song.slug / "gallery"
    for e in entries:
        print(f"  {e['name']}: {folder / e['file']} ({e['tempo']} BPM, {e['engine']})")
    if not entries:
        print(f"No style plays {song.meter} yet.")
    return 0


def cmd_write(args) -> int:
    """Melodies for new lyrics: several candidate songs to choose between by ear (docs/melody-writing.md)."""
    from . import write
    if not (args.lyrics or args.title):
        print("Give the lyrics file (or, with --keep, the song's --title).", file=sys.stderr)
        return 2
    title = args.title or Path(args.lyrics).stem.replace("-", " ").replace("_", " ").title()
    try:
        if args.keep is not None:
            target = write.keep(Path(args.out), title, args.keep, Path(args.songs), args.replace)
            if not args.build:
                print(f"Kept candidate {args.keep} as {target}. Build it with: copyist build {target}")
                return 0
            print(f"Kept candidate {args.keep} as {target}. Writing its score...", flush=True)
            return cmd_build(argparse.Namespace(song=str(target), out=args.out, cache=args.cache, no_audio=False,
                                                plain=False, seed=1, images=False))
        lyrics = Path(args.lyrics).read_text(encoding="utf-8")
        credits = {k: v for k, v in (("words", args.words_by), ("music", args.music_by)) if v}

        def progress(done, total, name):
            if name:
                print(f"[{done + 1}/{total}] {name}", flush=True)
        index = write.write_songs(lyrics, title, Path(args.out), args.style, args.words, args.voice, args.candidates,
                                  args.seed, args.takes, args.device, Path(args.cache), credits or None,
                                  previews=not args.no_preview, engine=args.engine, progress=progress)
    except write.WriteError as e:
        print(e, file=sys.stderr)
        return 2
    folder = Path(args.out) / index["slug"] / "write"
    print(f"Candidates in {folder} (best first):")
    for e in index["candidates"]:
        if e.get("ok"):
            sc = e["scores"]
            print(f"  {e['rank']}. candidate {e['seed']}: {e['key']}, {e['meter']}, {e['tempo']}; "
                  f"{sc['fails']} failing, {sc['warnings']} warnings, fit {sc['fit_cost']}"
                  + (f"; preview {folder / e['preview']}" if e.get("preview") else ""))
        else:
            print(f"  -  candidate {e['seed']}: not usable ({e.get('reason')})")
    print(f"Keep one with: copyist write --title {json.dumps(title)} --keep N")
    return 0


def cmd_rewrite(args) -> int:
    """Rewrite one section of a song: again, higher, or simpler (docs/melody-writing.md)."""
    from . import rewrite, write
    if args.keep is not None:
        if not args.title and not args.song:
            print("Give --title (or the song) with --keep.", file=sys.stderr)
            return 2
        title = args.title or load_song(args.song).title
        try:
            target = rewrite.keep(Path(args.out), title, args.how, args.keep, Path(args.songs), args.replace)
        except write.WriteError as e:
            print(e, file=sys.stderr)
            return 2
        if not args.build:
            print(f"Kept {args.how} candidate {args.keep} as {target}. Build it with: copyist build {target}")
            return 0
        print(f"Kept {args.how} candidate {args.keep} as {target}. Writing its score...", flush=True)
        return cmd_build(argparse.Namespace(song=str(target), out=args.out, cache=args.cache, no_audio=False,
                                            plain=False, seed=1, images=False))
    if not args.song:
        print("Give the song file to rewrite.", file=sys.stderr)
        return 2

    def progress(done, total, name):
        if name:
            print(f"[{done + 1}/{total}] {name}", flush=True)

    try:
        index = rewrite.rewrite_section(
            Path(args.song), args.section, args.how, Path(args.out),
            Path(args.lyrics) if args.lyrics else None, args.candidates, args.seed,
            args.device, Path(args.cache), previews=not args.no_preview,
            plan_more=not args.no_plan, progress=progress)
    except write.WriteError as e:
        print(e, file=sys.stderr)
        return 2
    folder = Path(args.out) / index["slug"] / "rewrite" / args.how
    print(f"Candidates in {folder} (best first):")
    for e in index["candidates"]:
        if e.get("ok"):
            sc = e["scores"]
            extra = f", +{e['semitones']}" if e.get("semitones") else (f", from {e['donor']}" if e.get("donor") else "")
            print(f"  {e['rank']}. candidate {e['seed']}{extra}: {e['key']}, {e['meter']}; "
                  f"{sc['fails']} failing, fit {sc['fit_cost']}"
                  + (f"; preview {folder / e['preview']}" if e.get("preview") else ""))
        else:
            print(f"  -  candidate {e['seed']}: not usable ({e.get('reason')})")
    print(f"Keep one with: copyist rewrite --title {json.dumps(index['title'])} --how {args.how} --keep N")
    return 0


def cmd_transcribe(args) -> int:
    """A lead sheet from a recording (docs/transcribing.md)."""
    from . import transcribe as tr
    if not (args.recording or args.title):
        print("Give the recording (or, with --keep, the song's --title).", file=sys.stderr)
        return 2
    title = args.title or Path(args.recording).stem.replace("-", " ").replace("_", " ").title()
    try:
        if args.keep:
            target = tr.keep(Path(args.out), title, Path(args.songs), args.replace)
            if not args.build:
                print(f"Kept the transcription as {target}. Build it with: copyist build {target}")
                return 0
            print(f"Kept the transcription as {target}. Writing its score...", flush=True)
            return cmd_build(argparse.Namespace(song=str(target), out=args.out, cache=args.cache, no_audio=False,
                                                plain=False, seed=1, images=False))
        if not args.recording:
            print("Give the recording to transcribe.", file=sys.stderr)
            return 2
        lyrics = Path(args.lyrics).read_text(encoding="utf-8") if args.lyrics else None
        if args.engine == "sheetsage":
            print(tr.SHEETSAGE_LICENCE, file=sys.stderr)
        index = tr.transcribe(Path(args.recording), title, Path(args.out), lyrics, args.engine, args.voice,
                              Path(args.vocals) if args.vocals else None,
                              Path(args.accompaniment) if args.accompaniment else None,
                              args.device, Path(args.cache), preview=not args.no_preview)
    except (ValueError, SongError) as e:
        print(e, file=sys.stderr)
        return 2
    folder = Path(args.out) / index["slug"] / "transcribe"
    print(f"{index['title']}: {index['key']}, {index['meter']}, {index['tempo']}; "
          f"{index['fails']} failing checks, {index['warnings']} warnings, {len(index['doubts'])} doubts.")
    for n in index["notes"]:
        print(f"  {n}")
    print(f"Song file: {folder / index['song']}")
    if index.get("preview"):
        print(f"Hear it on the band: {folder / index['preview']} (and the original: {folder / index['source']})")
    print(f"Keep it with: copyist transcribe --title {json.dumps(title)} --keep")
    return 0


def cmd_use_style(args) -> int:
    """Set a song's style (and tempo), then write the score again."""
    from . import styles
    from .song import set_style
    song = load_song(args.song)
    style = styles.get(args.style)
    if not style:
        print(f"There's no style called {args.style!r}; `copyist styles` lists them.", file=sys.stderr)
        return 2
    if song.meter not in style.meters:
        print(f"{style.name} has no pattern for {song.meter}; it plays {', '.join(style.meters)}.", file=sys.stderr)
        return 2
    set_style(Path(args.song), style.id, args.tempo)
    print(f"{song.title} is now in the {style.name} style" + (f" at {args.tempo:g} BPM." if args.tempo else "."))
    if args.no_build:
        return 0
    return cmd_build(argparse.Namespace(song=args.song, out=args.out, cache=args.cache, no_audio=False,
                                        plain=False, seed=1, images=False))


def styles_list(args) -> int:
    from . import styles
    for s in sorted(styles.catalog().values(), key=lambda s: (styles.FAMILIES.index(s.family), s.name)):
        print(f"{s.id:18} {s.name} ({s.family}; {', '.join(s.meters)}; {s.feel})")
    return 0


def cmd_voice(args) -> int:
    """Make a SoulX-Singer voice from a recording of one person singing."""
    from . import voiceprompt
    hint = Path(args.lyrics).read_text(encoding="utf-8")[:800] if args.lyrics else None
    wav, js, info = voiceprompt.make_voice(Path(args.recording), Path(args.out), args.name,
                                          args.start, args.end, hint)
    print(f"Voice “{args.name}”: {info['end'] - info['start']:.1f} s from {info['start']} s, "
          f"median pitch {info['median_hz']} Hz.")
    print(f"Words heard: {info['words']}")
    print(f"Wrote {wav} and {js}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from . import __version__
    parser = argparse.ArgumentParser(prog="copyist", description="The song, the score, the sound.")
    parser.add_argument("--version", action="version", version=f"copyist {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="build every output for a song")
    b.add_argument("song", help="path to a song file (.yaml)")
    b.add_argument("--out", default="out", help="output folder (default: out)")
    b.add_argument("--cache", default=".cache", help="where downloaded assets live (default: .cache)")
    b.add_argument("--no-audio", action="store_true", help="skip rendering the WAV")
    b.add_argument("--images", action="store_true", help="also write a PNG of every PDF page, for checking")
    b.add_argument("--plain", action="store_true", help="MIDI and audio exactly on the grid, without the performance")
    b.add_argument("--seed", type=int, default=1, help="seed for the performance (default 1)")
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

    p = sub.add_parser("produce", help="render a production with YuE2 from the score (see docs/production.md)")
    p.add_argument("song", help="path to a song file (.yaml)")
    p.add_argument("--verses", type=int, default=1, help="how many verses to render (default 1)")
    p.add_argument("--intro-bars", type=int, default=4, help="instrumental bars before verse 1 (default 4)")
    p.add_argument("--seed", type=int, default=831001, help="seed for the render (default 831001)")
    p.add_argument("--style", help="style tags; default comes from the song")
    p.add_argument("--device", help="yue-synth device, e.g. MTL0 (or set COPYIST_YUE_DEVICE)")
    p.add_argument("--take", help="keep this render in out/<song>/takes/TAKE/ instead of production/")
    p.add_argument("--lora", action="append", metavar="FILE[:SCALE]",
                   help="a YuE2 LoRA (.safetensors) to render with, e.g. a voice trained with scripts/yue-lora; "
                        "repeat for more. Put its trigger word in --style")
    p.add_argument("--octave", type=int, help="octaves to write the melody above where it should sound "
                   "(default 1: YuE2 sings an octave below what it's given)")
    p.add_argument("--out", default="out")
    p.set_defaults(func=cmd_produce)

    f = sub.add_parser("follow", help="check that a recording (e.g. a production's vocal) sings the melody")
    f.add_argument("song", help="path to a song file (.yaml)")
    f.add_argument("recording", help="the recording; a separated vocal works best")
    f.add_argument("--verses", type=int, default=1, help="how many verses the recording has (default 1)")
    f.add_argument("--intro-bars", type=int, default=4, help="bars before verse 1, as in `produce` (default 4)")
    f.add_argument("--search", type=float, default=3.0, help="seconds the recording may sit early or late (default 3)")
    f.add_argument("--separate", action="store_true",
                   help="the recording is a full mix: separate its vocal with Demucs first")
    f.add_argument("--written-octave", action="store_true", help="count only notes in the written octave")
    f.add_argument("--pass-share", type=float, default=0.8, help="share of notes that must match (default 0.8)")
    f.set_defaults(func=cmd_follow)

    ls = sub.add_parser("lora-songs", help="list songs for training a YuE2 LoRA (docs/voice-lora.md)")
    ls.add_argument("sheets", nargs="+", help="folders of prompt sheets (one .md per song, numbered)")
    ls.add_argument("--audio", required=True, help="folder of the songs' audio, numbered like the sheets")
    ls.add_argument("--trigger", required=True, help="a made-up word that will call up the LoRA, e.g. lightson")
    ls.add_argument("--style", choices=("demo", "production"), default="demo", help="which style on each sheet (default demo)")
    ls.add_argument("--out", required=True, help="where to write songs.jsonl")
    ls.set_defaults(func=cmd_lora_songs)

    sv = sub.add_parser("serve", help="open Copyist in a browser, on this computer only (docs/web.md)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--root", default=".", help="the project folder (default: here)")
    sv.add_argument("--no-open", action="store_true", help="don't open a browser window")
    sv.add_argument("--machine", action="store_true", help="print one JSON line with the URL first (for the desktop app)")
    sv.add_argument("--demo", action="store_true", help="give an empty library a demo song")
    sv.set_defaults(func=cmd_serve)

    ga = sub.add_parser("gallery", help="play a song in every style that fits its meter (docs/styles.md)")
    ga.add_argument("song", help="path to a song file (.yaml)")
    ga.add_argument("--styles", help="only these styles, comma-separated (see `copyist styles`)")
    ga.add_argument("--out", default="out", help="output folder (default: out)")
    ga.add_argument("--cache", default=".cache")
    ga.add_argument("--seed", type=int, default=1, help="seed for the performance (default 1)")
    ga.add_argument("--takes", action="store_true",
                    help="make a finished YuE2 take in each style (singer and band; needs the singer, a GPU helps)")
    ga.add_argument("--verses", type=int, default=1, help="with --takes: verses to sing (default 1)")
    ga.add_argument("--take-seed", type=int, default=831001, help="with --takes: the seed (default 831001)")
    ga.add_argument("--lora", action="append", metavar="FILE[:SCALE]", help="with --takes: a trained voice")
    ga.add_argument("--prefix", help="with --takes: words before every style line (a voice's trigger line)")
    ga.add_argument("--device", help="with --takes: yue2.cpp device (default COPYIST_YUE_DEVICE)")
    ga.set_defaults(func=cmd_gallery)

    wr = sub.add_parser("write", help="write melodies for new lyrics, to choose by ear (docs/melody-writing.md)")
    wr.add_argument("lyrics", nargs="?", help="a text file of lyrics, sections tagged [Verse], [Chorus], ...")
    wr.add_argument("--title", help="the song's title (default: from the file name)")
    wr.add_argument("--style", help="a style from `copyist styles`; its words steer the planner")
    wr.add_argument("--words", help="more words for the planner's style line (or instead of a style)")
    wr.add_argument("--voice", default="alto", choices=["soprano", "alto", "tenor", "baritone"],
                    help="the singer's range (default alto)")
    wr.add_argument("--candidates", type=int, default=4, help="how many songs to write (default 4)")
    wr.add_argument("--seed", type=int, default=1, help="the first planner seed; candidates use seed, seed+1, ...")
    wr.add_argument("--engine", default="auto", choices=["auto", "plan", "rules"],
                    help="plan (YuE2), rules (Copyist's own, MIT), or auto (plan if yue-plan is installed)")
    wr.add_argument("--takes", action="store_true", help="also make a finished YuE2 take of each candidate")
    wr.add_argument("--no-preview", action="store_true", help="skip the band previews")
    wr.add_argument("--words-by", help="credit for the words")
    wr.add_argument("--music-by", help="credit for the music")
    wr.add_argument("--keep", type=int, metavar="SEED", help="copy candidate SEED's song file into songs/")
    wr.add_argument("--replace", action="store_true", help="with --keep: replace a different song of the same name")
    wr.add_argument("--build", action="store_true", help="with --keep: then write its score, parts and audio")
    wr.add_argument("--songs", default="songs", help="with --keep: the songs folder (default songs)")
    wr.add_argument("--out", default="out", help="output folder (default: out)")
    wr.add_argument("--cache", default=".cache")
    wr.add_argument("--device", help="yue2.cpp device (default COPYIST_YUE_DEVICE)")
    wr.set_defaults(func=cmd_write)

    rw = sub.add_parser("rewrite", help="rewrite one section of a song: again, higher, or simpler")
    rw.add_argument("song", nargs="?", help="a song file to rewrite")
    rw.add_argument("--section", default="verse", help="which section (default verse)")
    rw.add_argument("--how", required=True, choices=["again", "higher", "simpler"],
                    help="again (swap from another candidate), higher (raise the notes), or simpler")
    rw.add_argument("--lyrics", help="plain lyrics (default: out/<slug>/write/lyrics.txt)")
    rw.add_argument("--candidates", type=int, default=4, help="how many rewrites to try (default 4)")
    rw.add_argument("--seed", type=int, default=1, help="first candidate number in the rewrite folder")
    rw.add_argument("--no-preview", action="store_true", help="skip the band previews")
    rw.add_argument("--no-plan", action="store_true",
                    help="with again/simpler: only use donors already in out/<slug>/write/")
    rw.add_argument("--title", help="with --keep: the song's title")
    rw.add_argument("--keep", type=int, metavar="SEED", help="copy rewrite candidate SEED into songs/")
    rw.add_argument("--replace", action="store_true", help="with --keep: replace a different song of the same name")
    rw.add_argument("--build", action="store_true", help="with --keep: then write its score, parts and audio")
    rw.add_argument("--songs", default="songs", help="with --keep: the songs folder (default songs)")
    rw.add_argument("--out", default="out", help="output folder (default: out)")
    rw.add_argument("--cache", default=".cache")
    rw.add_argument("--device", help="yue2.cpp device when planning more donors (default COPYIST_YUE_DEVICE)")
    rw.set_defaults(func=cmd_rewrite)

    tx = sub.add_parser("transcribe", help="a lead sheet from a recording (docs/transcribing.md)")
    tx.add_argument("recording", nargs="?", help="the recording (WAV, MP3, FLAC...), one you have the rights to")
    tx.add_argument("--title", help="the song's title (default: from the file name)")
    tx.add_argument("--lyrics", help="a text file of the lyrics; without it, Whisper listens for the words")
    tx.add_argument("--engine", default="open", choices=["open", "sheetsage"],
                    help="open (default, MIT) or sheetsage (more accurate, non-commercial licence)")
    tx.add_argument("--voice", choices=["soprano", "alto", "tenor", "baritone"],
                    help="the voice preset (default: the one that fits what was sung)")
    tx.add_argument("--vocals", help="the vocal already separated (skips Demucs); needs --accompaniment")
    tx.add_argument("--accompaniment", help="everything but the vocal, already separated")
    tx.add_argument("--no-preview", action="store_true", help="skip the band playing the transcription")
    tx.add_argument("--keep", action="store_true", help="copy the transcription's song file into songs/")
    tx.add_argument("--replace", action="store_true", help="with --keep: replace a different song of the same name")
    tx.add_argument("--build", action="store_true", help="with --keep: then write its score, parts and audio")
    tx.add_argument("--songs", default="songs", help="with --keep: the songs folder (default songs)")
    tx.add_argument("--out", default="out", help="output folder (default: out)")
    tx.add_argument("--cache", default=".cache")
    tx.add_argument("--device", help="Demucs / yue2.cpp device")
    tx.set_defaults(func=cmd_transcribe)

    us = sub.add_parser("use-style", help="set a song's style (and tempo) and write the score again")
    us.add_argument("song", help="path to a song file (.yaml)")
    us.add_argument("style", help="a style id (see `copyist styles`)")
    us.add_argument("--tempo", type=float, help="the new tempo, in beats a minute")
    us.add_argument("--no-build", action="store_true", help="only change the song file")
    us.add_argument("--out", default="out")
    us.add_argument("--cache", default=".cache")
    us.set_defaults(func=cmd_use_style)

    st = sub.add_parser("styles", help="list the styles Copyist can arrange in")
    st.set_defaults(func=styles_list)

    md = sub.add_parser("models", help="list the downloadable models, or download some (docs/desktop-app.md)")
    md.add_argument("what", nargs="?", choices=("list", "download"), default="list")
    md.add_argument("group", nargs="?", default="singer",
                    help="singer (needed for takes), voices, or band (the sampled instruments)")
    md.add_argument("--accept-licence", action="store_true", help="accept the models' licence (it's printed first)")
    md.set_defaults(func=cmd_models)

    v = sub.add_parser("voice", help="make a singer voice for `copyist sing` from a recording")
    v.add_argument("recording", help="a recording of one person singing (a vocal stem works)")
    v.add_argument("--name", required=True, help="what to call the voice")
    v.add_argument("--start", type=float, help="clip start in seconds (default: found automatically)")
    v.add_argument("--end", type=float, help="clip end in seconds")
    v.add_argument("--lyrics", help="a text file with the song's lyrics, to help the transcription")
    v.add_argument("--out", default="voices", help="where voices live (default: voices/, never committed)")
    v.set_defaults(func=cmd_voice)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except SongError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
