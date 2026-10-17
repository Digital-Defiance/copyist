# Copyist in a browser

```
copyist serve
```

Run it from the Copyist folder, or give it a library folder with `--root` (it creates `songs/` and `out/` there; `--demo` adds a demo song to an empty one). It opens http://127.0.0.1:8765/ (`--port` changes the port, `--no-open` skips opening a browser window), and Ctrl-C stops it. `--machine` prints one JSON line with the URL first, for the desktop app (docs/desktop-app.md).

If the singer (YuE2's model files) isn't installed, the sound tab offers to download it: it shows the licence, asks you to accept it, and shows progress.

What's there:

- **Songs**: every song in `songs/`.
- **The song**: the lyrics, and the validators' checks.
- **The score**: the lead sheet, full score and parts, shown as pages. "Write the score" runs `copyist build`.
- **The sound**: every take, with a player, and the form that makes a new one. Pick a trained voice, adjust its strength, the verses and the seed, edit the style, and press "Make the take". That runs `copyist produce --take …`, so each take keeps its own folder in `out/<song>/takes/`. "Check the melody" separates the vocal with Demucs and runs `copyist follow` on it. Older experiments (SoulX vocals, the SoundFont preview) are listed under "Earlier tests".
- **Voice training**: the progress of any run of `scripts/yue-lora/run.sh`: the step, the time left, the losses, and the checkpoints ready to try. "Ready to try" opens the sound tab with that voice chosen and its trigger line in the style.

How it works: `copyist/web/server.py` is Python's own HTTP server. It reads `songs/`, `out/` and `.cache/lora/`, and runs one `copyist` command at a time (the GPU can only do one), keeping each command's output in `out/.jobs/`. The page is plain HTML, CSS and JavaScript in `copyist/web/static/`, with no build step. Fonts (Shantell Sans and Source Serif 4, SIL Open Font License) are bundled, so it never fetches anything from the internet.

Safety: it listens on 127.0.0.1 only, serves files from `out/` only, answers only requests addressed to 127.0.0.1 or localhost, and starts jobs only for requests from its own page (a custom header plus an origin check). Other websites can't reach it or start anything.

Not there yet: writing a new song (it needs melody proposals, milestone M2), comparing two takes side by side, and running on a server for other people.
