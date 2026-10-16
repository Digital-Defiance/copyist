# Decisions

Newest first. One entry per decision: what, why, and what we gave up.

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
