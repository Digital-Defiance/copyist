// Editing by ear: the song's notes as bars to click, hear and nudge. The server makes each change
// in the song file (copyist/edit.py); this page draws the notes and plays them with Web Audio.

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const PX_SEMITONE = 7;
const LINES = [43, 47, 50, 53, 57, 64, 67, 71, 74, 77];     // the bass and treble staff lines
const LENGTHS = { 4: "a whole note", 3: "a dotted half note", 2: "a half note", 1.5: "a dotted quarter note",
  1: "a quarter note", 0.75: "a dotted eighth note", 0.5: "an eighth note", 0.25: "a sixteenth note" };

let ed = null;        // { slug, view, sel, verse, busy }
let ctx = null;       // the AudioContext, made on the first click
let out = null;       // its output: a gentle compressor so chords don't clip
let nodes = [];       // what's sounding, to stop
let timers = [];      // highlight steps while playing

// ------------------------------------------------------------------ the page

export function editTab(song) {
  return `<div class="editor" id="editor" data-slug="${esc(song.slug)}">
    <div class="ed-bar" role="toolbar" aria-label="Listening">
      <button class="small" id="ed-play">Play from here</button>
      <label class="check"><input type="checkbox" id="ed-slow"> Slower</label>
      <label class="check"><input type="checkbox" id="ed-pad" checked> With the chords</label>
      <label class="ed-verse" hidden>Words <select id="ed-verse"></select></label>
      <span class="ed-spacer"></span>
      <button class="small" id="ed-undo" disabled>Undo</button>
      <button class="small" id="ed-redo" disabled>Redo</button>
    </div>
    <div class="ed-panel" id="ed-panel"></div>
    <p class="ed-msg status" id="ed-msg" role="status" aria-live="polite"></p>
    <div class="ed-bars" id="ed-bars"><p class="hint">Opening the notes…</p></div>
    <div class="ed-foot">
      <p class="hint">Each change is saved in the song file as you make it, and the song's checks run again.
        The score and the takes are made from the song file, so when it sounds right:</p>
      <button class="go" data-job="build">Write the score again</button>
      <div class="job" data-job-panel></div>
    </div>
  </div>`;
}

export async function wireEdit(song) {
  ed = { slug: song.slug, view: null, sel: null, verse: 0, busy: false };
  try {
    ed.view = await getJSON(`/api/edit/${encodeURIComponent(song.slug)}`);
  } catch (e) {
    $("#ed-bars").innerHTML = `<p class="status failed">This song can't be edited here: ${esc(e.message)}</p>`;
    return;
  }
  const first = events().find(({ e }) => e.kind === "note");
  ed.sel = first ? first.e.id : null;
  const verses = ed.view.verses;
  if (verses > 1) {
    $("#ed-verse").innerHTML = Array.from({ length: verses }, (_, i) => `<option value="${i}">Verse ${i + 1}</option>`).join("");
    $(".ed-verse").hidden = false;
    $("#ed-verse").addEventListener("change", () => { ed.verse = Number($("#ed-verse").value); draw(); });
  }
  $("#ed-play").addEventListener("click", () => (nodes.length ? stop() : playFrom(ed.sel)));
  $("#ed-undo").addEventListener("click", () => change("undo"));
  $("#ed-redo").addEventListener("click", () => change("redo"));
  $("#ed-bars").addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-id]");
    if (b) select(b.dataset.id, true);
  });
  $("#ed-panel").addEventListener("click", onPanel);
  draw();
}

function on() { return ed && $("#editor") && $("#editor").dataset.slug === ed.slug; }

async function getJSON(path) {
  const r = await fetch(path);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// Every note and rest with its time from the start of the song, in quarter notes.
function events() {
  const list = [];
  let t = 0;
  for (const bar of ed.view.bars) {
    for (const e of bar.events) list.push({ e, bar, t: t + e.start });
    t += bar.length;
  }
  return list;
}

function find(id) {
  const list = events();
  const i = list.findIndex(({ e }) => e.id === id);
  return { list, i, item: list[i] };
}

// ------------------------------------------------------------------ drawing

function draw() {
  if (!on()) return;
  const v = ed.view;
  const lo = v.low - 2, hi = v.high + 2;
  const shortest = Math.min(...v.bars.flatMap((b) => b.events.map((e) => e.length)));
  const pxq = Math.min(120, Math.max(52, 34 / shortest));
  const height = (hi - lo + 1) * PX_SEMITONE;
  const y = (m) => (hi - m) * PX_SEMITONE;
  let section = null;
  $("#ed-bars").innerHTML = v.bars.map((bar) => {
    const head = bar.section !== section ? `<span class="sec">${esc(sectionName(bar.section))}</span>` : "";
    section = bar.section;
    const chords = bar.events.filter((e) => e.chord).map((e) =>
      `<span style="left:${e.start * pxq}px">${esc(e.chord)}</span>`).join("");
    const lines = LINES.filter((m) => m > lo && m < hi).map((m) =>
      `<div class="ed-line" style="top:${y(m) + PX_SEMITONE / 2}px"></div>`).join("");
    const notes = bar.events.map((e) => {
      const sel = e.id === ed.sel ? " sel" : "";
      const left = e.start * pxq + 1, width = Math.max(6, e.length * pxq - 3);
      if (e.kind === "rest") {
        return `<button class="ed-rest${sel}" data-id="${e.id}" style="left:${left}px;width:${width}px;top:${height / 2 - 9}px"
          aria-label="Bar ${bar.number}, a rest"></button>`;
      }
      const cls = (e.held_over ? " held" : "") + (e.tie ? " tie" : "");
      return `<button class="ed-note${cls}${sel}" data-id="${e.id}" style="left:${left}px;width:${width}px;top:${y(e.midi)}px;height:${PX_SEMITONE + 1}px"
        aria-label="${esc(label(bar, e))}" ${sel ? 'aria-current="true"' : ""}></button>`;
    }).join("");
    const words = bar.events.filter((e) => e.kind === "note" && e.words && e.words.length).map((e) => {
      const w = e.words[ed.verse] ?? "";
      const shown = w === "_" ? "–" : w === "*" ? "" : w;
      return shown ? `<span class="${w === "_" ? "hold" : ""}" style="left:${e.start * pxq}px">${esc(shown)}</span>` : "";
    }).join("");
    return `<div class="ed-measure" style="width:${bar.length * pxq}px">
      <div class="ed-head"><span class="n">${bar.number}</span>${head}</div>
      <div class="ed-chords">${chords}</div>
      <div class="ed-roll" style="height:${height}px">${lines}${notes}</div>
      <div class="ed-words">${words}</div>
    </div>`;
  }).join("");
  $("#ed-undo").disabled = !v.can_undo || ed.busy;
  $("#ed-redo").disabled = !v.can_redo || ed.busy;
  panel();
}

function label(bar, e) {
  const w = e.words && e.words.length ? e.words[ed.verse] : "";
  const sung = e.held_over ? ", held from the note before" : w === "_" ? ", holding the word before" : w && w !== "*" ? `, “${w.replace(/-$/, "")}”` : "";
  return `Bar ${bar.number}, ${e.name}${sung}`;
}

function sectionName(s) {
  if (s === "prechorus") return "Pre-chorus";
  return s ? s[0].toUpperCase() + s.slice(1) : "";
}

function lengthName(q) {
  return LENGTHS[q] || `${q} beats`;
}

function panel() {
  const box = $("#ed-panel");
  const { item } = find(ed.sel);
  if (!item) {
    box.innerHTML = `<p class="hint">Click a note to hear it and change it.</p>`;
    return;
  }
  const { e, bar } = item;
  const busy = ed.busy ? "disabled" : "";
  const words = (e.words || []).map((w, i) => {
    const said = w === "_" ? "holds the word before" : w === "*" ? "no word" : w ? `“${esc(w.replace(/-$/, ""))}”` : "past the end";
    return e.words.length > 1 ? `verse ${i + 1}: ${said}` : said;
  }).join("; ");
  const what = e.kind === "rest"
    ? `<b>A rest</b> · bar ${bar.number} · ${lengthName(e.length)}`
    : `<b>${esc(e.name)}</b> · bar ${bar.number} · ${lengthName(e.length)}${e.held_over ? " · held over from the note before" : ""}${words ? ` · ${words}` : ""}`;
  const pitch = e.kind === "note" ? `
    <div class="ed-group" role="group" aria-label="Pitch">
      <span class="label">Pitch</span>
      <button class="small" data-op="up" ${busy} title="Up arrow">Higher</button>
      <button class="small" data-op="down" ${busy} title="Down arrow">Lower</button>
      <button class="small" data-op="up-half" ${busy} title="Shift + up arrow">Half step up</button>
      <button class="small" data-op="down-half" ${busy} title="Shift + down arrow">Half step down</button>
      <button class="small" data-hear="note">Hear it</button>
    </div>` : "";
  const length = `
    <div class="ed-group" role="group" aria-label="Length">
      <span class="label">Length</span>
      <button class="small" data-op="longer" ${busy}>Longer</button>
      <button class="small" data-op="shorter" ${busy}>Shorter</button>
      ${e.kind === "note" ? `<button class="small" data-op="split" ${busy}>Split in two</button>
      <button class="small" data-op="join" ${busy}>Join with the next</button>` : ""}
      <button class="small" data-hear="bar">Hear the bar</button>
    </div>`;
  const chord = `
    <div class="ed-group" role="group" aria-label="Chord">
      <span class="label">Chord</span>
      <span class="ed-chord">${e.sounding ? esc(e.sounding) : "none"}</span>
      <button class="small" data-chords ${busy}>Try other chords here</button>
      ${e.chord ? `<button class="small" data-op="chord" data-value="" ${busy}>No chord change here</button>` : ""}
    </div>
    <div id="ed-options"></div>`;
  box.innerHTML = `<p class="ed-what">${what}</p>${pitch}${length}${chord}`;
}

function select(id, hear) {
  stop();
  ed.sel = id;
  draw();
  const b = $(`#ed-bars [data-id="${id}"]`);
  if (b) { b.focus({ preventScroll: true }); b.scrollIntoView({ block: "nearest", inline: "nearest" }); }
  if (hear) playNote(id);
}

// ------------------------------------------------------------------ changing

async function onPanel(ev) {
  const b = ev.target.closest("button");
  if (!b) return;
  if (b.dataset.op) return change(b.dataset.op, b.dataset.value);
  if (b.dataset.hear === "note") return playNote(ed.sel);
  if (b.dataset.hear === "bar") return playBar(ed.sel);
  if (b.dataset.chords !== undefined) return chordOptions();
  if (b.dataset.tryChord !== undefined) return playSpan(ed.sel, JSON.parse(b.dataset.tones));
  if (b.dataset.useChord !== undefined) return change("chord", b.dataset.useChord);
}

async function change(op, value) {
  if (ed.busy || (!ed.sel && op !== "undo" && op !== "redo")) return;
  stop();
  ed.busy = true;
  draw();
  try {
    const r = await fetch("/api/edit", {
      method: "POST", headers: { "Content-Type": "application/json", "X-Copyist": "1" },
      body: JSON.stringify({ song: ed.slug, op, at: ed.sel, value }),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.error || r.statusText);
    ed.view = data.view;
    if (data.at) ed.sel = data.at;
    if (!find(ed.sel).item) ed.sel = events()[0]?.e.id ?? null;
    say(sentence(op, data.changed));
    ed.busy = false;
    draw();
    const b = $(`#ed-bars [data-id="${ed.sel}"]`);
    if (b) b.focus({ preventScroll: true });
    if (op.startsWith("up") || op.startsWith("down")) playAround(ed.sel);
    else if (op === "chord") playSpan(ed.sel);
    else playBar(ed.sel);
  } catch (e) {
    ed.busy = false;
    draw();
    say(e.message, true);
  }
}

function sentence(op, changed) {
  if (op === "undo") return "Undone.";
  if (op === "redo") return "Done again.";
  if (op === "chord") return changed === "chord taken out" ? "The chord before carries on here now." : `Now ${changed.replace("chord ", "")} here.`;
  return { longer: "Longer: the next note starts later.", shorter: "Shorter: what follows starts sooner.",
    split: "Split in two. The second note holds the same word.", join: "Joined into one held note." }[op] || changed + ".";
}

function say(text, failed = false) {
  const m = $("#ed-msg");
  if (!m) return;
  m.textContent = text;
  m.classList.toggle("failed", failed);
}

async function chordOptions() {
  const box = $("#ed-options");
  box.innerHTML = `<p class="hint">Finding chords that fit…</p>`;
  try {
    const { options } = await getJSON(`/api/edit/${encodeURIComponent(ed.slug)}/chords?at=${encodeURIComponent(ed.sel)}`);
    box.innerHTML = `<p class="hint">How much of the tune from here to the next chord change each chord holds.
        Play one to hear the tune over it.</p>
      <ul class="ed-options">${options.map((o) => `<li>
        <span class="sym">${esc(o.symbol)}</span>
        <span class="fit">${Math.round(o.fit * 100)}%${o.now ? " · now" : ""}</span>
        <button class="small" data-try-chord data-tones="${esc(JSON.stringify(o.tones))}" aria-label="Play ${esc(o.symbol)}">Play</button>
        ${o.now ? "" : `<button class="small" data-use-chord="${esc(o.symbol)}" aria-label="Use ${esc(o.symbol)}">Use</button>`}
      </li>`).join("")}</ul>`;
  } catch (e) {
    box.innerHTML = `<p class="status failed">${esc(e.message)}</p>`;
  }
}

// ------------------------------------------------------------------ sound

function audio() {
  if (!ctx) {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    out = ctx.createDynamicsCompressor();
    out.connect(ctx.destination);
  }
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

const hz = (m) => 440 * 2 ** ((m - 69) / 12);

// A soft, piano-like note: a quick strike that fades, partials an octave and a twelfth up.
function tone(m, t0, dur, level = 0.2) {
  const c = audio();
  const g = c.createGain();
  g.connect(out);
  const end = t0 + Math.max(0.08, dur);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(level, t0 + 0.01);
  g.gain.setTargetAtTime(level * 0.3, t0 + 0.01, 0.4);
  g.gain.setTargetAtTime(0, end - 0.03, 0.06);
  for (const [mult, amp, type] of [[1, 1, "triangle"], [2, 0.22, "sine"], [3, 0.06, "sine"]]) {
    const o = c.createOscillator();
    o.type = type;
    o.frequency.value = hz(m) * mult;
    const og = c.createGain();
    og.gain.value = amp;
    o.connect(og);
    og.connect(g);
    o.start(t0);
    o.stop(end + 0.4);
    nodes.push(o);
  }
}

// A quiet held chord under the tune.
function pad(tones, t0, dur) {
  if (!tones || !tones.length || !$("#ed-pad")?.checked) return;
  const c = audio();
  const f = c.createBiquadFilter();
  f.type = "lowpass";
  f.frequency.value = 1100;
  const g = c.createGain();
  f.connect(g);
  g.connect(out);
  g.gain.setValueAtTime(0, t0);
  g.gain.linearRampToValueAtTime(0.045, t0 + 0.12);
  g.gain.setTargetAtTime(0, t0 + Math.max(0.15, dur - 0.08), 0.1);
  for (const m of tones) {
    for (const detune of [-7, 7]) {
      const o = c.createOscillator();
      o.type = "sawtooth";
      o.frequency.value = hz(m);
      o.detune.value = detune;
      o.connect(f);
      o.start(t0);
      o.stop(t0 + dur + 0.6);
      nodes.push(o);
    }
  }
}

function stop() {
  for (const o of nodes) { try { o.stop(); } catch { /* already stopped */ } }
  nodes = [];
  for (const t of timers) clearTimeout(t);
  timers = [];
  for (const b of document.querySelectorAll(".ed-note.now")) b.classList.remove("now");
  const p = $("#ed-play");
  if (p) p.textContent = "Play from here";
}

// Play events [i0, i1) of the song. Tied notes sound as one; the chords follow the song unless
// `tones` replaces them (to try a chord).
function play(i0, i1, tones = null) {
  stop();
  const list = events();
  if (i0 < 0 || i0 >= list.length) return;
  i1 = Math.min(i1, list.length);
  const c = audio();
  const spq = 60 / ed.view.qpm / ($("#ed-slow")?.checked ? 0.7 : 1);
  const start = c.currentTime + 0.05, base = list[i0].t;
  const at = (t) => start + (t - base) * spq;
  let chord = null, chordAt = base;
  const flush = (until) => { if (chord) pad(chord, at(chordAt), (until - chordAt) * spq); };
  for (let i = i0; i < i1; i++) {
    const { e, t } = list[i];
    const want = tones || e.chord_tones;
    if (i === i0 || (!tones && e.chord)) { flush(t); chord = want; chordAt = t; }
    if (e.kind === "note" && (!e.held_over || i === i0)) {
      let dur = e.length, j = i;
      while (list[j].e.tie && j + 1 < list.length) { j++; dur += list[j].e.length; }
      tone(e.midi, at(t), dur * spq * 0.97);
    }
    timers.push(setTimeout(() => {
      for (const b of document.querySelectorAll(".ed-note.now")) b.classList.remove("now");
      const b = $(`#ed-bars [data-id="${e.id}"]`);
      if (b && e.kind === "note") b.classList.add("now");
    }, (at(t) - c.currentTime) * 1000));
  }
  const last = list[i1 - 1];
  const end = last.t + last.e.length;
  flush(end);
  timers.push(setTimeout(stop, (at(end) - c.currentTime) * 1000 + 300));
  const p = $("#ed-play");
  if (p) p.textContent = "Stop";
}

function playNote(id) {
  const { list, i } = find(id);
  if (i < 0) return;
  let j = i + 1;
  while (j < list.length && list[j - 1].e.tie) j++;
  play(i, j);
}

function playAround(id) {          // the note before, this one, the one after
  const { list, i } = find(id);
  if (i < 0) return;
  let a = i - 1;
  while (a > 0 && list[a].e.held_over) a--;
  let b = i + 1;
  while (b < list.length && list[b - 1].e.tie) b++;
  play(Math.max(0, a), Math.min(list.length, b + 1));
}

function playBar(id) {
  const { list, item } = find(id);
  if (!item) return;
  const i0 = list.findIndex((x) => x.bar === item.bar);
  let i1 = i0;
  while (i1 < list.length && list[i1].bar === item.bar) i1++;
  play(i0, i1);
}

function playFrom(id) {
  const { list, i } = find(id);
  play(Math.max(0, i), list.length);
}

function playSpan(id, tones = null) {   // from here to the next chord change, at most two bars
  const { list, i } = find(id);
  if (i < 0) return;
  let j = i + 1;
  while (j < list.length && !list[j].e.chord && list[j].t - list[i].t < 2 * ed.view.bar_quarters) j++;
  play(i, j, tones);
}

// ------------------------------------------------------------------ keys

document.addEventListener("keydown", (ev) => {
  if (!on() || ev.altKey || ev.target.closest("select, input, textarea")) return;
  if (ev.target !== document.body && !ev.target.closest("#editor")) return;    // the drawer keeps its keys
  const mod = ev.metaKey || ev.ctrlKey;
  if (mod && ev.key.toLowerCase() === "z") {
    ev.preventDefault();
    change(ev.shiftKey ? "redo" : "undo");
    return;
  }
  if (mod) return;
  const { list, i } = find(ed.sel);
  if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
    const j = i + (ev.key === "ArrowRight" ? 1 : -1);
    if (j >= 0 && j < list.length) select(list[j].e.id, true);
  } else if (ev.key === "ArrowUp" || ev.key === "ArrowDown") {
    const up = ev.key === "ArrowUp";
    change(ev.shiftKey ? (up ? "up-half" : "down-half") : (up ? "up" : "down"));
  } else if (ev.key === " " && ev.target.closest("#editor")) {
    nodes.length ? stop() : playFrom(ed.sel);
  } else {
    return;
  }
  ev.preventDefault();
});

window.addEventListener("hashchange", stop);
