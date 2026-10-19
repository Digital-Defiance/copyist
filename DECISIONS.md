# Decisions

Newest first. One entry per decision: what, why, and what we gave up.

## 2026-10-19 (key changes, and the scorer's alignment)

- **Copyist's ABC reader keeps every bar through a key change, and each note leaves it with its own accidental.** SheetSage2 and yue-plan write a key change as a `K:` line in both voices, or `[K:…]` inside a bar. `abcplan.parse` started a new plan at every `K:` line, so it kept only the bars after the last one, and it refused `[K:…]`. Now `abcplan.read_vocal` follows ABC 2.1 and SheetSage2's own writer. The first `K:` ends the header and sets every voice's key. After that, a `K:` line or `[K:…]` changes the key of the voice it's written in, from that point on. Accidentals hold for their letter, in every octave, until the bar line or the key change. Every note then gets the accidental for the pitch it sounds (`=` for a natural), so the rest of the pipeline reads the right pitch under one key, with no other change. That also fixes a bug: pairing 2/4 bars joined one bar's `^f` with the next bar's `f`, and the F came out sharp. Any other inline field, and a key Copyist can't read, is refused. Gave up: nothing.
- **A song file holds a key change as one key signature, with an accidental on every note the change alters; the report says in which bar the key changes.** This is the song's `key:` (the key at the first sung note), and the format stays `copyist-song/0`, since SPEC §4's ABC subset never had fields. Inline `[K:…]` in the melody was the preferred form, but it fails at the first stage. music21 10.5.0 ignores it, so the notes after it sound in the old key (F and C where F♯ and C♯ were meant), the `key` check passes, and the YuE2 export writes the same wrong notes. A `K:` line in the melody plays the right pitches, but the `bars` check counts it as a note, and music21 keeps a single key signature either way, so the page never shows the change. `copyist write` and `copyist transcribe` both write the change this way; SheetSage's joined short bars keep a `K:` line at the change, so the report can name the bar. Gave up: a change of key signature on the page.

## 2026-10-19 (the owner's goal, and SheetSage kept away from her songs)

- **Copyist's purpose, in the owner's words, has two parts.**
  - **Part 1:** transcribe the audio demos of her musical *I Left the Lights On*, which have no sheet music, and reproduce them with YuE2 from the transcriptions as closely as can be measured. Then make lead sheets and orchestra arrangements from them.
  - **Part 2:** write her second musical from scratch.
  - Gave up: nothing. This orders the work: the transcriber, the closeness loop, then arrangements.
- **SheetSage never touches the owner's songs, not even as a yardstick.** Owner's call. Her lead sheets come only from Copyist's own engines, so no song of hers carries SheetSage's non-commercial terms. SheetSage stays an optional engine for other people, with its licence shown, and a yardstick on public test sets only.
  - The Lights On loop waits for our engine.
  - SheetSage files already made from June Snow on 2026-10-18 went to the Trash with her OK: a transcription, and a take rendered from another. SheetSage2 came out of both Copyist model folders; the only copy left is test-only (TASKS §7).
  - Gave up: a private comparison on her songs, and starting the loop with today's engine.

## 2026-10-19 (the open transcriber: what it builds on, and how it's judged)

- **The trained transcriber builds on Basic Pitch and SoulX-Singer (both Apache-2.0), though their own training data can't be audited.** Owner's call. Basic Pitch is only a frozen input under our own head; SoulX sings the training data. Newer options were checked and set aside: VocalParse (Mandarin, 1.7B, crawled data), T3MS, the phoneme-informed model, VOCANO and ROSVOT (weights trained on non-commercial singing sets), and VocalRender (Apache-2.0 score-native singer, but its checkpoints are Mandarin-only; watched for an English one). Gave up: a fully auditable data chain, which only an open singer trained on our own data would give (plan B).
- **Compute is the owner's M4 Max (64 GB) only; no rented GPU.** Owner's call. Gave up: the one-to-two-day rented path; making data takes nights instead.
- **The trained weights will be MIT, like the code.** Owner's call; the plan had suggested Apache-2.0, like Basic Pitch. Gave up: Apache's explicit patent grant.
- **The benchmark is held out by code, not by convention.** `open_transcriber/data/heldout.py` reads every `songs/*.yaml` and the round-trip cases at runtime and rejects a training score that matches one by title, lyrics or a transposition- and tempo-invariant melodic fingerprint; the sampler re-rolls on a hit. Gave up: nothing; without it the scores would mean nothing.
- **SheetSage2 is a yardstick only:** run once on all seven test songs to measure the gap, never used to teach or to tune. Owner's call.
- **YuE2 renders may be training material for the transcriber,** in the second data round. Owner's call.
  - **What goes in:** renders of sampler scores only, never held-out tunes. Each phrase is aligned and checked note by note: a clip needs 95% of its notes within ±50 cents, and failed notes are masked. Labels are melody only, because YuE2's band doesn't always play the written chords. YuE2 audio is a separate, tagged slice of the manifest, so a model can be retrained without it.
  - **Why:** it's the most realistic singing we can make, closer to real records than SoulX over the band.
  - **Checked 2026-10-19, nothing prohibits it,** so the owner said to go ahead. The sources: the weights' `LICENSE` on Hugging Face (the plain CC BY-NC 4.0 text, covering the checkpoint files) and the licence table in the YuE2 GitHub README. Neither has a clause against training on outputs, unlike Suno's terms. The creator permission lets personal users, creators and musicians use YuE2 and monetize its outputs, and it bars only illegal, harmful, deceptive or unethical use. The one line that could touch us is "commercial use by companies: contact us". Copyist is free, with no money changing hands, and it never ships or redistributes YuE2's weights. If that ever needs settling, the README's licensing contact is lauryliuyang@hkgai.org; the 2026-10-16 contact is now listed for academic collaboration.
  - **Judging:** YuE2 learned from SheetSage2's transcriptions, so YuE2 takes favour SheetSage2, and would favour a model trained on YuE2 too. Real recordings, not YuE2 takes, decide whether we're better.
  - **Gave up:** a training set with no licence doubt.
- **Goal raised: the best open transcriber available, beating SheetSage2 objectively,** for songs, musicals and orchestral music (owner). A design audit comes before T1 trains anything. Gave up: starting the GPU data work today.
- **The transcriber's budget is $0.** Owner's call.
  - **What it rules out:** every dataset, model and tool must be a free download. No test recordings are bought, and there's no external drive. Copyist keeps recipes rather than renders, and stores only the costly audio (SoulX and YuE2) as FLAC.
  - **Disk:** about 300 GB at most of the Mac's own disk (685 GB free after the owner's cleanup), for training and testing only, never long term; jobs stop by themselves below 150 GB free. Owner's call. Once the test is published and the model ships, a final stage shrinks the project to about 15 GB. It keeps the COTB recordings and their truth, plus manifests that can rebuild the rest.
  - **Rock Corpus is out:** the owner owns none of its songs.
  - **What replaces Rock Corpus,** SheetSage2's rock test, whose recordings must be bought, so it can't be scored:
    - RWC's other 75 sung pieces (CC BY-NC, testing only);
    - the Creative Commons songs with karaoke charts in UltraStar Deluxe's GitHub song library (the owner's idea), 32 of the 39. The 2 under older no-derivatives licences are left out, because a transcription may count as an adaptation, which those licences don't allow. The 4 that are in HookTheory's training split are scored apart.
  - **Non-commercial test material is for testing only, with safeguards.** The owner left this to the audit's judgment. It covers RWC, the non-commercial karaoke songs, and runs of SheetSage2, MuScriptor and YourMT3+. These songs are never trained on, shipped or shared; for them we publish only scores and credits, never their audio or our transcriptions. Why: testing a free MIT tool with nothing sold sits on the non-commercial side, and RWC's re-release says its licence covers research, including research inside companies. This is a reading of the licences, not legal advice; ask a lawyer before publishing results if certainty is wanted.
  - **Gave up:** a head-to-head on SheetSage2's rock test. A claim to beat it on its own ground rests on RWC-Pop alone, and we'll say so.
- **Real recordings decide "best"; YuE2 takes are practice.** The owner agreed. YuE2 learned from SheetSage2's transcriptions, so its songs flatter SheetSage2, and would flatter us once we train on YuE2. Real recordings with clean rights flatter neither. The five truth takes and the two big songs become dev sets. Gave up: the convenience of a benchmark we can make ourselves in a minute.
- **Nothing waits on the owner's listening, hands-on work or time.** Owner's call.
  - **Test truth:** checked automatically by two independent aligners and torchcrepe pitch checks.
  - **Listening tests:** replaced by a playback check, which renders each transcription with Copyist's band and compares it with the original by pitch track and chroma.
  - **Correction effort:** measured with a simulated listener, a script that picks the alternative closer to the truth.
  - **GPU jobs:** agents on the Mac start and watch them. The Mac is her laptop, so they run in windows she agrees to. Agents ask ahead, saying how many hours they need, and she keeps it plugged in with the lid open. Jobs resume from checkpoints, pause on battery and keep the Mac awake while they run. Gave up: unattended "whenever it's idle" scheduling, which a laptop that travels can't promise.
  - **Gave up:** human listening as an endpoint. An automatic sound check can't be validated without people, so it backs up the claims rather than deciding them.
- **The transcriber may build on a ready-made "ear":** a pre-trained audio model with an open licence whose own training data can't be audited. Owner's call, on the same standard as Basic Pitch and SoulX. A fair bake-off on dev sets picks which one, with Whisper's encoder as a partner for lyrics. The candidates are MusicFM, Dasheng and HeartCodec's encoder. Gave up: an auditable data chain under the encoder. Training our own from scratch would take weeks of GPU and would very likely hear worse.
- **The song format moves to `copyist-song/1`.** Owner's call.
  - **What it adds:** tuplets, inline key, meter and tempo changes, repeats and voltas, and an optional second vocal line. Higher tiers (piano-vocal and short scores) live in MusicXML parts beside the song file.
  - **Versioning:** a version bump in SPEC §4 and a converter, so every `copyist-song/0` file keeps working (the AGENTS rule).
  - **The catch:** music21 10.5 drops inline `[K:]` (probed 2026-10-19), so Copyist must handle inline changes itself rather than trust music21's ABC reader.
  - **Gave up:** the simplicity of one key, meter and tempo per song.

## 2026-10-19 (v0.0.1 release and where the cask lives)

- **The cask lives in Digital Defiance's existing tap, `Digital-Defiance/homebrew-tap` (`Casks/copyist.rb`), and people install with `brew install --cask digital-defiance/tap/copyist`.** The copy in this repo is gone so the two can't drift. This replaces the earlier choice to keep a tap in this repo (2026-10-18, below): a repo not named `homebrew-…` needs a full tap URL, and the owner already has a tap. The tap's cask is updated only after the release asset downloads with a matching SHA-256. Its `zap` leaves `~/Music/Copyist` alone, because those are the person's songs. Gave up: one repo holding both the app and its cask.
- **The release DMG is built, signed, notarized and stapled on the owner's Mac and attached with `gh release create`; `release-mac.yml` only uploads unsigned workflow artifacts.** Before, the workflow would have uploaded an unsigned DMG with the same name to the tagged release, which could replace the notarized one. Gave up: releases built in CI, until CI has the signing certificate.
- **v0.0.1 ships for Apple Silicon only (`depends_on arch: :arm64`).** An Intel DMG can't be built and smoke-tested on this Mac; CI's unsigned Intel build stays a compile check. Gave up: an Intel Mac build in the first release (follow-up in TASKS §3d).

## 2026-10-19 (Mac packaging leaves git clean)

- **`freeze-engine.sh` writes `dist/copyist-engine-<triple>` (ignored); `bundle-mac.sh` copies it over the tracked placeholder in `app/src-tauri/binaries/` only for the build and puts the placeholder back on exit (a trap), and hands Tauri the extra sidecars through a temporary `--config` file (Tauri merges it over `tauri.conf.json`; the array replaces the engine-only list).** A full freeze and signed bundle now leave `git status` empty, and a fresh checkout still compiles against the placeholder. CI calls the same script. Gave up: freezing straight into `binaries/` (one stray `git add` puts 200 MB in history) and rewriting `tauri.conf.json`.
- **The app's engine leaves out the neural transcriber (open-transcriber, Basic Pitch, TensorFlow).** PyInstaller followed `--engine neural`'s import into TensorFlow and the engine grew from ~200 MB to ~410 MB, yet the page doesn't offer the neural engine and its models aren't bundled. In the app, `--engine neural` stops with its "needs the open-transcriber submodule" message; the open engine and SheetSage2 work as before. Gave up: neural transcription in the app until it's the default (bundle its models then).
- **The engine sidecar runs in its own process group.** The frozen engine is PyInstaller's launcher plus the Python it starts; Tauri's quit sends SIGKILL to the launcher alone, which left the Python serving after the app quit (eleven stale engines were found on 2026-10-19). With `set_process_group(true)` the kill takes the whole group, including any job the engine started. Gave up: nothing; a force-quit of the app itself still can't clean up.

## 2026-10-19 (desktop packaging in git)

- **The committed `tauri.conf.json` lists only the engine sidecar; `bundle-mac.sh` adds the yue/sfizz sidecars it stages.** Those binaries come from `.cache/` and are gitignored, so listing them in the committed config would break `npm run dev` on a fresh checkout and the unsigned `release-mac.yml` build. The engine placeholders stay tracked; the frozen ~200 MB engine never goes in git (GitHub refuses files over 100 MB). Lock files (`Cargo.lock`, `package-lock.json`) are committed for reproducible app builds. Gave up: a config that matches a full local bundle without the script's rewrite.

## 2026-10-19 (neural engine wired; MT3 deferred; Omnizart blocked on arm64)

- **`--engine neural` uses open-transcriber Basic Pitch + Copyist `clean_notes` for melody, open draft for harmony.** Default stays `open` until every round-trip row wins. Magenta MT3 skipped for sung takes (upstream: not trained on singing). Omnizart chords wrapped but fail on Apple Silicon (x86 `nnls-chroma` Vamp). T1 training deferred while −0.01/−0.02 note gaps remain. Gave up: shipping Magenta MT3 as the melody engine; treating Omnizart chords as ready on M-series Macs.

## 2026-10-19 (adaptive Basic Pitch ≈ open engine)

- **open-transcriber's default path is adaptive BP + tidy / clean_notes, not raw BP.** Raised defaults; loose re-run when notes < 75% of lyric target (Major-General, no same-pitch merge); strict presets when flooded only if they hit the count or clean up substantially; Copyist `clean_notes` on lyrical takes. Table (with clean_notes): SN 0.85 (+0.05), Tyger 0.97 (+0.19), Saints/AG/MG within 0.02. Mean ~0.87 vs open 0.83. Gave up: always preferring the closer note count (hurt Tyger); forcing the lyric count (hurt AG); Magenta MT3 for vocals.

## 2026-10-18 (T0 Basic Pitch loses on lyrical takes)

- **Spotify Basic Pitch (Apache-2.0, CoreML) is the first T0 baseline.** Raw note F1: Saints 0.46, Silent Night 0.58, Amazing Grace 0.37, Tyger 0.64, Major-General 0.82 — vs open engine 0.85 / 0.80 / 0.88 / 0.78 / 0.84. High recall, severe over-segmentation except on allegro patter. On Python 3.12 macOS, install with `open-transcriber/scripts/setup_baseline.sh` (pip's tensorflow-macos pin is unavailable). Gave up: treating off-the-shelf BP as a product engine without Copyist's tidy path or training.

## 2026-10-18 (open-transcriber as a submodule)

- **Neural lead-sheet work lives in its own MIT repo** ([Digital-Defiance/open-transcriber](https://github.com/Digital-Defiance/open-transcriber)), vendored as the git submodule `open-transcriber/`. Copyist keeps the product gate (`roundtrip.py`), tidy path, and `--engine` wiring; the submodule holds baselines, training and inference. Gave up: growing a large train/infer tree inside `copyist/` or cloning only into `.cache/` (not versioned with the product).

## 2026-10-18 (scoop fold when lyric overshoot ≥ 2)

- **After the mild overshoot gate, fold brief approach tones (≤0.28 s, ≤2.5 semitones, some spread) down to the lyric count — but only if overshoot was ≥ 2.** Saints sat at 35 vs 33 (D-before-E scoops); the old target+2 gate never fired. Forcing every song to the exact count hurt Amazing Grace and Tyger. Gate on ≥2 extras: Saints 0.79→0.85; AG 0.88 and Tyger 0.78 flat. Gave up: always folding to the lyric count.

## 2026-10-18 (cap consonant onset pull)

- **`pull_onset_start` moves a note start back to a nearby onset by at most 0.08 s** (was uncapped within a 0.15 s window). Uncapped pulls on Silent Night's YuE2 take walked some onsets ~0.12 s early; the quarter-beat match then lost D5/F5 (note F1 0.77). Cap → 0.80; Tyger 0.76→0.78; other rows flat. Forcing note count to 46 with onset splits matched the lyric tally but dropped F1 to 0.74 — the four missing pitches aren't hiding in long same-pitch holds. Gave up: uncapped consonant lead-in.

## 2026-10-18 (tonal chord prior + open neural lead-sheet plan)

- **Chord reading adds a tonal boost (I/IV/V(7)/vi in major) and, in compound meter, dearer mid-bar changes plus wider chroma smooth.** Silent Night's YuE2 band was naming Dm/Em every bar against written C/G7/F; priors lifted chords 0.40→0.69 without moving note F1. Saints 0.83→0.89, Amazing Grace 0.78→0.91, Major-General 0.61→0.79. Gave up: matching the take's played harmony instead of the lead sheet (evaluation stays vs written).
- **A commercially usable neural lead-sheet engine is planned (docs/open-transcriber.md), not started.** Apache/MIT stack only (MT3, Omnizart, Demucs); no SheetSage/MuScriptor weights. Gate is the same round-trip table; open DSP stays default until neural wins. Gave up: treating SheetSage as the product path.

## 2026-10-18 (lyric note target includes melisma holds)

- **Open-engine tidy target = syllables + `_` holds + `*`** (`lyrics.note_target` / `slots_available`), not syllable count alone. Silent Night is 46 notes / 41 syllables; targeting 41 left F5-adjacent gaps. Also keep long loud notes within ±12 of the median (Silent Night's F5). Blind bisection only when starting count < 85% of target; mild shortfalls stop at ~92% so weak onset fills don't tank precision. Round-trip: Silent Night 0.76→0.77, Amazing Grace 0.82→0.88, Major-General 0.79→0.84 (128 vs 128); Saints flat; Tyger 0.78→0.76.

## 2026-10-18 (key from the most confident chroma source)

- **`choose_key` picks among accompaniment, mix, vocal, and melody pitch-class histograms** by Krumhansl margin. When the Demucs band stem's own key is weak or disagrees, chord chroma comes from the mix. Major-General was C#m @ 0.09 from accompaniment alone; mix/melody said Eb — now Eb, chords 0.46 → 0.61. Saints/Silent Night flat; Tyger chords 0.78 → 0.81. Gave up: always using accompaniment only (wrong when the stem is thin).

## 2026-10-18 (lyric-guided split for allegro patter)

- **When lyrics give a syllable target and clean_notes under-counts, `split_toward_target` cuts long same-pitch holds** (inner onsets first, else bisect by the tracked eighth). YuE2's Major-General take follows the score (124/128 by `follow`) but pYIN heard ~80 continuous-pitch notes; without the split, open-engine F1 was 0.44 (43 vs 128).
- **`fold_grid_rearticulations` takes a `floor` (lyric count) and a 0.4 length ratio** so equal eighths on a pedal don't cascade-merge after rhythm snap. Major-General: 0.44 → 0.79 (117 vs 128). Saints stays 0.79; Tyger 0.76 → 0.78. Gave up: loosening the onset loudness climb (hurt Saints).

## 2026-10-18 (MusicXML import + Major-General stress case)

- **`copyist import` turns MusicXML into a song YAML** (melody ABC, chord symbols, lyrics by verse, key/meter/tempo). Prefers a part named like Voice/Melody when a piano-vocal score has several. This is the first slice of MusicXML import; full edit round-trip that preserves every Copyist field is still open. Gave up: blocking the Major-General table row on that fuller import.
- **Major-General stress case is a lead-sheet reduction of Sullivan's No. 13** (verse 1 only, ~128 eighths, Eb, broadway-uptempo), not a full vocal-score dump. Source rights: Gilbert & Sullivan 1879 / US PD vocal score. Produce truth take on the Mac before `roundtrip.py` can score it.

## 2026-10-18 (gentle fragments only when lyrics say we under-detected)

- **If `clean_notes` finishes under 92% of the lyric syllable count, retry with gentler fragment folding** (keep short steady step-tones). Always-on gentle folding lifted Silent Night but hurt Saints; the undershoot gate gets Silent Night 0.74 → 0.76 with Saints/Tyger/Amazing Grace flat. Round-trip now includes Amazing Grace (0.82). Hardest case remains Silent Night (46 true notes, chords still ~0.40 vs the take's band).

## 2026-10-18 (tighter re-articulation keeps repeated syllables)

- **Re-articulation fold: short < 0.25 s (was 0.4) and neighbour gap < 0.25 s (was 0.4).** The looser rule merged Tyger's same-pitch syllable pairs into one note (0.69 F1). Tighter: Tyger 0.69 → 0.76, Saints flat at 0.79, Silent Night 0.75 → 0.74. Grace-note echoes still fold; equal-weight repeats stay.

## 2026-10-18 (waltz guard on double-tempo → 6/8)

- **Skip the Silent Night double-tempo→6/8 rebuild when the plain eighth grid already prefers simple meter with confidence ≥ 0.35.** Tyger's YuE2 take (written 3/4 @ 80) has the same tracked≈108 / peak≈54 shape as Silent Night, but acoustically it's four pulses per waltz bar (~107 ≈ 80×4/3); forcing 6/8 @ 54 was wrong. After the guard: 4/4 ~108 (same bar length as 3/4 @ 80), note F1 0.67→0.69. Silent Night stays 6/8 (plain simple confidence only ~0.21).

## 2026-10-18 (late downbeats beat solo offbeats in rhythm snap)

- **Solo eighth pattern cost 0.05 → 0.25.** A lone onset ~0.35 into the beat was snapping to the and-of-beat; on Saints' YuE2 take that was a systematic +½-beat error (note F1 0.74 → 0.79). Silent Night unchanged. Real off-beats (onset ~0.5) and two-onset (0, ½) patterns stay. Gave up: forcing every onset before 0.5 to the downbeat (hurts Silent Night).

## 2026-10-18 (transcription improves by round-trip F1, not owner-song ear alone)

- **The yardstick is `scripts/transcribe/roundtrip.py`:** public-domain score → YuE2 truth take → open engine → note/chord F1. Keep a change only when that table rises and no row collapses. June Snow remains a listen check after a win — it has no written truth, so ear-only chasing misled (open engine scored higher on `--sung`/`follow` but felt more broken).
- **Measured trade-off:** keeping short steady "passing" notes helps Silent Night (~0.75→0.77) but hurts Saints (~0.74→0.71). Left the Saints-winning fragment fold in place until a rule helps both.

## 2026-10-18 (YuE2 snaps tuplets; open engine avoids them in 4/4)

- **`copyist produce` snaps tuplet onsets/lengths to sixteenths** when YuE2's ABC can't write them (`yue.snap_to_unit`). Open-engine June Snow had `4/3` figures from beat-triplet patterns and refused to render. The song file keeps the rhythm for reading; the take approximates it. Gave up: refusing the whole produce.
- **Simple-meter `BEAT_PATTERNS` no longer offer 1/3 onsets.** Spurious triplets on Broadway takes hurt feel and blocked YuE2; 6/8 still uses `COMPOUND_PATTERNS`.

## 2026-10-18 (ornament folding + scoring owner songs)

- **Short same-pitch re-articulations fold into the longer note**, even with an onset and across a brief rest; after rhythm snap the grid does the same. Equal-length repeated syllables stay. The lyric-count fold now stops near `target + 2` / `1.08×` (was `1.25×`, which let Saints' 41 notes past a 33-syllable lyric). Stray pitches more than 7 semitones from the line's median drop. Saints YuE2 take: 0.68 → 0.74 note F1. Gave up: folding every same-pitch pair (real repeated notes in the tune).
- **Owner songs without a score are scored with `evaluate.py --sung VOCAL.wav`** (pYIN + tidy as truth) and/or `copyist follow`. SheetSage June Snow sat ~0.32 note F1 vs the vocal — useful before/after, not a written-score F1.

## 2026-10-18 (desktop app is the default install)

- **People install `Copyist.app` (Homebrew cask), not a bare `pip` + `copyist serve`.** The Tauri shell is the product; the CLI and `copyist serve` stay for contributors. Optional packs (band, singer, voices) download from **Install extras** when chosen — writing with the rules engine needs no download. Gave up: treating the browser UI as the primary story on the README and site.
- (Replaced 2026-10-19: the cask moved to Digital-Defiance/homebrew-tap.) **Homebrew tap lives in this repo** (`Casks/copyist.rb` + `brew tap digital-defiance/copyist`). Releases attach DMGs from CI; SHA-256 is filled in after the first notarized build. Gave up: waiting to submit to homebrew-cask before anyone can `brew install --cask`.
- **Ship with Digital Defiance's Developer ID Application (`J6887N729S`),** not the personal Developer ID. Same keychain has both; `bundle-mac.sh --sign` prefers the Defiance identity. Notarization uses an app-specific password (or ASC API key) kept outside the repo.
- **Freeze via `scripts/package/engine_entry.py` (absolute import of `copyist.cli`), not `copyist/__main__.py`.** PyInstaller runs the entry as a bare `__main__` script, so relative imports die. Also `--copy-metadata` / `--collect-all` for `cmudict` and `pronouncing` — they call `importlib.metadata.version` at import. Gave up: freezing `__main__.py` directly.
- **SheetSage2 is a downloadable Install-extras pack** (`sheetsage` + MERT, ~1 GB), offered on Transcribe when missing, with its stricter NC licence (no creator sell-through). `yue-transcribe` ships with the desktop app; weights stay opt-in. Gave up: leaving SheetSage as a disabled menu item with no install path.
- **Frozen jobs re-invoke `sys.executable` with the subcommand only** (`engine_argv`). `python -m copyist …` is for a checkout; the PyInstaller sidecar *is* Copyist, so `-m copyist` made every UI job die with `invalid choice: 'copyist'`.
- **Model downloads always land in `COPYIST_HOME/models`**, copying from `.cache/yue/` when present. SheetSage's `yue-transcribe` loads MERT from beside the head GGUF; treating a checkout MERT as "already installed" left the app folder with SheetSage alone and failed every run.
- **Transcription trims long lyrics to the notes heard** (`syllables_for_transcription`): drop spoken sections, then whole lines from the start until the fit's split budget. A full libretto against a shorter SheetSage draft used to abort with "written for different words"; the melody from the recording is the source of truth.
- **SheetSage Ins lead + short bars:** when Ins has more notes than Vocal, swap voices; allow mid-song 1/4–2/4 bars then `consolidate_meters` into the header meter. Otherwise the lead sheet was mostly empty rests (tune left on Ins).
- **Transcription check previews are piano-led** (`ballad` / `waltz` / `lullaby` by meter). The default full band buried the melody so you couldn't tell if the transcription was right; YuE2 stays the finished listen after Keep.

## 2026-10-18 (README and Pages: how to make music)

- **README and the Pages site lead with `copyist serve`, then write/build.** Quick start was only `copyist build`; newcomers never saw the local page, `--engine rules`, rewrite/refit or transcribe. The site gained a "Make some music" section. Gave up: keeping the install page as build-only.

## 2026-10-18 (chord chroma smoothing)

- **Accompaniment chroma is averaged with nearby beats that still match (cosine ≥ 0.55).** Blind ±2-beat means smeared real changes (synthetic C→F→G→C lost the last C). Edge-aware smoothing raised Saints take chords from 0.70 to 0.83 (Amazing Grace 0.75 → 0.78) without that smear. Bass chroma is not smoothed. Silent Night's take still scores ~0.41–0.49 because long stretches of the accompaniment read as Em against the written C/G7/F — a take/score mismatch, not only a detector bug.

## 2026-10-18 (6/8 double-tempo on takes)

- **When the beat tracker doubles a soft 6/8 pulse, rebuild eighths from the slow peak and read 6/8 only.** Silent Night's YuE2 take locked onto ~108 BPM (half of each dotted-quarter) and became a wrong 4/4; autocorrelation preferred ~54. Every other tracked beat, trisected, plus `compound_duple` meter choice fixes the lead sheet's meter and tempo. Gave up: keeping the slightly higher note F1 of the wrong 4/4 (0.78 vs 0.75) — the band preview has to feel like a lullaby.

## 2026-10-18 (lyric refit)

- **Refit keeps the melody and re-runs the write fitter.** `copyist refit` / the page's "Edit the lyrics" place new words under existing notes (splits allowed). Multi-verse hymn files become one fitted verse block when refit from plain text — same as `copyist write`. Gave up: editing each Amazing Grace verse independently without a syllable budget UI.

## 2026-10-18 (rule-based writer)

- **`copyist write --engine rules` is Copyist's own MIT melody writer**, and `--engine auto` falls back to it when `yue-plan` isn't installed. YuE2's planner stays the default when present (`plan`). Gave up: waiting on an open neural planner before anyone without YuE2 can write a song.
- **Rules melodies stay diatonic in the key.** An early version stepped by chromatic semitones, so Hope in E♭ mixed `_G`/`G` and `=e` against flat chords and sounded sharp and flat at once. Contour and motif now move by scale degree; strong beats are chord tones.

## 2026-10-18 (GitHub Pages site)

- **The public site lives in `site/` and deploys with GitHub Actions**, not the repo `docs/` folder. `docs/` stays project documentation (markdown for agents and contributors). The Pages site is a static advert: score-first pitch, features, install — same desk colours, staff motif and type as `copyist serve`, at `https://copyist.digitaldefiance.org/` (`site/CNAME`). **Type everywhere is Instrument Serif + Instrument Sans + Source Serif 4** (SIL OFL); Shantell Sans is gone (too handwritten). Gave up: a CDN-built framework; plain HTML/CSS/JS, no build step.

## 2026-10-18 (section rewrite)

- **Section rewrite swaps donors or raises a section; it does not ask the planner for a fragment.** `yue-plan` only writes whole songs, so `again` / `simpler` plan or reuse full candidates with the same key, meter and section length, then splice that section into the base. `higher` moves that section's notes and chords together (and the key when the section is the whole song); raising the tune alone against old chords sounded flat/out of tune. Output lives under `out/<slug>/rewrite/<how>/`.

## 2026-10-18 (write style line)

- **Planner style lines keep meter and tempo as their own tags.** Deduping phrases was dropping a trailing `3/4` when production already said "gentle 3/4 waltz", and yue-plan then wandered into 4/4 and 6/8. Steering tags (`N/D`, `N BPM`) are appended after dedupe. Ranking also prefers candidates whose meter the asked-for style actually plays (`meter_miss`).

## 2026-10-18 (celesta)

- **Music-box style uses Neil Bickford's A Sampled Celesta** (CC0 Mustel, via a 5 MB mono whole-tone subset in `Digital-Defiance/copyist-celesta`). The earlier VCSL glockenspiel stays in the `bells` pack as `musicbox` (comb music-box stand-in) until a real crank/comb set can be hosted — folkman's CC0 Freesound pack needs a login to download, so it isn't in the auto-downloader yet. Celesta covers C4–C8 at written pitch (no `PLAY_SHIFT`).

## 2026-10-18 (guitar staff)

- **Guitar is its own staff and style part**, not the piano hands played on guitar samples. Styles declare `instruments.guitar` and a `guitar:` figure (`chord` / `strum`, arps, thumb tones). Folk (nylon fingerpicking), country and country-waltz (steel boom-chick), pop/rock/power-ballad/blues (electric) use it; the piano staff is omitted when empty. Shapes sit above a separate bass part so the mix stays clear. Song `instruments:` may list `guitar` (default includes it; empty styles skip the part).

## 2026-10-18 (oboe)

- **Broadway ballad melody uses the VSCO oboe** (vibrato, CC0, ~24 MB, `winds` pack) over the harp. Flute stays on Broadway uptempo and march. Sparse whole-tone sampling (A♯/D/F) with stretch; take v1/v3 only (deterministic).

## 2026-10-18 (alto sax)

- **Swing, jazz waltz, blues-shuffle and bossa melodies use Karoryfer Weresax** (CC0 alto, ~50 MB of rr1 dynamic-mic samples, `winds` pack). Copyist writes a simple SFZ (no humanize LFOs, no round-robin) so previews stay deterministic. Upstream's full Sax.sfz stayed out.
- **Swing and jazz waltz drop piano shells under the sax.** Charleston comps in the same midrange as the alto made Saints sound discordant even though the sax was in tune; the preview is now sax + walking bass + ride. Blues keeps guitar under the sax. Wind leads also use the quieter accompaniment mix (same as piano-vocal).
- **Walking bass: chromatic approach only when the chord changes.** A half-step into the same root (C♯ under bars of C) is fine in bebop, but under a hymn melody it read as wrong notes. While a chord holds, beat 4 stays on a chord tone (3rd/5th/6th).

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

- **Neural melody candidate selection balances count distance with amplitude confidence** (2026-10-18): Rather than requiring a coarse hurdle (MIN_COUNT_IMPROVE >= 4) that prevented strict Basic Pitch presets from being chosen when `clean_notes` was already close to target count, the adaptive pipeline switches when a preset is closer to target without losing confidence (>= default - 0.02) or breaks ties on higher amplitude confidence (+0.01). Restores Saints to 0.85 and Amazing Grace to 0.89, reaching mean note F1 of 0.88 vs open 0.83.
- **Roundtrip lead-sheet benchmark with `--engine neural`** (2026-10-18): Added `--engine {open,neural}` to `scripts/transcribe/roundtrip.py`. On full drafted ABC scores, neural note F1 reaches 0.87 mean vs open 0.83 (Saints 0.91 vs 0.85, Tyger 0.93 vs 0.78, AG 0.89 vs 0.88, Major-General 0.84 tied).
- **Native arm64 nnls-chroma for Omnizart on Apple Silicon** (2026-10-18): Compiled `nnls-chroma.dylib` from source with Homebrew `vamp-plugin-sdk` and Boost; unblocks native Omnizart chord inference on Apple Silicon without x86 Rosetta translation errors.
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
- **Fonts are bundled** (Instrument Serif for brand/titles, Instrument Sans for controls, Source Serif 4 for reading; SIL OFL), so the page fetches nothing from the internet. Shantell Sans was dropped 2026-10-18.
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
