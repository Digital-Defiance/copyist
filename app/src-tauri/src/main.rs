//! Copyist's desktop shell (docs/desktop-app.md).
//!
//! A window around the page the Copyist engine serves. The engine runs as a
//! sidecar: this program starts it, waits for the JSON line that says where
//! it's listening, shows that page, and stops the engine on quit. The page
//! gets no access to Tauri; it only talks to the engine.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::path::PathBuf;
use std::sync::Mutex;

use serde::Deserialize;
use tauri::{AppHandle, Manager, RunEvent, Url, WebviewUrl, WebviewWindow, WebviewWindowBuilder};
use tauri_plugin_opener::OpenerExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

/// The engine's first line on stdout (`copyist serve --machine`).
#[derive(Deserialize)]
struct Ready {
    copyist: String,
    url: String,
}

/// The running engine, so quitting can stop it.
struct Engine(Mutex<Option<CommandChild>>);

/// Pages the window may show itself: its own start page and the engine on this computer.
fn is_local(url: &Url) -> bool {
    matches!(url.scheme(), "tauri" | "asset")
        || matches!(url.host_str(), Some("127.0.0.1") | Some("localhost") | Some("tauri.localhost"))
}

fn main() {
    tauri::Builder::default()
        // One Copyist at a time: two engines on one library would trip over each other.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            app.manage(Engine(Mutex::new(None)));
            let opener = app.handle().clone();
            let window = WebviewWindowBuilder::new(app, "main", WebviewUrl::App("index.html".into()))
                .title("Copyist")
                .inner_size(1280.0, 860.0)
                .min_inner_size(720.0, 520.0)
                .on_navigation(move |url| {
                    if is_local(url) {
                        return true;
                    }
                    // Links out of Copyist (the licence, for one) open in the person's browser.
                    let _ = opener.opener().open_url(url.as_str(), None::<&str>);
                    false
                })
                .build()?;
            start_engine(app.handle(), window)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Copyist couldn't start")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                if let Some(child) = app.state::<Engine>().0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        });
}

/// Where the songs live, and what the engine needs to know about this machine.
fn library_and_env(app: &AppHandle) -> Result<(PathBuf, PathBuf, Vec<(String, String)>), Box<dyn std::error::Error>> {
    let data = app.path().app_data_dir()?;
    std::fs::create_dir_all(&data)?;
    let mut env = vec![
        ("COPYIST_HOME".to_string(), data.to_string_lossy().into_owned()),
        ("COPYIST_DESKTOP".to_string(), "1".to_string()),
    ];
    if cfg!(debug_assertions) {
        // Development: the engine runs from this checkout, on its own songs and .cache/.
        let repo = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize()?;
        env.push(("COPYIST_REPO".to_string(), repo.to_string_lossy().into_owned()));
        Ok((repo.clone(), repo, env))
    } else {
        // The app: songs in ~/Music/Copyist; yue-synth and friends beside this program.
        let music = app.path().audio_dir().or_else(|_| app.path().home_dir().map(|h| h.join("Music")))?;
        let library = music.join("Copyist");
        std::fs::create_dir_all(&library)?;
        if let Some(bin) = std::env::current_exe()?.parent() {
            env.push(("COPYIST_BIN".to_string(), bin.to_string_lossy().into_owned()));
        }
        Ok((library.clone(), library, env))
    }
}

fn start_engine(app: &AppHandle, window: WebviewWindow) -> Result<(), Box<dyn std::error::Error>> {
    let (library, workdir, env) = library_and_env(app)?;
    let root = library.to_string_lossy().into_owned();
    let mut cmd = app
        .shell()
        .sidecar("copyist-engine")?
        .current_dir(workdir)
        .args(["serve", "--root", root.as_str(), "--port", "0", "--machine", "--demo"]);
    for (k, v) in env {
        cmd = cmd.env(k, v);
    }
    let (mut events, child) = cmd.spawn()?;
    *app.state::<Engine>().0.lock().unwrap() = Some(child);
    let start = window.url()?;

    tauri::async_runtime::spawn(async move {
        let mut ready = false;
        let mut said: Vec<String> = Vec::new(); // the engine's last words, if it stops
        while let Some(event) = events.recv().await {
            match event {
                CommandEvent::Stdout(line) if !ready => {
                    let text = String::from_utf8_lossy(&line);
                    if let Ok(r) = serde_json::from_str::<Ready>(text.trim()) {
                        if r.copyist == "ready" {
                            if let Ok(url) = Url::parse(&r.url) {
                                ready = true;
                                let _ = window.navigate(url);
                            }
                        }
                    }
                }
                CommandEvent::Stderr(line) => {
                    said.push(String::from_utf8_lossy(&line).trim_end().to_string());
                    if said.len() > 40 {
                        said.remove(0);
                    }
                }
                CommandEvent::Terminated(status) => {
                    // Back to the start page, which explains what happened.
                    let mut url = start.clone();
                    url.query_pairs_mut()
                        .append_pair("stopped", &status.code.map(|c| c.to_string()).unwrap_or_default())
                        .append_pair("detail", &said.join("\n"));
                    let _ = window.navigate(url);
                    break;
                }
                _ => {}
            }
        }
    });
    Ok(())
}
