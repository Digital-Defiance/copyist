# Copyist, the desktop app

The Tauri 2 shell around Copyist (docs/desktop-app.md). It opens a window, starts the Copyist engine as a sidecar, waits for the engine's JSON start line, loads the engine's page, and stops the engine on quit. Links out of Copyist open in your browser, and only one copy runs at a time.

## Run it on a Mac (development)

Once, install the tools:

```
xcode-select --install                                           # Apple's command-line tools
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh   # Rust
```

Then, from this folder:

```
npm install        # Tauri's command-line tool (or: cargo install tauri-cli --version "^2")
npm run dev        # builds and opens Copyist
```

In development the engine runs from this checkout (`../.venv`, your songs, your `.cache/`), through `src-tauri/binaries/copyist-engine-<platform>`, a small script that stands in for the frozen engine. The first build compiles Tauri, which takes a few minutes.

## Layout

```
shell/             the start page ("Starting…", or why the engine stopped)
src-tauri/
  src/main.rs      the window, the engine sidecar, links, quitting
  tauri.conf.json  the app's name, identifier (org.digitaldefiance.copyist), icons, sidecar
  binaries/        the engine sidecar, one per platform (development scripts until step 3)
  icons/           generated from ../icon.png with `npx @tauri-apps/cli icon icon.png -o src-tauri/icons`
```

Step 3 (packaging) swaps the scripts in `binaries/` for a PyInstaller build of the engine, adds yue2.cpp's `yue-synth` and `yue-tokenize`, and signs and notarizes with the Developer ID.
