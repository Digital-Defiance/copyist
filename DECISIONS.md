# Decisions

Newest first. One entry per decision: what, why, and what we gave up.

## 2026-10-17 (web front end)

- **A local page served by Python's own HTTP server** (`copyist serve`), not a framework or a hosted app. No new dependencies, and the work has to run where the GPU is. Gave up: hosting for other people, for now.
- **The page runs the `copyist` commands as jobs, one at a time.** The command line stays the one way things get made, and the GPU can't do two renders at once.
- **Sheets are shown as page images** rendered from the PDFs with PyMuPDF, because browsers' PDF viewers aren't reliable (Chromium headless shows nothing).
- **Fonts are bundled** (Shantell Sans for what you do, Source Serif 4 for what Copyist wrote; both SIL OFL), so the page fetches nothing from the internet.
- **Guards:** 127.0.0.1 only, files from `out/` only, a Host check against DNS rebinding, and jobs only from the page itself (a custom header plus an Origin check).

## 2026-10-17 (voice LoRA)

- **A voice comes from a YuE2 LoRA, not from SoulX over the SoundFont band.** The SoundFont band and a SoulX vocal stay as checking tools; she found the band "terrible" and the singer "a little glitchy". Gave up: SoulX's note-exact control of the vocal line.
- **The LoRA trainer is Copyist's own code** (scripts/yue-lora), following the published recipe (AR-half LoRA, 50% artist and 50% YuE2 songs, stop well before memorizing) without copying its scripts, which are CC BY-NC. It imports the YuE2 package at run time and doesn't vendor it.
- **It trains on a 64 GB Apple Silicon Mac (PyTorch mps)**, because that's the hardware there is. The YuE2 package already supports mps; the trainer runs attention in query blocks as YuE2 does there. Checked here on a tiny model: the training forward matches the model's own forward exactly, a fresh LoRA changes nothing, and a real-sized adapter merges in yue2.cpp (196 AR tensors).
- **Spoken passages are kept as `[spoken]` sections** in training lyrics, because the recordings contain them; voice tags and staging cues are dropped.
- **LoRAs are local, like voices.** They live in `.cache/` and are never committed or published, and the YuE2 terms (non-commercial) carry over to them.

## 2026-10-16 (YuE2)

- **The vocal goes to YuE2 an octave above where it should sound.** YuE2 sang an octave below the ABC both times we measured (docs/production.md). Gave up: an ABC that matches the lead sheet note for note; the lead sheet and MusicXML still show the real octave.
- **Productions are checked with allowances for timing and octave** (`copyist follow`). YuE2 shortens the intro and drifts, so a check at the planned time scored 0 of 32 on a render that sang every note. Gave up: a single strict number.
- **Production audio goes through yue2.cpp, not the MLX port.** `copyist produce` already called `yue-synth`; the Mac build turns Metal on, and `--device MTL0` selects the GPU. Gave up: mlx-Yue, which is a native Metal port of the same model, for one engine rather than two.
- **One seed drives both of yue2.cpp's seeds, and the requested length is the score.** `lm_seed` draws the performance and `seed` draws the noise; leaving `lm_seed` at its default (-1) would make a new recording every time. The length field defaults to 360 seconds, which would ask for a song far longer than the one written.
- **YuE2 weights are CC BY-NC 4.0, plus an individual-creator permission dated 16 September 2026.** An individual may generate songs and sell those recordings. A company may not use the weights commercially without a separate licence (the YuE team, ryuanab@connect.ust.hk). The permission does not cover selling or redistributing the weights. The GGUF files from Serveurperso/YuE2-GGUF are those weights converted, so the same terms apply. yue2.cpp itself is MIT; the official YuE code is Apache-2.0. Digital Defiance is a company, so shipping these weights inside a product, or selling songs made with them as the company, needs that commercial licence. Using them locally to hear whether a Copyist score survives the render is the use recorded here. Copyist does not ship the weights.

## 2026-10-16 (singing)

- **SoulX-Singer runs as a subprocess in its own Python 3.10 environment.** Its pinned PyTorch 2.2 and Transformers 4.41 shouldn't constrain Copyist, and Copyist stays installable without PyTorch.
- **Score control, no auto-shift.** The model follows the written notes, at written pitch, so the pitch check can hold it to the score.
- **Phrases of about 8 seconds, split at word starts;** a short last phrase folds into the one before. Each phrase is sung separately and placed on one timeline.
- **Voices are reference recordings, kept out of the project.** No training is needed for a new voice. Voices live in the git-ignored `voices/` folder, chosen by whoever runs Copyist, and are never committed, shipped or published. Any voice Copyist ever ships or sells must come from a consenting person and not from another generator's output: Suno's terms, for one, forbid using its output to power other AI or to compete with it.
- **The sung vocal is checked twice:** pitch per note (pYIN, ±50 cents, judged on the middle of the note so scoops and slides are allowed) and words (Whisper, base.en). Both are optional dependencies (`pip install -e ".[sing]"`).

## 2026-10-16 (drums, held syllables, vocals)

- **Drums are built from one list of hits** that produces both the notation (percussion staff, two voices) and the MIDI (GM drum notes on channel 10). music21's MIDI export of unpitched notation is unreliable, and one source keeps written and heard identical.
- **Extender lines are added to the MusicXML after export.** music21's Lyric can't express `<extend>`; marked lyrics are exported with a name attribute and rewritten. Slurs on melismas only where every verse holds, since verses can disagree.
- **`instruments:` in the song file is the first "direction".** Left-out instruments get no part at all, and the report says so. This is the seed of the brief (SPEC 8).
- **Vocal rendering candidates: SoulX-Singer (Apache-2.0) first, YuE2 if its licence fits, ACE-Step 1.5 as the open fallback.** YuE2 plans in ABC itself, which matches Copyist's format, but its weights are non-commercial except for individual creators.

## 2026-10-16 (later)

- **Verovio SVG is rewritten before PyMuPDF turns it into PDF.** Verovio sets stroke colour in CSS, nests a scaled `<svg>`, and draws tempo-mark notes with an embedded SMuFL web font. MuPDF's SVG renderer ignores all three and produced blank pages. `engrave.printable_svg` flattens the nested SVG into a scaled group, adds explicit strokes, and swaps the SMuFL metronome glyphs for Unicode notes (♩, ♪). Gave up: nothing visible so far. If it ever breaks, cairosvg or a headless browser are the fallbacks, at the cost of a system dependency.
- **The page header is written into Verovio's MEI, not the MusicXML credits.** With MusicXML `<credit>`s present, Verovio drops the automatic title and ignores credit font sizes. MusicXML files still carry the credits, for MuseScore and others.
- **The `bars` check reads the song file's bar lines, not music21's bars.** music21's ABC parser re-bars an overfull bar by the meter, which moves the error to the wrong bar number.
- **Bar numbering: a pickup is bar 0, the first full bar is bar 1.** music21's ABC parser numbered a first full bar 0.
- **Right-hand voicings drop the 5th of chords bigger than a triad,** the way pianists usually voice 7th chords; voicings are chosen to move as little as possible.
- **MIDI comes from a "performance" copy** at sounding pitch with chord symbols removed (music21 would otherwise play chord symbols as chords, and the bass would sound an octave too high).

## 2026-10-16

- **Name: Copyist. Tagline: "the song, the score, the sound."** A copyist turns a composer's sketch into correct parts for every player; the tagline covers the rest (writing and recording). Considered Tutti, Broadside, BrightScore, Tin Pan. Using any real person's name (e.g. Sondheim) was ruled out.
- **Score-first architecture.** The canonical score is the source of truth and audio is rendered from it. Gave up: the fastest path to Suno-like audio quality. Gained: correct MIDI and sheet music by construction.
- **Song files are YAML with the melody in ABC.** ABC is compact, human-writable, and what symbolic models (e.g. MuPT) are trained on. music21 parses it, including chord symbols and ties. Lyrics use ABC `w:` syntax but Copyist aligns them itself, so the rules are explicit and testable.
- **music21 as the internal model.** Mature, handles MusicXML and MIDI both ways, and has the theory tools validators need.
- **Verovio for engraving, PyMuPDF for PDF.** Both install with pip on macOS and Linux with no system packages. LilyPond engraves more beautifully but needs a separate install; it can be added as an optional engraver later.
- **TinySoundFont + GeneralUser GS for demo audio.** pip-installable (install with `--no-deps`, since its optional playback dependency, PyAudio, needs PortAudio) and a free SoundFont. Sounds like a demo, which is the M0 goal.
- **Validators are deterministic and block "finished."** They are the quality gate for both people and models.
