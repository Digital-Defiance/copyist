# Decisions

Newest first. One entry per decision: what, why, and what we gave up.

## 2026-10-18 (alto sax)

- **Swing, jazz waltz, blues-shuffle and bossa melodies use Karoryfer Weresax** (CC0 alto, ~50 MB of rr1 dynamic-mic samples, `winds` pack). Copyist writes a simple SFZ (no humanize LFOs, no round-robin) so previews stay deterministic. Upstream's full Sax.sfz stayed out.

## 2026-10-18 (flute)

- **Broadway ballad, Broadway uptempo and march melodies use the VSCO flute** (susvib, CC0, ~25 MB, `winds` pack). Take 1 only (no round-robin) so previews stay deterministic. Clarinet remains the default melody elsewhere; harp still covers Broadway ballad accompaniment.

## 2026-10-18 (fiddle)

- **Country, country-waltz and Celtic jig melodies use the VSCO solo violin** (arco vib, CC0, ~74 MB, `folk` pack) as a fiddle. Copyist writes the SFZ (p/f layers, loops, evened forte). Steel/nylon still cover the accompaniment; clarinet stays the default melody elsewhere.

## 2026-10-18 (electric guitar)

- **Pop, rock, power-ballad and blues-shuffle use Karoryfer Emilyguitar** (CC0 Epiphone, clean program, ~123 MB, `electric` pack). Chord patterns stay on the piano staff; the electric just plays them. Black and Green Guitars stayed out for now (large, LFS-awkward). A dedicated guitar staff still open.

## 2026-10-18 (steel guitar)

- **Country uses Discord GM's Martin HD28 steel-string** (CC0, Jeff Learman, ~3 MB, `folk` pack). Folk keeps the nylon. Copyist writes a simple SFZ (no keyswitches) and links `samples/` to the nested folder so sfizz isn't fed a path with spaces. The guitar still plays the piano-staff patterns; a dedicated guitar staff and Meta Open Sound's larger steel set stay open.

## 2026-10-18 (nylon guitar)

- **Folk uses FreePats' Spanish classical guitar** (CC0 nylon, ~5 MB, `folk` pack). Country started on nylon, then moved to steel (see above). The guitar plays the existing piano-staff patterns (no separate guitar role yet). Strums-as-shapes and a dedicated guitar part stay open.

## 2026-10-18 (music box)

- **Music-box exact preview uses the VCSL glockenspiel** as a stand-in (~17 MB, `bells` pack). No free real music-box library turned up; glock is what docs/sound-set.md already named. New `music-box` style: tinkling melody over soft piano arps, no bass/drums. A true music box and celesta stay on the find list for *I Left the Lights On*.
- **The music box plays an octave above the written melody** (`PLAY_SHIFT`). Its samples start at G4; Amazing Grace and Silent Night sit lower, and stretching them down sounded flat and dull. The score stays as written.

## 2026-10-18 (pipe organ and harp)

- **Hymn and gospel previews use the VCSL pipe organ** (manuals only, Quiet + Loud; Copyist writes the SFZ like the clarinet). Hymn: organ on the melody and the held chords, upright bass under. Pack `keys` downloads it (~86 MB). Gave up: pedals and a real Hammond for this cut.
- **Gospel exact preview: piano tune + synthetic tonewheel pad, no drums.** Pipe organ + kit + clarinet was a kids' band; piano alone was only "I guess better". The tonewheel is sfizz `*sine` drawbars (fixed ~888800000), MIT, no download. Pipe organ stays on hymn; YuE2 still gets Hammond/choir in the style line.
- **Broadway ballad plays the VSCO concert harp** (~35 MB, same `keys` pack) on the arpeggio part. The pit needs a harp more than another piano.
- **Synthetic instruments** (`Instrument.synthetic`): SFZ only, installed by writing `copyist/sound/*.sfz` into the instruments folder. Manifest lists no sample files.

## 2026-10-18 (prosody in compound meters)

- **Prosody and chord-tone "strong beats" use `fit.beat_strength`, not music21's `beatStrength` alone.** In 6/8 and 12/8 the beat is a dotted quarter; a plain quarter is only an eighth-subdivision. The lyric fitter already scored that way; `copyist check` now matches it. Gave up: nothing useful — music21's weights were close on clean 6/8 but not the project's source of truth.
- **The band room keeps stereo place in the wet** (each side through its IR, light crossfeed). Collapsing the dry to mono before the hall made pan pointless once reverb was up. Hall ~1.3 s. Still a synthetic IR, not a measured one.

## 2026-10-18 (less-cheesy exact preview, first cut)

- **Style files can cycle a phrase of bars** (`rh` / `lh` / `bass` / `drums` as a list of bars). One-bar forever was the arranger-keyboard feel; a 2–4 bar cycle is enough to break om-pah-pah without per-style code.
- **The waltz is piano-vocal: melody on the piano, no drums.** The clarinet-plus-kit waltz was the cheese the owner named (rigidity, clarinet, om-pah-pah). Country waltz keeps the kit and the oom-pah on purpose. Piano-vocal mixes put the accompaniment further back and use less room.
- **When the melody is on the piano, the right hand rests.** Same sample library on two MIDI parts was double-striking every shared chord tone. Left hand and bass stay under the tune.
- **Piano melody skips voice-style legato.** Overlapping successive notes (~15 ms) sounds right on a clarinet and clicks on Salamander; `melody_legato=False` releases before the next hammer.
- **Ballad, hymn and lullaby follow the same idea** (2026-10-18, continued): piano melody, no kit on ballad/hymn, phrase cycles under the tune. Broadway ballad keeps the clarinet and varies its arpeggio phrase. Solo-piano textures (lullaby, no bass) keep the right-hand figure but drop pitches the melody is already playing.
- **Uptempo styles get phrase cycles, not piano-vocal** (straight, pop, rock, country): the kit and clarinet stay; patterns answer across two bars. Folk is piano-vocal with `keep_rh: true` so the fingerpicked figure remains under the tune.
- **Every style now cycles a phrase** on at least one of rh/lh/bass (2026-10-18). One-bar forever was the cheese; two-bar answers keep each style's identity (skank, Charleston, oom-pah, boogie, …).
- **The band builds across the song** in the performance (soft open → full middle → settle), not the melody. Same notes, clearer form by ear.
- **The mix places parts in stereo** (constant-power pan: piano a little left, drums a little right, melody and bass centre) so the preview isn't a mono pile in one room.
- **Gave up for this cut:** more melody instruments beyond piano/clarinet (needs libraries), and a fancier room. Those stay on TASKS 3f.

## 2026-10-18 (previews and score editing)

- **Previews are a ladder, not "YuE2 or cheese".** Rejected: making YuE2 the default audition for every write candidate (about a minute each, and it judges production sound, not whether the notes are the right tune), and settling for a bare rehearsal-piano as the only band preview. Kept:
  1. **Fast, exact preview** (seconds): the sampled band playing the written notes. Make this good enough to judge a melody and a style by ear: phrase-level patterns, builds, a melody voice that fits the style (or piano-vocal when that helps), and a real mix. This is the default for `copyist write`, the style gallery, and "does this transcription sound right".
  2. **Sung guide** (optional): SoulX on the melody over that band or piano, when you need to hear the words on the notes without a full production.
  3. **Finished take** (YuE2, optional or on demand): when judging production sound, styles as records, or a kept song. `write --takes` and `gallery --takes` stay; they are not the default audition.
- **Score editing is two modes, both first-class.** By ear for people who can't read music (listen, nudge, try another bar, A/B). By note for people who can or want to: click and drag on the score, change pitch/length/chord, edit lyrics under notes, and round-trip through MusicXML. The score stays the source of truth either way; audio re-renders from the edited score. Gave up: treating note editing as optional or "later for MuseScore only".

## 2026-10-18 (transcription)

- **Copyist's own transcriber is the default; SheetSage2 is optional.** SheetSage2 (through yue2.cpp) is the most accurate we measured, but its weights are CC BY-NC 4.0 with no permission for creators to sell their songs, unlike YuE2's. Copyist's own engine is open code (MIT, librosa, Demucs) and free for any use. The page names SheetSage2's licence and asks the person to accept it. Gave up: the best accuracy by default, for now.
- **A transcription becomes a song through melody writing's path:** the engine writes planner-dialect ABC, and `write.song_from_plan` makes the song file, keeping the octave as sung. One way in, tested twice over.
- **Meter is found on a grid of eighths, beat first, then bar,** so 6/8 and 12/8 are heard as such, and a tracker that locked onto off-beats or quarter pairs doesn't matter.
- **The lyric fit listens:** a transcription tells the fit where syllables really start (a breath, a consonant) and where the voice only moved (a melisma).
- **The truth set is Copyist's own public-domain songs** (band renders and YuE2 takes), never the owner's songs, which stay on her Mac.

## 2026-10-18 (melody writing built; transcription rules)

- **Song files write every accidental.** YuE2's plans carry an accidental through the bar; music21, which reads Copyist's songs, doesn't (measured: `^F f F` reads F#4 F5 F4). Written songs repeat the accidental on every altered note, so they read the same under both rules. Gave up: the shortest possible ABC.
- **2/4 plans become 4/4.** The planner writes 2/4 even when asked for 4/4, and no style plays 2/4; two bars become one, paired so the chords change on the downbeats. Gave up: the planner's own barring when it really meant 2/4 (a march); a 2/4 style can bring it back.
- **The lyric fit adds a within-word stress rule** to the spec's costs: a word's stressed syllable mustn't land on a weaker beat than its neighbour, the rule `copyist check` warns about. The first real plan sang "A-bash" without it.
- **Keeping a candidate writes its score** from the page, so one press gives a finished song with lead sheet, score and parts.
- **Transcribing recordings (when it's built) resolves doubt by musical logic** and asks by ear when still unsure (SPEC 12.2a), rather than taking the loudest frame. The owner asked for it.

## 2026-10-17 (melody writing and the open singer)

- **Melody writing starts with YuE2's own planner** (`yue-plan`), not a melody model of Copyist's own. YuE2 writes melodies learned from real songs, and its planning stage runs alone, text in and text out, so Copyist gets the score without rendering audio. Copyist's part is everything around it: the right octave and range, lyrics fitted by stress and phrasing, validation, ranking, and choosing by ear. Gave up: a melody source free of YuE2's licence, for now. A rule-based writer and the open singer's planner come later.
- **Plan B for the singer: train our own lead-sheet conditioning onto HeartMuLa-oss-3B** (Apache-2.0), using MuLaCover's published method and code (Apache-2.0), not its non-commercial weights. Considered:
  - using ACE-Step 1.5 or HeartMuLa as they are: they can't sing a given melody, which breaks the product;
  - guide-and-restyle, re-performing a SoulX-plus-band guide through ACE-Step's cover mode: quick, but it only approximates the melody.

  The owner chose B.
- **Training data has clean rights only:** HeartMuLa's own outputs, public-domain and original lyrics, and Creative Commons recordings, each logged in a manifest. Never: YuE2, MuLaCover, MiniMax, Suno or Mozart outputs, copyrighted recordings, or the owner's own songs.
- **The handoff is written down** (AGENTS.md "Start here", TASKS.md 3g and 3h, the two specs, `.cursor/rules`), so another agent (Cursor) can continue if this session stops.

## 2026-10-17 (open source)

- **MIT licence, open to contributors now.** The copyright line reads "Digital Defiance and Copyist contributors". MIT is the most permissive choice and the easiest for anyone to build on. Gave up: GPL's guarantee that forks stay open.
- **Contributions are welcome from the start,** with tests running on GitHub (Linux and macOS) on every push and pull request. Styles and instrument packs are data files, so they're the natural first contributions.
- **The model and sample licences stay separate from the code's.** Nothing licensed differently is committed; it downloads from its own source with its licence shown.

## 2026-10-17 (styles)

- **As many styles as make sense: anything that can be written as a correct score in twelve-note notation.** Correct sheet music is what sets Copyist apart, so that's the line. Music built on notes between the piano keys (maqam, raga, gamelan) and rap verses are out for now, because the score would be wrong or empty.
- **A style is a data file, not code** (`copyist/styles/*.yaml`, `copyist-style/0`). Adding a style means writing a file, which is how the list can grow quickly. The files are checked when they load, and every style is arranged in the tests. Gave up: arbitrary logic per style. What patterns can't express becomes a named generator in the arranger (`walk`, `line`), usable by any style.
- **The original three styles were ported note for note** (same MIDI, byte for byte), so nothing already made changed.
- **Swing lives in the performance, not the notation.** The score shows straight eighths with "Swing" over them, as charts do. The MIDI plays the off-beats at two thirds of the beat, and `--plain` keeps that, because the swing is part of how the music is written to be played.
- **The gallery picks a tempo inside each style's range,** since a pop take at hymn tempo would mislead. Using a style can change the song's tempo too, and only the `style:` and `tempo:` lines of the song file change.
- **Styles come in waves, each with the parts and instruments it needs.** A style whose band doesn't exist yet (organ, guitar, strings) would only be a sketch.
- **The voice gets the treble clef unless the song says otherwise.** music21 guessed the bass clef for a melody between C4 and G4.

## 2026-10-17 (the sound set, wired in)

- **The sound set is for everyone's music.** Copyist isn't built around one songwriter's genres: music boxes, Broadway pits, country bands, hymns and synth pop all need instruments, and the arranger needs templates that write for them. So instruments come in packs, each with the templates that use it. The band pack came first because every template needs it. Music box and celesta come next, because *I Left the Lights On* uses them.
- **One part at a time, then mixed in Python.** sfizz plays one SFZ per render, so each part is rendered alone and the parts are mixed in Copyist. That gives stems for free and keeps the mix under our control. Gave up: one-pass rendering and sfizz's own effects.
- **Parts are balanced by loudness (BS.1770), not by peak.** Sample libraries are recorded at very different levels: the clarinet peaks at -24 dBFS, the drums at -9. Measured loudness puts each part a set amount under the melody (piano 4 dB, bass 6, drums 9). The numbers are a starting point for listening, not final.
- **A gentle master: -16 LUFS, peaks under -1 dBFS, at most 4 dB of limiting.** If more limiting would be needed, the mix stays quieter. Gave up: competitive loudness. The band render is for checking the score.
- **The mixing is plain numpy** (FFT K-weighting, FFT convolution, a block look-ahead limiter), so it runs anywhere the engine does, without scipy.
- **Instruments are checked against their git object ids, not SHA-256.** The libraries live in git, so `git ls-tree` gives every file's id at the pinned commit without downloading anything. The manifest can't drift from the library, and building it is cheap. Gave up: a stronger hash. SHA-1 here guards against corruption and mixed versions, and the pinned commit is SHA-1 anyway.
- **Only the files an instrument plays are downloaded:** the SFZ, its includes, its samples, the licence and the readme. The band is 1.1 GB, against several GB for the whole libraries.
- **The clarinet's SFZ is ours, written from measurements.** VSCO ships WAV files only. Every number in the SFZ (key, tuning, start offset, loudness, loop points) comes from measuring the samples, and the measured pitch wins over the file name.
- **The SoundFont stays as the fallback,** so `copyist build` always makes audio, and the report and page say why the real instruments didn't play.

## 2026-10-17 (performance and sound set)

- **The performance is a MIDI-to-MIDI step after the arrangement,** not part of the score. The score and the part PDFs stay exact; only the sound is played. It never adds, removes or moves a note to another pitch, which the tests check. Gave up: performance marks (hairpins, rubato) written into the score; they can come later from the same rules.
- **It's seeded and on by default.** The same song and seed give the same MIDI, so builds stay repeatable; `--plain` gives the grid.
- **Instruments come from CC0 and CC BY libraries played by sfizz** (docs/sound-set.md): Salamander piano, Karoryfer basses and guitars, AVL drums, VSCO 2 and VCSL. They're downloaded from their own repositories, not shipped.

## 2026-10-17 (desktop app)

- **Models are pinned and verified.** Each file in `copyist/models.py` names a repository revision, a size and a SHA-256; a download that doesn't match is deleted. A repository that changes upstream can't change what Copyist installs. Gave up: picking up new model versions automatically.
- **The licence is shown and accepted before the first download,** on the page and on the command line. The weights are non-commercial, and the person downloading them is the one agreeing to that.
- **Models live in a data folder shared by every library** (COPYIST_HOME, else the platform's usual place); a developer checkout's `.cache/` still counts, so nothing changes for development.

- **Copyist becomes a free, open-source desktop app (Tauri 2) that runs everything locally,** rather than a hosted service. YuE2's weights are non-commercial with an individual-creator permission: each user's app downloads them, and users may sell their own songs, while Copyist makes no commercial use of them. It also keeps songs private and needs no servers. Gave up: revenue from the app itself unless the YuE team licenses it; people without a capable GPU.
- **The page stays the interface; the Python engine and yue2.cpp ship as Tauri sidecars.** Tauri 2 bundles external binaries (`externalBin`), names PyInstaller for Python servers, and signs sidecars when it notarizes on macOS. Gave up: a single-language app.

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
