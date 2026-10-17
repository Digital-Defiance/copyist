# Contributing to Copyist

Copyist writes songs the way a composer, copyist and band would: from the notes. Every song comes out as a correct lead sheet, score and parts, plus a recording made from those same notes. Copyist is free and open source under the MIT licence, and it's for everyone's music. Help is welcome.

By sending a contribution, you agree it's released under the MIT licence ([LICENSE](LICENSE)).

## Ways to help

- **Styles.** A style is one YAML file in `copyist/styles/` ([docs/styles.md](docs/styles.md)), so this is the easiest place to start. Copy a style close to the one you want, change what each part plays, and listen to it with `copyist gallery songs/when-the-saints.yaml --styles your-style`. Tango, polka, bluegrass and salsa are all still missing.
- **Instruments.** Sampled instruments come from libraries anyone may use for any music: CC0, CC BY, or CC BY-SA where music made with them can be sold ([docs/sound-set.md](docs/sound-set.md)). We especially need a music box, a celesta, acoustic guitars, a banjo, a mandolin, a pedal steel, an accordion and snare brushes. A library with a clear licence is a contribution in itself.
- **Test songs.** These must be in the public domain (published in the US before 1929) or written for Copyist. Never add copyrighted lyrics or melodies.
- **Bugs.** A wrong note, a collision on the page, a sound that's off. Attach the song file if you can.
- **Code.** Take an unchecked item from [ROADMAP.md](ROADMAP.md) or [TASKS.md](TASKS.md), or something you need.

## Setting up

You need Python 3.10 or later.

```
python -m venv .venv && . .venv/bin/activate
pip install -e .
python -m unittest discover -s tests          # the tests
copyist build songs/amazing-grace.yaml        # a song, end to end
```

Optional extras:
- `pip install --no-deps tinysoundfont`: the fallback sound.
- `scripts/setup-sfizz.sh --instruments`: the sampled band.
- `scripts/setup-yue.sh`: YuE2, the singer, which needs a capable GPU.
- `pip install -e ".[sing]"`: the pitch and lyric checks.

## The rules

These are the rules from [AGENTS.md](AGENTS.md), which also covers the code layout.

- **The score is the source of truth.** Audio is made from the notes. Never derive notes from audio, except to check a recording.
- **Builds are deterministic.** The same song and seed give the same files.
- **Every validator and every style has tests.** Validators include an input that should fail.
- **Look at and listen to what you change.** Render the PDF pages and check them; listen to the audio.
- **Keep the docs current.** If you change what SPEC.md describes, change SPEC.md in the same commit.
- **Small commits,** with messages that say what changed and why.

## Assets and licences

- **Never commit** model weights, sample libraries, voice recordings or trained voices (LoRAs). They download from their own sources, pinned and checked: `copyist/models.py` and `copyist/instruments.py`.
- **A voice Copyist ships must come from a person who consented.** It must never come from another AI generator's output.
- **Copyist's code is MIT; some models aren't.** YuE2's weights are CC BY-NC 4.0, with a permission for individual creators to sell their songs. The Copyist page shows each model's licence before it downloads.

## Conduct

Be kind and assume good faith. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
