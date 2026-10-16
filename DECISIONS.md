# Decisions

Newest first. One entry per decision: what, why, and what we gave up.

## 2026-10-16

- **Name: Copyist. Tagline: "the song, the score, the sound."** A copyist turns a composer's sketch into correct parts for every player; the tagline covers the rest (writing and recording). Considered Tutti, Broadside, BrightScore, Tin Pan. Using any real person's name (e.g. Sondheim) was ruled out.
- **Score-first architecture.** The canonical score is the source of truth and audio is rendered from it. Gave up: the fastest path to Suno-like audio quality. Gained: correct MIDI and sheet music by construction.
- **Song files are YAML with the melody in ABC.** ABC is compact, human-writable, and what symbolic models (e.g. MuPT) are trained on. music21 parses it, including chord symbols and ties. Lyrics use ABC `w:` syntax but Copyist aligns them itself, so the rules are explicit and testable.
- **music21 as the internal model.** Mature, handles MusicXML and MIDI both ways, and has the theory tools validators need.
- **Verovio for engraving, PyMuPDF for PDF.** Both install with pip on macOS and Linux with no system packages. LilyPond engraves more beautifully but needs a separate install; it can be added as an optional engraver later.
- **TinySoundFont + GeneralUser GS for demo audio.** pip-installable (install with `--no-deps`, since its optional playback dependency, PyAudio, needs PortAudio) and a free SoundFont. Sounds like a demo, which is the M0 goal.
- **Validators are deterministic and block "finished."** They are the quality gate for both people and models.
