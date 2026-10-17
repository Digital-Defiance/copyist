// Copyist in a browser. Plain modules, no build step; the server is copyist/web/server.py.

const $ = (sel, root = document) => root.querySelector(sel);
const page = $("#page");
let songs = [];
let voices = [];
let current = null;          // the song on screen
let watching = null;         // the job being watched
let pendingVoice = null;     // a voice picked from the training drawer
let training = [];           // runs from /api/training
let models = null;           // /api/models: what's downloaded
const TABS = [["song", "The song"], ["score", "The score"], ["sound", "The sound"]];

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fileUrl = (path) => "/files/" + path.split("/").map(encodeURIComponent).join("/");

async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
  return r.json();
}

async function post(body) {
  const r = await fetch("/api/jobs", {
    method: "POST", headers: { "Content-Type": "application/json", "X-Copyist": "1" }, body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

// ------------------------------------------------------------------ words

function keyName(key) {
  if (!key) return null;
  const m = String(key).match(/^([A-G][#b]?)(m|min|minor)?$/);
  if (!m) return String(key);
  return `${m[1].replace("#", "♯").replace("b", "♭")} ${m[2] ? "minor" : "major"}`;
}

function facts(song) {
  const bits = [keyName(song.key), song.meter, song.tempo ? `${song.tempo} beats a minute` : null].filter(Boolean);
  const credits = Object.entries(song.credits || {}).map(([k, v]) => `${k[0].toUpperCase()}${k.slice(1)}: ${v}`);
  return [bits.join(", ") + (bits.length ? "." : ""), ...credits.map((c) => c + ".")].join(" ");
}

// Copyist lyrics mark syllables (-), held notes (_) and skips (*). Show them as plain words.
function plainLyrics(text) {
  const words = String(text).replace(/\*/g, "").replace(/_/g, "").replace(/-\s*/g, "").replace(/\s+/g, " ").trim();
  return words.split(/(?<=[.!?;])\s+/);
}

function when(iso) {
  const d = new Date(iso);
  return d.toLocaleString(undefined, { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
}

// ------------------------------------------------------------------ layout

function renderSongList() {
  $("#song-list").innerHTML = songs.length
    ? songs.map((s) => `<li><a href="#/song/${encodeURIComponent(s.slug)}/song" data-slug="${esc(s.slug)}">${esc(s.title)}</a></li>`).join("")
    : `<li class="hint">No songs yet. Song files go in the songs folder.</li>`;
}

function markCurrent(slug) {
  for (const a of document.querySelectorAll(".song-list a")) {
    if (a.dataset.slug === slug) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}

function header(song, tab) {
  return `
    <div class="staff-title"><h1>${esc(song.title)}</h1></div>
    <p class="facts">${esc(facts(song))}</p>
    <nav class="tabs" aria-label="${esc(song.title)}">
      ${TABS.map(([id, label]) => `<a href="#/song/${encodeURIComponent(song.slug)}/${id}" ${id === tab ? 'aria-current="page"' : ""}>${label}</a>`).join("")}
    </nav>`;
}

async function route() {
  const m = location.hash.match(/^#\/song\/([^/]+)\/(song|score|sound)$/);
  if (!m) {
    if (songs.length) location.replace(`#/song/${encodeURIComponent(songs[0].slug)}/song`);
    else page.innerHTML = `<div class="empty"><h1>Copyist</h1><p>Add a song file to the songs folder to begin.</p></div>`;
    return;
  }
  const slug = decodeURIComponent(m[1]);
  const tab = m[2];
  markCurrent(slug);
  try {
    current = await api(`/api/songs/${encodeURIComponent(slug)}`);
  } catch (e) {
    page.innerHTML = `<div class="empty"><p>Couldn't open that song: ${esc(e.message)}</p></div>`;
    return;
  }
  const body = tab === "song" ? songTab(current) : tab === "score" ? scoreTab(current) : soundTab(current);
  page.innerHTML = header(current, tab) + body;
  if (tab === "score") wireScore(current);
  if (tab === "sound") wireSound(current);
  wireJobButtons(current);
  if (watching) showJob(watching);
}

// ---------------------------------------------------------------- the song

function songTab(song) {
  const verses = song.verses.map((v, i) => `
    <div class="verse"><span class="n">Verse ${i + 1}</span>
      ${plainLyrics(v).map((line) => `<p>${esc(line)}</p>`).join("")}</div>`).join("");
  const report = song.report;
  const checks = report
    ? `<p class="verdict">${esc(report.verdict || "")}</p>
       <ul class="checks">${report.checks.map((c) => `
         <li><span class="mark ${c.result === "pass" ? "pass" : c.result === "fail" ? "fail" : "warn"}" aria-label="${esc(c.result)}">${c.result === "pass" ? "✓" : c.result === "fail" ? "✗" : "?"}</span>
         <span><b>${esc(c.check)}</b>: ${esc(c.details)}${c.where ? ` (${esc(c.where)})` : ""}</span></li>`).join("")}</ul>`
    : `<p class="hint">Not checked yet.</p><p><button data-job="build">Write the score</button></p>`;
  return `<div class="song-tab">
      <section><h2>Lyrics</h2><div class="verses" style="margin-top:.75rem">${verses || '<p class="hint">No lyrics.</p>'}</div></section>
      <aside><h2>Checks</h2>${checks}<div class="job" data-job-panel></div></aside>
    </div>`;
}

// --------------------------------------------------------------- the score

function scoreTab(song) {
  if (!song.sheets.length) {
    return `<div class="empty"><p>The score hasn't been written out yet.</p>
      <button class="go" data-job="build">Write the score</button><div class="job" data-job-panel></div></div>`;
  }
  return `<div class="sheet-picker" role="group" aria-label="Which sheet">
      ${song.sheets.map((s, i) => `<button class="small" data-sheet="${esc(s.path)}" aria-pressed="${i === 0}">${esc(s.label)}</button>`).join("")}
      <a class="button small" id="sheet-download" href="${fileUrl(song.sheets[0].path)}" download>Download</a>
      <button class="small" data-job="build">Write the score again</button>
    </div>
    <div class="job" data-job-panel></div>
    <div class="sheets" id="sheet" aria-live="polite"></div>`;
}

async function showSheet(path, label) {
  const box = $("#sheet");
  box.innerHTML = `<p class="hint">Opening the ${esc(label.toLowerCase())}…</p>`;
  try {
    const { pages } = await api(`/api/pages?file=${encodeURIComponent(path)}`);
    box.innerHTML = pages.map((p, i) =>
      `<img class="sheet-page" src="${fileUrl(p)}" alt="${esc(label)}, page ${i + 1} of ${pages.length}">`).join("");
  } catch (e) {
    box.innerHTML = `<p class="status failed">Couldn't open the ${esc(label.toLowerCase())}: ${esc(e.message)}</p>`;
  }
}

function wireScore(song) {
  for (const b of document.querySelectorAll("[data-sheet]")) {
    b.addEventListener("click", () => {
      for (const o of document.querySelectorAll("[data-sheet]")) o.setAttribute("aria-pressed", String(o === b));
      $("#sheet-download").href = fileUrl(b.dataset.sheet);
      showSheet(b.dataset.sheet, b.textContent);
    });
  }
  if (song.sheets.length) showSheet(song.sheets[0].path, song.sheets[0].label);
}

// --------------------------------------------------------------- the sound

function voiceName(file) {
  const v = voices.find((x) => x.id.endsWith("/" + file));
  return v ? v.label : file.replace(/\.safetensors$/, "");
}

function singerReady() {
  return !models || models.groups.some((g) => g.id === "singer" && g.ready);
}

function installPanel() {
  const g = models.groups.find((x) => x.id === "singer");
  const gb = (n) => (n / 1e9).toFixed(1);
  return `
    <section class="make">
      <h2>Install the singer</h2>
      <p>Copyist sings with YuE2, an open model that runs on this computer, not online. It's a one-time download of
        ${gb(g.size)} GB${g.have ? `, and ${gb(g.have)} GB of it is already here` : ""}.</p>
      <p class="hint">${esc(models.licence)} <a href="${esc(models.licence_url)}" target="_blank" rel="noopener">Read the licence</a>.</p>
      <p><label class="check"><input type="checkbox" id="accept"> I accept the licence</label></p>
      <div class="actions"><button class="go" id="install" disabled>Download the singer</button>
        <span class="hint">It goes into ${esc(models.folder)}.</span></div>
      <div class="job" data-job-panel></div>
    </section>`;
}

function soundTab(song) {
  const takes = song.recordings.filter((r) => r.kind === "take");
  const tests = song.recordings.filter((r) => r.kind !== "take");
  const verseOptions = song.verses.map((_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("");
  const voiceOptions = [`<option value="">Let YuE2 choose</option>`,
    ...voices.map((v) => `<option value="${esc(v.id)}">${esc(v.label)}</option>`)].join("");
  const make = singerReady() ? `
    <section class="make">
      <h2>Make a take</h2>
      <div class="fields">
        <div class="field"><label for="voice">Voice</label><select id="voice">${voiceOptions}</select>
          ${voices.length ? "" : '<p class="hint">Trained voices show up here.</p>'}</div>
        <div class="field"><label for="strength">Voice strength <span id="strength-out">1.0</span></label>
          <input id="strength" type="range" min="0.4" max="1.4" step="0.1" value="1"></div>
        <div class="field"><label for="verses">Verses</label><select id="verses">${verseOptions}</select></div>
        <div class="field"><label for="seed">Seed</label>
          <div class="row"><input id="seed" type="number" min="0" value="831001"><button type="button" class="small" id="reseed">Another</button></div></div>
        <div class="field wide"><label for="style">Style</label>
          <textarea id="style">${esc(song.default_style || "")}</textarea>
          <p class="hint">The sound you want, in words. A trained voice's trigger word goes first.</p></div>
      </div>
      <div class="actions"><button class="go" id="make">Make the take</button>
        <span class="hint">${training.some((r) => !r.done && !r.error && r.stale_minutes <= 10)
          ? "Voice training is using the GPU right now, so a take will be slow and will slow the training down."
          : "Takes render on this Mac's GPU, about a minute for a verse."}</span></div>
      <div class="job" data-job-panel></div>
    </section>` : installPanel();
  return `${make}
    <section><h2>Takes</h2>
      ${takes.length ? `<ul class="recordings">${takes.map(takeItem).join("")}</ul>`
        : '<p class="hint">No takes yet. Choose a voice above and make the first one.</p>'}
    </section>
    ${tests.length ? `<section class="section-gap"><h2>Earlier tests</h2><ul class="recordings">${tests.map(testItem).join("")}</ul></section>` : ""}`;
}

function takeItem(r) {
  const voice = r.voice && r.voice.length ? voiceName(r.voice[0]) : "YuE2's choice";
  const title = r.name === "production" ? "First production" : `Take from ${when(r.when)}`;
  return `<li><h3>${esc(title)}</h3>
    <p class="meta">Voice: ${esc(voice)}. Seed ${esc(r.seed ?? "?")}.</p>
    <audio controls preload="none" src="${fileUrl(r.path)}"></audio>
    ${r.follow ? `<p class="follow">Melody check: ${esc(r.follow)}</p>`
      : `<p class="follow"><button class="small" data-job="follow" data-take="${esc(r.name)}">Check the melody</button></p>`}
    ${r.style ? `<details><summary>Style</summary><p>${esc(r.style)}</p></details>` : ""}</li>`;
}

function testItem(r) {
  const title = r.kind === "preview" ? "Band preview (SoundFont)" : `Sung test: ${r.name.replace(/-/g, " ")} (SoulX, SoundFont band)`;
  return `<li><h3>${esc(title)}</h3><audio controls preload="none" src="${fileUrl(r.path)}"></audio></li>`;
}

function wireSound(song) {
  if (!singerReady()) {
    const accept = $("#accept"), install = $("#install");
    accept.addEventListener("change", () => { install.disabled = !accept.checked; });
    install.addEventListener("click", () => start({ action: "download", group: "singer", accept_licence: accept.checked }));
    return;
  }
  const voice = $("#voice"), style = $("#style"), strength = $("#strength");
  let styleEdited = false;
  style.addEventListener("input", () => { styleEdited = true; });
  const applyVoice = () => {
    const v = voices.find((x) => x.id === voice.value);
    if (!styleEdited) style.value = [v && v.style, song.default_style].filter(Boolean).join(" ");
  };
  voice.addEventListener("change", applyVoice);
  if (pendingVoice && voices.some((v) => v.id === pendingVoice)) { voice.value = pendingVoice; applyVoice(); pendingVoice = null; }
  strength.addEventListener("input", () => { $("#strength-out").textContent = Number(strength.value).toFixed(1); });
  $("#reseed").addEventListener("click", () => { $("#seed").value = Math.floor(Math.random() * 2 ** 31); });
  $("#make").addEventListener("click", () => start({
    action: "produce", song: song.slug, voice: voice.value || null, strength: Number(strength.value),
    verses: Number($("#verses").value), seed: Number($("#seed").value), style: style.value,
  }));
}

// -------------------------------------------------------------------- jobs

function wireJobButtons(song) {
  for (const b of document.querySelectorAll("button[data-job]")) {
    b.addEventListener("click", () => start({ action: b.dataset.job, song: song.slug, take: b.dataset.take }));
  }
}

async function start(body) {
  try {
    watching = await post(body);
    showJob(watching);
    poll();
  } catch (e) {
    showMessage(e.message);
  }
}

function showMessage(text) {
  const panel = $("[data-job-panel]");
  if (panel) panel.innerHTML = `<p class="status failed">${esc(text)}</p>`;
}

function showJob(job) {
  const panel = $("[data-job-panel]");
  if (!panel) return;
  const words = { running: "Working…", done: "Done.", failed: "That didn't work. The output below says why." };
  const pr = job.progress;
  const bar = pr && job.status === "running"
    ? `<p><progress max="${pr[1]}" value="${pr[0]}"></progress> ${(pr[0] / 1e9).toFixed(2)} of ${(pr[1] / 1e9).toFixed(1)} GB</p>` : "";
  panel.innerHTML = `<p class="status ${job.status}">${esc(job.label)}: ${words[job.status] || job.status}</p>${bar}
    <details ${job.status === "failed" ? "open" : ""}><summary>Output</summary><pre>${esc(job.output || "")}</pre></details>`;
  for (const b of document.querySelectorAll("button[data-job], #make, #install")) b.disabled = job.status === "running";
}

// The "Make a take" choices survive the page redrawing after a job.
const FORM = ["voice", "strength", "verses", "seed", "style"];
let saved = null;
function saveForm() {
  if (!$("#make")) return;
  saved = { song: current && current.slug, values: Object.fromEntries(FORM.map((id) => [id, $("#" + id).value])) };
}
function restoreForm() {
  if (!saved || !$("#make") || !current || saved.song !== current.slug) return;
  for (const id of FORM) if (saved.values[id] !== undefined) $("#" + id).value = saved.values[id];
  $("#strength-out").textContent = Number($("#strength").value).toFixed(1);
  $("#style").dispatchEvent(new Event("input"));   // counts as edited: picking a voice won't overwrite it
}

async function poll() {
  if (!watching || watching.status !== "running") return;
  try { watching = await api(`/api/jobs/${watching.id}`); } catch { return; }
  if (watching.status === "running") { showJob(watching); setTimeout(poll, 2000); return; }
  saveForm();
  try { models = await api("/api/models"); } catch { /* keep the last answer */ }
  await route();    // shows the new take or score, then the finished job
  restoreForm();
}

// ---------------------------------------------------------------- training

function bars(run) {
  const steps = run.steps || 1, measures = Math.min(10, Math.max(1, Math.round(steps / 100)));
  const w = 224, x0 = 4, x1 = w - 4, top = 8, gap = 6, bottom = top + 4 * gap;
  const x = (s) => x0 + (x1 - x0) * Math.min(1, s / steps);
  const lines = [0, 1, 2, 3, 4].map((i) => `<line class="line" x1="${x0}" x2="${x1}" y1="${top + i * gap}" y2="${top + i * gap}"/>`).join("");
  const barlines = Array.from({ length: measures + 1 }, (_, i) => {
    const bx = x0 + ((x1 - x0) * i) / measures;
    return `<line class="barline" x1="${bx}" x2="${bx}" y1="${top}" y2="${bottom}"/>`;
  }).join("");
  const head = `<ellipse class="head" cx="${x(run.step)}" cy="${top + 2 * gap}" rx="4.2" ry="3.1" transform="rotate(-20 ${x(run.step)} ${top + 2 * gap})"/>`;
  return `<svg class="bars" viewBox="0 0 ${w} 40" role="img" aria-label="Step ${run.step} of ${steps}">
    <rect class="done" x="${x0}" y="${top}" width="${x(run.step) - x0}" height="${4 * gap}"/>${lines}${barlines}${head}</svg>`;
}

function losses(run) {
  if (run.evals.length < 2) return "";
  const a = run.evals[0], b = run.evals[run.evals.length - 1];
  const row = (label, key) => (key in a && key in b) ? `<span>${label}</span><span>${a[key].toFixed(2)} → ${b[key].toFixed(2)}</span>` : "";
  return `<div class="losses">${row("Songs it learns from", "artist_trained")}${row("Songs held back", "artist_held_out")}${row("YuE2's own songs", "minted_val")}</div>
    <p class="hint">Lower is better. Held-back songs falling too means it's learning the sound, not memorizing.</p>`;
}

function renderTraining(runs) {
  training = runs;
  const box = $("#training");
  if (!runs.length) { box.innerHTML = ""; return; }
  box.innerHTML = `<h2>Voice training</h2>` + runs.map((run) => {
    const status = run.error ? `<p class="warn-text">It stopped with an error. The Terminal window shows the details.</p>`
      : run.done ? `<p>Finished: ${run.steps} steps.</p>`
      : run.steps ? `<p>Step ${run.step} of ${run.steps}. About ${run.hours_left.toFixed(1)} hours left.</p>`
      : `<p>Getting ready.</p>`;
    const stale = !run.done && !run.error && run.stale_minutes > 10
      ? `<p class="warn-text">No news for ${run.stale_minutes} minutes. Is the Terminal window still open?</p>` : "";
    const ready = run.checkpoints.length
      ? `<p class="ready">Ready to try: ${run.checkpoints.map((c) => `<a href="#" data-voice=".cache/lora/${esc(run.name)}/lora/${esc(c)}.safetensors">${esc(c.replace("step-", "step "))}</a>`).join(", ")}</p>` : "";
    return `<div class="run"><h3>${esc(run.name)}</h3>${status}${run.steps ? bars(run) : ""}${losses(run)}${stale}${ready}</div>`;
  }).join("");
  for (const a of box.querySelectorAll("[data-voice]")) {
    a.addEventListener("click", (ev) => {
      ev.preventDefault();
      pendingVoice = a.dataset.voice;
      const slug = current ? current.slug : songs[0] && songs[0].slug;
      if (slug) location.hash = `#/song/${encodeURIComponent(slug)}/sound`;
    });
  }
}

async function refreshTraining() {
  try {
    renderTraining(await api("/api/training"));
    voices = await api("/api/voices");
  } catch { /* the drawer just keeps its last state */ }
  setTimeout(refreshTraining, 15000);
}

// ------------------------------------------------------------------- start

async function main() {
  [songs, voices, training, models] = await Promise.all([api("/api/songs"), api("/api/voices"), api("/api/training"), api("/api/models")]);
  renderSongList();
  renderTraining(training);
  const jobs = await api("/api/jobs");
  watching = jobs.find((j) => j.status === "running") || null;
  window.addEventListener("hashchange", route);
  await route();
  setTimeout(refreshTraining, 15000);
  poll();
}

main().catch((e) => { page.innerHTML = `<div class="empty"><p>Copyist couldn't start: ${esc(e.message)}</p></div>`; });
