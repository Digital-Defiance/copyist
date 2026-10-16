# Copyist

**The song, the score, the sound.**

Copyist writes songs the way a working composer, copyist and band would: it starts from the notes, not from audio. Every song comes out as real, correct music: a lead sheet, a full score, a part for every player, MIDI and MusicXML, and a recording made from those same notes. Because the score is the source of truth, the sheet music always matches what you hear.

Tools like Suno and Mozart AI generate audio first. Their notes don't exist as data, so any sheet music has to be guessed back out of the recording. Copyist works the other way around.

## Status

Early. Milestone 0 works: a song file becomes a validated lead sheet, a band arrangement (voice, piano, bass, drums) with full score and parts, MIDI, and a demo recording. See [ROADMAP.md](ROADMAP.md).

## Quick start

```
pip install -e .
pip install --no-deps tinysoundfont      # for audio; skips an optional playback library
copyist build songs/amazing-grace.yaml
```

Outputs land in `out/<song>/`: the lead sheet and band score as PDF, every part, MusicXML, MIDI, a demo WAV and a validation report.

## Read next

- [SPEC.md](SPEC.md): what Copyist is, how it works, the song file format, the quality bar.
- [ROADMAP.md](ROADMAP.md): milestones and the next thing to do.
- [AGENTS.md](AGENTS.md): instructions for AI coding agents (and humans) picking up the work.
- [DECISIONS.md](DECISIONS.md): why things are the way they are.
