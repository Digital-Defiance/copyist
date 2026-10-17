# Copyist

**The song, the score, the sound.**

Copyist writes songs the way a working composer, copyist and band would: it starts from the notes, not from audio. Every song comes out as real, correct music: a lead sheet, a full score, a part for every player, MIDI and MusicXML, and a recording made from those same notes. Because the score is the source of truth, the sheet music always matches what you hear.

Tools like Suno and Mozart AI generate audio first. Their notes don't exist as data, so any sheet music has to be guessed back out of the recording. Copyist works the other way around.

## Status

Early. A song file becomes a validated lead sheet, a band arrangement (voice, piano, bass, drums) with full score and parts, MIDI, and a recording of the score played on sampled instruments (a concert grand, upright and electric basses, a drum kit, a clarinet on the melody), mixed and mastered, with a stem per part ([docs/sound-set.md](docs/sound-set.md)). The arrangement follows one of 23 styles, from waltz, hymn and lullaby to swing, bossa nova, reggae, disco and Broadway, and `copyist gallery` plays a song in every style that fits it, as a band preview or (with `--takes`) as finished YuE2 takes, so you can choose by ear ([docs/styles.md](docs/styles.md)). `copyist produce` has YuE2 perform the same score, band and singer together ([docs/production.md](docs/production.md)), and `copyist follow` checks that the take sings the written melody. A trained voice can be added with a LoRA ([docs/voice-lora.md](docs/voice-lora.md)). `copyist serve` puts it all in a browser ([docs/web.md](docs/web.md)). `copyist sing` (SoulX-Singer) sings the exact notes, for checking ([docs/singing.md](docs/singing.md)). See [ROADMAP.md](ROADMAP.md) and [TASKS.md](TASKS.md).

## Quick start

```
pip install -e .
pip install --no-deps tinysoundfont      # the fallback sound; skips an optional playback library
scripts/setup-sfizz.sh --instruments     # the sampled instruments' player, and the band (about 1.1 GB)
copyist build songs/amazing-grace.yaml
```

Outputs land in `out/<song>/`: the lead sheet and band score as PDF, every part, MusicXML, MIDI, the band recording and its stems, and a validation report. Without sfizz or the instruments, a SoundFont plays instead, and the report says so.

## Licence and contributing

Copyist is free and open source under the [MIT licence](LICENSE), stewarded by [Digital Defiance](https://github.com/Digital-Defiance), a nonprofit. Contributions are welcome, styles and instruments especially: see [CONTRIBUTING.md](CONTRIBUTING.md).

What Copyist downloads has its own terms:
- **YuE2, the singer:** CC BY-NC 4.0, with a permission for individual creators to sell their songs.
- **The sampled instruments:** CC0, CC BY 3.0 or CC BY-SA 3.0, with the credits owed shown in every song's report.
- **The page's fonts:** SIL Open Font License.

## Read next

- [SPEC.md](SPEC.md): what Copyist is, how it works, the song file format, the quality bar.
- [ROADMAP.md](ROADMAP.md): milestones and the next thing to do.
- [AGENTS.md](AGENTS.md): instructions for AI coding agents (and humans) picking up the work.
- [DECISIONS.md](DECISIONS.md): why things are the way they are.
