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
let writings = [];           // /api/writing: songs being written
let rewrites = [];           // /api/rewrites: section rewrites in progress
let allStyles = null;        // /api/styles, loaded when the "Write a song" form first opens
let transcriptions = { items: [], sheetsage: false };   // /api/transcriptions
const TABS = [["song", "The song"], ["score", "The score"], ["sound", "The sound"]];
const REWRITE_HOW = [
  ["again", "Try again", "Swap this section for another melody with the same feel."],
  ["higher", "Higher", "Move this section up a few notes, with its chords."],
  ["simpler", "Simpler", "Prefer a version of this section with smaller leaps."],
];
const SECTION_NAMES = { verse: "Verse", chorus: "Chorus", bridge: "Bridge", intro: "Intro", outro: "Outro",
  prechorus: "Pre-chorus" };

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
  const plain = (t) => t.replace(/\*/g, "").replace(/_/g, "").replace(/-\s*/g, "").replace(/\s+/g, " ").trim();
  const lines = String(text).trim().split("\n");
  if (lines.length > 1) return lines.map(plain).filter(Boolean);     // written songs keep one lyric line per line
  return plain(String(text)).split(/(?<=[.!?;])\s+/);
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

function renderWritingList() {
  const box = $("#writing-list");
  const written = writings.length ? `<h2>Being written</h2><ul class="song-list">${writings.map((w) =>
    `<li><a href="#/write/${encodeURIComponent(w.slug)}" data-slug="write:${esc(w.slug)}">${esc(w.title)}</a>
      <span class="meta">${w.usable} of ${w.candidates} usable${w.kept ? ", one kept" : ""}</span></li>`).join("")}</ul>` : "";
  const redone = rewrites.length ? `<h2>Rewrites</h2><ul class="song-list">${rewrites.map((w) =>
    `<li><a href="#/rewrite/${encodeURIComponent(w.slug)}/${esc(w.how)}" data-slug="rewrite:${esc(w.slug)}:${esc(w.how)}">${esc(w.title)}</a>
      <span class="meta">${esc(w.how)} · ${w.usable} of ${w.candidates}${w.kept ? ", one kept" : ""}</span></li>`).join("")}</ul>` : "";
  const heard = transcriptions.items.length ? `<h2>Transcribed</h2><ul class="song-list">${transcriptions.items.map((t) =>
    `<li><a href="#/transcribe/${encodeURIComponent(t.slug)}" data-slug="transcribe:${esc(t.slug)}">${esc(t.title)}</a>
      ${t.kept ? '<span class="meta">kept</span>' : ""}</li>`).join("")}</ul>` : "";
  const parts = [written, redone, heard].filter(Boolean);
  box.innerHTML = parts.join('<div class="drawer-gap"></div>');
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
  const w = location.hash.match(/^#\/write(?:\/([^/]+))?$/);
  if (w) return w[1] ? routeWriting(decodeURIComponent(w[1])) : routeWriteForm();
  const rw = location.hash.match(/^#\/rewrite\/([^/]+)\/(again|higher|simpler)$/);
  if (rw) return routeRewrite(decodeURIComponent(rw[1]), rw[2]);
  const t = location.hash.match(/^#\/transcribe(?:\/([^/]+))?$/);
  if (t) return t[1] ? routeTranscription(decodeURIComponent(t[1])) : routeTranscribeForm();
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
  if (tab === "song") wireRewrite(current);
  wireJobButtons(current);
  if (watching) showJob(watching);
}

function wireRewrite(song) {
  for (const b of document.querySelectorAll("[data-rewrite]")) {
    b.addEventListener("click", () => {
      const section = ($("#rewrite-section") && $("#rewrite-section").value) || "verse";
      start({ action: "rewrite", song: song.slug, how: b.dataset.rewrite, section, candidates: 4 }, "rewrite");
    });
  }
  const refit = $("#refit-go");
  if (refit) {
    refit.addEventListener("click", () => {
      const lyrics = ($("#refit-lyrics") && $("#refit-lyrics").value) || "";
      start({ action: "refit", song: song.slug, lyrics }, "refit");
    });
  }
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
  const edit = song.lyrics_edit || "";
  return `<div class="song-tab">
      <section><h2>Lyrics</h2><div class="verses" style="margin-top:.75rem">${verses || '<p class="hint">No lyrics.</p>'}</div>
        <div class="section-gap">
          <h2>Edit the lyrics</h2>
          <p class="hint">Change the words and fit them under the same melody. You can mark [Verse] and [Chorus].
            The score and band preview are written again when you save.</p>
          <textarea id="refit-lyrics" class="lyrics-box" rows="8">${esc(edit)}</textarea>
          <div class="actions" style="margin-top:.5rem">
            <button class="small" id="refit-go">Fit lyrics and write the score</button></div>
          <div class="job" data-job-panel="refit"></div>
        </div>
        ${rewritePanel(song)}</section>
      <aside><h2>Checks</h2>${checks}<div class="job" data-job-panel></div></aside>
    </div>`;
}

function rewritePanel(song) {
  const sections = (song.sections && song.sections.length)
    ? song.sections : [{ name: "verse", bar: 1 }];
  const opts = sections.map((s) =>
    `<option value="${esc(s.name)}">${esc(SECTION_NAMES[s.name] || s.name)} (bar ${s.bar})</option>`).join("");
  const past = (song.rewrites || []).map((r) =>
    `<li><a href="#/rewrite/${encodeURIComponent(song.slug)}/${esc(r.how)}">${esc(r.how)}</a>
      <span class="meta">${r.usable} of ${r.candidates}${r.kept ? ", kept" : ""}</span></li>`).join("");
  const buttons = REWRITE_HOW.map(([how, label]) =>
    `<button class="small" data-rewrite="${esc(how)}">${esc(label)}</button>`).join("");
  return `<div class="section-gap rewrite-panel">
      <h2>Try another melody</h2>
      <p class="hint">Change one section by ear: try again, sit higher, or prefer smaller leaps. Each choice
        writes a few candidates with the band playing them.</p>
      <p><label>Section <select id="rewrite-section">${opts}</select></label></p>
      <div class="actions">${buttons}</div>
      ${past ? `<ul class="song-list" style="margin-top:.75rem">${past}</ul>` : ""}
      <div class="job" data-job-panel="rewrite"></div>
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
      <p class="hint">${esc(models.licence)} <a href="${esc(models.licence_url)}" rel="noopener">Read the licence</a>.</p>
      <p><label class="check"><input type="checkbox" id="accept"> I accept the licence</label></p>
      <div class="actions"><button class="go" id="install" disabled>Download the singer</button>
        <span class="hint">It goes into ${esc(models.folder)}.</span></div>
      <div class="job" data-job-panel></div>
    </section>`;
}

const PART_NAMES = { melody: "Melody", piano: "Piano", bass: "Bass", drums: "Drums", other: "Other" };

function bandPack() {
  return models && (models.instruments || []).find((x) => x.id === "instruments-band");
}

function bandSection(song) {
  const b = song.band, pack = bandPack();
  const gb = (n) => (n / 1e9).toFixed(1);
  let body;
  if (!b) {
    body = '<p class="hint">Write the score (on the Song tab) and the band plays it here.</p>';
  } else if (b.engine === "sampled") {
    body = `<audio controls preload="none" src="${fileUrl(b.path)}"></audio>
      <ul class="players">${b.parts.map((x) => `<li><span class="part">${esc(PART_NAMES[x.part] || x.part)}</span>
        <span>${esc(x.label)}</span>${x.path ? ` <a href="${fileUrl(x.path)}" download>stem</a>` : ""}</li>`).join("")}</ul>
      ${b.credits.length ? `<p class="hint">Credits: ${b.credits.map(esc).join("; ")}.</p>` : ""}`;
  } else {
    body = `<audio controls preload="none" src="${fileUrl(b.path)}"></audio>
      <p class="hint">Played with a basic SoundFont${b.note ? `, because ${esc(b.note)}` : "."}</p>`;
  }
  let offer = "";
  if (pack && !pack.ready) {
    offer = `<div class="offer">
      <p>Hear it on real instruments: a concert grand, upright and electric basses, a drum kit, and a clarinet
        for the melody. A one-time download of ${gb(pack.size)} GB${pack.have ? `, ${gb(pack.have)} GB of it already here` : ""}.</p>
      <p class="hint">${pack.models.map((i) => `${esc(i.label)} (${esc(i.licence)})`).join("; ")}.
        All free to use in any music you make.</p>
      <div class="actions"><button class="go" id="get-band">Download the instruments</button>
        <span class="hint">They go into ${esc(models.instruments_folder)}.</span></div></div>`;
  } else if (pack && pack.ready && !models.sfizz) {
    offer = '<p class="hint">The instruments are here, but their player (sfizz) isn\'t installed yet: run scripts/setup-sfizz.sh, or use the desktop app.</p>';
  } else if (pack && pack.ready && b && b.engine !== "sampled") {
    offer = '<div class="actions"><button class="go" data-job="build" data-panel="band">Play it on the real instruments</button></div>';
  }
  return `<section class="section-gap"><h2>The band</h2>
    <p class="hint">The score exactly as written, played by the band, so you can check it by ear.</p>
    ${body}${offer}<div class="job" data-job-panel="band"></div></section>`;
}

function stylesSection(song) {
  if (!song.styles.length) return "";
  const made = Object.fromEntries(song.gallery.map((g) => [g.style, g]));
  const families = [...new Set(song.styles.map((s) => s.family))];
  const n = song.styles.length;
  const item = (s) => {
    const g = made[s.id], current = s.id === song.style_in_use;
    const feel = s.feel !== "straight" ? `, ${s.feel}` : "";
    const action = current ? '<span class="tag">This song\'s style</span>'
      : g ? `<button class="small" data-use="${esc(s.id)}" data-tempo="${g.tempo}">Use this style</button>` : "";
    const player = (label, path) => path
      ? `<div class="player"><span class="player-label">${label}</span><audio controls preload="none" src="${fileUrl(path)}"></audio></div>` : "";
    return `<li class="${current ? "current" : ""}"><div class="style-head"><h4>${esc(s.name)}</h4>
        ${g ? `<span class="meta">${g.tempo} beats a minute${esc(feel)}</span>` : ""}${action}</div>
      <p class="hint">${esc(s.about)}</p>
      ${g ? player("Finished take", g.take_path) + player("Band preview", g.path) : ""}</li>`;
  };
  const takes = singerReady() ? `<div class="actions"><button data-job="gallery-takes" data-panel="styles">Make a finished
      take in every style</button><span class="hint">YuE2 sings each style with its own band, in the voice chosen
      above. About 45 seconds a style on this Mac.</span></div>` : "";
  return `<section class="section-gap"><h2>Styles</h2>
    <p class="hint">The same song in every style that fits its ${esc(song.meter)} time, each at a tempo that suits
      it, played by the band. Listen, and use the one you like: the score and parts are written again in that style.</p>
    <div class="actions"><button class="go" data-job="gallery" data-panel="styles">${song.gallery.length
      ? "Play them all again" : `Hear it in all ${n} styles`}</button>
      <span class="hint">The band preview: a few seconds a style.</span></div>
    ${takes}
    <div class="job" data-job-panel="styles"></div>
    ${families.map((f) => `<h3 class="family">${esc(f)}</h3>
      <ul class="styles">${song.styles.filter((s) => s.family === f).map(item).join("")}</ul>`).join("")}
  </section>`;
}

function soundTab(song) {
  const takes = song.recordings.filter((r) => r.kind === "take");
  const tests = song.recordings.filter((r) => r.kind !== "take" && r.kind !== "preview");
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
    ${bandSection(song)}
    ${stylesSection(song)}
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
  const title = `Sung test: ${r.name.replace(/-/g, " ")} (SoulX-Singer)`;
  return `<li><h3>${esc(title)}</h3><audio controls preload="none" src="${fileUrl(r.path)}"></audio></li>`;
}

function wireSound(song) {
  const getBand = $("#get-band");
  if (getBand) getBand.addEventListener("click", () => start({ action: "download", group: "instruments-band" }, "band"));
  for (const b of document.querySelectorAll("button[data-use]")) {
    b.addEventListener("click", () => start({ action: "use-style", song: song.slug, style: b.dataset.use,
      tempo: Number(b.dataset.tempo) }, "styles"));
  }
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

// ------------------------------------------------------- writing a song

const VOICE_LABELS = { soprano: "Soprano (high female)", alto: "Alto (low female)", tenor: "Tenor (high male)",
  baritone: "Baritone (low male)" };

async function routeWriteForm() {
  markCurrent(null);
  current = null;
  if (!allStyles) {
    try { allStyles = await api("/api/styles"); } catch { allStyles = []; }
  }
  const families = [...new Set(allStyles.map((s) => s.family))];
  const styleOptions = `<option value="">No particular style</option>` + families.map((f) =>
    `<optgroup label="${esc(f)}">${allStyles.filter((s) => s.family === f).map((s) =>
      `<option value="${esc(s.id)}">${esc(s.name)}</option>`).join("")}</optgroup>`).join("");
  const form = singerReady() ? `
    <section class="make">
      <div class="fields">
        <div class="field"><label for="w-title">Title</label><input id="w-title" type="text" maxlength="120"></div>
        <div class="field"><label for="w-style">Style</label><select id="w-style">${styleOptions}</select></div>
        <div class="field"><label for="w-voice">Voice</label><select id="w-voice">${Object.entries(VOICE_LABELS).map(([id, label]) =>
          `<option value="${id}" ${id === "alto" ? "selected" : ""}>${esc(label)}</option>`).join("")}</select></div>
        <div class="field"><label for="w-count">How many to write</label><select id="w-count">${[2, 3, 4, 6, 8].map((n) =>
          `<option ${n === 4 ? "selected" : ""}>${n}</option>`).join("")}</select></div>
        <div class="field"><label for="w-engine">Writer</label><select id="w-engine">
          <option value="auto" selected>Auto (YuE2 when installed)</option>
          <option value="plan">YuE2 planner</option>
          <option value="rules">Copyist's own (no GPU)</option>
        </select></div>
        <div class="field wide"><label for="w-lyrics">Lyrics</label>
          <textarea id="w-lyrics" class="lyrics-box" placeholder="[Verse]&#10;Hope is the thing with feathers&#10;That perches in the soul&#10;&#10;[Chorus]&#10;..."></textarea>
          <p class="hint">One sung line per line. Mark sections with [Verse], [Chorus], [Bridge]; untagged lines count as a verse.</p></div>
        <div class="field wide"><label for="w-words">More words for the sound (optional)</label>
          <input id="w-words" type="text" maxlength="300" placeholder="music box, slow build, cast recording">
          <p class="hint">They steer the melody writer along with the style.</p></div>
      </div>
      <div class="actions"><button class="go" id="w-go">Write the songs</button>
        <span class="hint">Each melody comes with the band playing it, so you can choose by ear. Copyist's own writer
          needs no download.</span></div>
      <div class="job" data-job-panel></div>
    </section>` : installPanel();
  page.innerHTML = `<div class="staff-title"><h1>Write a song</h1></div>
    <p class="facts">Give Copyist your lyrics and it writes several melodies for them, with chords, the lyrics placed
      under the notes, and the band playing each one. Keep the one you like, and it becomes a song with a lead
      sheet, a score and parts.</p>${form}`;
  if (!singerReady()) {
    const accept = $("#accept"), install = $("#install");
    accept.addEventListener("change", () => { install.disabled = !accept.checked; });
    install.addEventListener("click", () => start({ action: "download", group: "singer", accept_licence: accept.checked }));
  } else {
    $("#w-go").addEventListener("click", async () => {
      const body = { action: "write", title: $("#w-title").value.trim(), lyrics: $("#w-lyrics").value,
        style: $("#w-style").value || null, voice: $("#w-voice").value, words: $("#w-words").value.trim() || null,
        candidates: Number($("#w-count").value), engine: $("#w-engine").value };
      await start(body);
      if (watching && watching.song) location.hash = `#/write/${encodeURIComponent(watching.song)}`;
    });
  }
  if (watching) showJob(watching);
}

function scoreWords(c) {
  const s = c.scores;
  const checks = s.fails ? `${s.fails} failing check${s.fails > 1 ? "s" : ""}` : "passes every check";
  const warns = s.warnings ? `, ${s.warnings} warning${s.warnings > 1 ? "s" : ""}` : "";
  const fit = s.fit_cost < 0.6 ? "the words sit well on the beat" : s.fit_cost < 1 ? "the words mostly sit on the beat"
    : "some words fall awkwardly";
  const hook = s.hook ? `; the chorus's opening comes back ${s.hook === 1 ? "once" : s.hook + " times"}` : "";
  return `It ${checks}${warns}; ${fit}${hook}.`;
}

function sectionsWords(sections) {
  return (sections || []).map((x) => `${SECTION_NAMES[x.name] || x.name} at bar ${x.bar}`).join(", ");
}

function candidateItem(d, c) {
  if (!c.ok) {
    return `<li class="unusable"><h3>Candidate ${c.seed}</h3><p class="hint">Couldn't be used: ${esc(c.reason || "see its report")}</p></li>`;
  }
  const keep = d.kept === c.seed ? '<span class="tag">Kept</span>'
    : `<button class="small" data-keep="${c.seed}">${d.song_exists ? "Keep this one (replaces the song of the same name)" : "Keep this one"}</button>`;
  const player = (label, path) => path
    ? `<div class="player"><span class="player-label">${label}</span><audio controls preload="none" src="${fileUrl(path)}"></audio></div>` : "";
  return `<li><div class="style-head"><h3>${c.rank}. Candidate ${c.seed}</h3>
      <span class="meta">${esc(keyName(c.key))}, ${esc(c.meter)}, ${esc(c.tempo)} beats a minute</span>${keep}</div>
    ${player("Finished take", c.take_path)}${player("Band preview", c.preview_path)}
    ${c.preview_path || c.take_path ? "" : `<p class="hint">${c.preview_error ? `No preview: ${esc(c.preview_error)}` : "No preview yet."}</p>`}
    <p>${esc(scoreWords(c))}</p>
    ${c.sections && c.sections.length ? `<p class="hint">Sections: ${esc(sectionsWords(c.sections))}.</p>` : ""}
    <details><summary>Details</summary><ul>${(c.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
      ${c.report_path ? `<p><a href="${fileUrl(c.report_path)}" target="_blank" rel="noopener">The full report</a></p>` : ""}</details></li>`;
}

function candidatesHtml(d) {
  const cands = d.candidates || [];
  return cands.length ? `<ul class="styles candidates">${cands.map((c) => candidateItem(d, c)).join("")}</ul>`
    : '<p class="hint">The first melody is on its way.</p>';
}

let writingShown = null;    // what the candidate list was drawn from, so it's redrawn only when it changes
async function routeWriting(slug) {
  markCurrent("write:" + slug);
  current = null;
  let d;
  try { d = await api(`/api/writing/${encodeURIComponent(slug)}`); } catch (e) {
    page.innerHTML = `<div class="empty"><p>Couldn't open that: ${esc(e.message)}</p></div>`;
    return;
  }
  writingShown = JSON.stringify(d.candidates);
  page.innerHTML = `<div class="staff-title"><h1>${esc(d.title)}</h1></div>
    <p class="facts">${(d.candidates || []).some((c) => c.ok)
      ? `${(d.candidates || []).filter((c) => c.ok).length} melodies to choose from, best first by Copyist's checks.
         Listen, and keep the one you like: it becomes a song with its score written out.`
      : "Copyist is writing the melodies. Each one shows up here, with the band playing it, as soon as it's ready."}</p>
    <div class="actions"><button data-write-more>Write ${4} more</button>
      ${d.kept ? `<a class="button small" href="#/song/${encodeURIComponent(d.slug)}/song">Open the kept song</a>` : ""}</div>
    <div class="job" data-job-panel></div>
    <section class="section-gap" id="candidates">${candidatesHtml(d)}</section>
    <details class="section-gap"><summary>The lyrics</summary><pre class="lyrics-text">${esc(d.lyrics)}</pre></details>`;
  wireWriting(d);
  if (watching) showJob(watching);
}

function wireWriting(d) {
  for (const b of document.querySelectorAll("[data-keep]")) {
    b.addEventListener("click", () => start({ action: "keep", slug: d.slug, seed: Number(b.dataset.keep),
      replace: d.song_exists }));
  }
  const more = $("[data-write-more]");
  if (more) more.addEventListener("click", () => start({ action: "write-more", slug: d.slug, candidates: 4 }));
}

function rewriteCandidateItem(d, c) {
  if (!c.ok) {
    return `<li class="unusable"><h3>Candidate ${c.seed}</h3><p class="hint">Couldn't be used: ${esc(c.reason || "see its report")}</p></li>`;
  }
  const keep = d.kept === c.seed ? '<span class="tag">Kept</span>'
    : `<button class="small" data-keep-rewrite="${c.seed}">${d.song_exists ? "Keep this one (replaces the song)" : "Keep this one"}</button>`;
  const extra = c.semitones ? ` (+${c.semitones})` : (c.donor ? ` (from write ${c.donor})` : "");
  const player = c.preview_path
    ? `<div class="player"><span class="player-label">Band preview</span><audio controls preload="none" src="${fileUrl(c.preview_path)}"></audio></div>` : "";
  return `<li><div class="style-head"><h3>${c.rank}. Candidate ${c.seed}${extra}</h3>
      <span class="meta">${esc(keyName(c.key))}, ${esc(c.meter)}</span>${keep}</div>
    ${player}
    <p>${esc(scoreWords(c))}</p>
    <details><summary>Details</summary><ul>${(c.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
      ${c.report_path ? `<p><a href="${fileUrl(c.report_path)}" target="_blank" rel="noopener">The full report</a></p>` : ""}</details></li>`;
}

async function routeRewrite(slug, how) {
  markCurrent(`rewrite:${slug}:${how}`);
  current = null;
  let d;
  try { d = await api(`/api/rewrites/${encodeURIComponent(slug)}/${encodeURIComponent(how)}`); } catch (e) {
    page.innerHTML = `<div class="empty"><p>Couldn't open that: ${esc(e.message)}</p></div>`;
    return;
  }
  const label = (REWRITE_HOW.find((x) => x[0] === how) || [how, how])[1];
  page.innerHTML = `<div class="staff-title"><h1>${esc(d.title)}</h1></div>
    <p class="facts">${esc(label)} · ${esc(SECTION_NAMES[d.section] || d.section || "verse")}.
      Listen, and keep the one you like.</p>
    <div class="actions">
      <a class="button small" href="#/song/${encodeURIComponent(slug)}/song">Back to the song</a>
    </div>
    <div class="job" data-job-panel></div>
    <section class="section-gap" id="candidates"><ul class="styles candidates">${
      (d.candidates || []).map((c) => rewriteCandidateItem(d, c)).join("") ||
      '<p class="hint">The first rewrite is on its way.</p>'}</ul></section>`;
  for (const b of document.querySelectorAll("[data-keep-rewrite]")) {
    b.addEventListener("click", () => start({ action: "keep-rewrite", song: slug, how, seed: Number(b.dataset.keepRewrite),
      replace: d.song_exists }));
  }
  if (watching) showJob(watching);
}

// Candidates land one at a time while a write runs: show each, without cutting off one that's playing.
async function refreshWriting() {
  const w = location.hash.match(/^#\/write\/([^/]+)$/);
  if (!w) return;
  if ([...document.querySelectorAll("audio")].some((a) => !a.paused)) return;
  if (!$("#candidates")) { await route(); return; }
  let d;
  try { d = await api(`/api/writing/${w[1]}`); } catch { return; }
  const now = JSON.stringify(d.candidates);
  if (now === writingShown) return;
  writingShown = now;
  const box = $("#candidates");
  if (box) { box.innerHTML = candidatesHtml(d); wireWriting(d); }
}

// ------------------------------------------------- transcribing a recording

function routeTranscribeForm() {
  markCurrent(null);
  current = null;
  const ss = transcriptions.sheetsage;
  page.innerHTML = `<div class="staff-title"><h1>Transcribe a recording</h1></div>
    <p class="facts">Give Copyist a recording of a song, one you made or have the rights to, and it writes the
      lead sheet: the melody as sung, the chords, and the words under the notes. Then the band plays it back so
      you can compare it with the original by ear.</p>
    <section class="make">
      <div class="fields">
        <div class="field wide"><label for="t-file">The recording</label>
          <input id="t-file" type="file" accept="audio/*,.wav,.mp3,.flac,.m4a,.ogg"></div>
        <div class="field"><label for="t-title">Title</label><input id="t-title" type="text" maxlength="120"></div>
        <div class="field"><label for="t-engine">Transcriber</label><select id="t-engine" title="SheetSage2 is often more accurate, but its licence forbids commercial use.">
          <option value="open">Copyist's own: free for any use</option>
          <option value="sheetsage" ${ss ? "" : "disabled"}>SheetSage2: non-commercial${ss ? "" : " (not installed)"}</option>
        </select></div>
        <div class="field wide" id="t-licence" hidden><label class="check"><input type="checkbox" id="t-accept">
          I understand SheetSage2's licence is non-commercial: I won't use this transcription in anything I sell.</label></div>
        <div class="field wide"><label for="t-lyrics">Lyrics (optional, but they help a lot)</label>
          <textarea id="t-lyrics" class="lyrics-box" placeholder="[Verse]&#10;The words as they're sung, one line per line"></textarea>
          <p class="hint">The words tell Copyist how many notes the singer sings. Without them, it listens for the words itself.</p></div>
      </div>
      <div class="actions"><button class="go" id="t-go">Transcribe it</button>
        <span class="hint" id="t-status">The recording stays on this computer.</span></div>
      <div class="job" data-job-panel></div>
    </section>`;
  const file = $("#t-file"), title = $("#t-title"), engine = $("#t-engine");
  file.addEventListener("change", () => {
    if (file.files[0] && !title.value) title.value = file.files[0].name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
  });
  engine.addEventListener("change", () => { $("#t-licence").hidden = engine.value !== "sheetsage"; });
  $("#t-go").addEventListener("click", async () => {
    const f = file.files[0];
    if (!f) { showMessage("Choose the recording first."); return; }
    $("#t-go").disabled = true;
    $("#t-status").textContent = "Copying the recording into your library…";
    try {
      const r = await fetch(`/api/upload?name=${encodeURIComponent(f.name)}`, {
        method: "POST", headers: { "X-Copyist": "1", "Content-Type": "application/octet-stream" }, body: f });
      const up = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(up.error || r.statusText);
      $("#t-status").textContent = "The recording stays on this computer.";
      await start({ action: "transcribe", upload: up.upload, title: title.value.trim(), lyrics: $("#t-lyrics").value,
        engine: engine.value, accept_licence: $("#t-accept").checked });
      if (watching && watching.song) location.hash = `#/transcribe/${encodeURIComponent(watching.song)}`;
    } catch (e) {
      showMessage(e.message);
    } finally {
      $("#t-go") && ($("#t-go").disabled = false);
    }
  });
  if (watching) showJob(watching);
}

async function routeTranscription(slug) {
  markCurrent("transcribe:" + slug);
  current = null;
  let d;
  try { d = await api(`/api/transcriptions/${encodeURIComponent(slug)}`); } catch (e) {
    page.innerHTML = `<div class="empty"><p>Couldn't open that: ${esc(e.message)}</p></div>`;
    return;
  }
  if (d.pending) {
    page.innerHTML = `<div class="staff-title"><h1>${esc(d.title)}</h1></div>
      <p class="facts">Copyist is listening: separating the voice from the band, then finding the beat, the key,
        the chords and every sung note. It takes a minute or two.</p><div class="job" data-job-panel></div>`;
    if (watching) showJob(watching);
    return;
  }
  const player = (label, path) => path
    ? `<div class="player"><span class="player-label">${label}</span><audio controls preload="none" src="${fileUrl(path)}"></audio></div>` : "";
  const keep = d.kept ? `<a class="button small" href="#/song/${encodeURIComponent(d.slug)}/song">Open the song</a>`
    : `<button class="go" data-keep-transcription>${d.song_exists ? "Keep it (replaces the song of the same name)" : "Keep it"}</button>`;
  const checks = d.fails ? `${d.fails} failing check${d.fails > 1 ? "s" : ""}` : "It passes every check";
  page.innerHTML = `<div class="staff-title"><h1>${esc(d.title)}</h1></div>
    <p class="facts">${esc(keyName(d.key))}, ${esc(d.meter)}, ${esc(d.tempo)}. Transcribed from ${esc(d.recording)}
      by ${d.engine === "sheetsage" ? "SheetSage2 (non-commercial use only)" : "Copyist's own transcriber"}.</p>
    <section class="section-gap"><h2>Compare by ear</h2>
      <p class="hint">Play the original, then the band playing what Copyist wrote. Where they differ, the doubts below
        are the first places to listen.</p>
      <div class="styles">${player("The recording", d.source_path)}${player("Copyist's band, playing the transcription", d.preview_path)}</div>
      ${d.preview_path ? "" : `<p class="hint">${d.preview_error ? `No playback: ${esc(d.preview_error)}` : "No playback yet."}</p>`}
    </section>
    <section class="section-gap"><h2>Doubts</h2>
      ${d.doubts && d.doubts.length ? `<ul>${d.doubts.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`
        : '<p class="hint">None: wherever the audio was unclear, the music around it decided clearly.</p>'}
    </section>
    <section class="section-gap"><h2>What Copyist heard</h2>
      <p>${esc(checks)}${d.warnings ? `, ${d.warnings} warning${d.warnings > 1 ? "s" : ""}` : ""}.
        ${d.sections && d.sections.length > 1 ? `Sections: ${esc(sectionsWords(d.sections))}.` : ""}</p>
      <ul>${(d.notes || []).map((n) => `<li>${esc(n)}</li>`).join("")}</ul>
      ${d.report_path ? `<p><a href="${fileUrl(d.report_path)}" target="_blank" rel="noopener">The full report</a></p>` : ""}
    </section>
    <div class="actions section-gap">${keep}<span class="hint">Keeping it adds it to your songs and writes its lead
      sheet, score and parts.</span></div>
    <div class="job" data-job-panel></div>`;
  const k = $("[data-keep-transcription]");
  if (k) k.addEventListener("click", () => start({ action: "keep-transcription", slug: d.slug, replace: d.song_exists }));
  if (watching) showJob(watching);
}

// -------------------------------------------------------------------- jobs

function wireJobButtons(song) {
  for (const b of document.querySelectorAll("button[data-job]")) {
    b.addEventListener("click", () => {
      const body = { action: b.dataset.job, song: song.slug, take: b.dataset.take };
      if (b.dataset.job === "gallery-takes" && $("#voice") && $("#voice").value) {
        body.voice = $("#voice").value;
        body.strength = Number($("#strength").value);
      }
      start(body, b.dataset.panel);
    });
  }
}

let jobPanel = null;    // which panel shows the running job ("band", or the first one on the page)
function panelFor() {
  return (jobPanel && $(`[data-job-panel="${jobPanel}"]`)) || $("[data-job-panel]");
}

async function start(body, panel = null) {
  jobPanel = panel;
  try {
    watching = await post(body);
    showJob(watching);
    poll();
  } catch (e) {
    showMessage(e.message);
  }
}

function showMessage(text) {
  const panel = panelFor();
  if (panel) panel.innerHTML = `<p class="status failed">${esc(text)}</p>`;
}

function showJob(job) {
  const panel = panelFor();
  if (!panel) return;
  const words = { running: "Working…", done: "Done.", failed: "That didn't work. The output below says why." };
  const pr = job.progress;
  const bar = pr && job.status === "running"
    ? `<p><progress max="${pr[1]}" value="${pr[0]}"></progress> ${(pr[0] / 1e9).toFixed(2)} of ${(pr[1] / 1e9).toFixed(1)} GB</p>` : "";
  panel.innerHTML = `<p class="status ${job.status}">${esc(job.label)}: ${words[job.status] || job.status}</p>${bar}
    <details ${job.status === "failed" ? "open" : ""}><summary>Output</summary><pre>${esc(job.output || "")}</pre></details>`;
  for (const b of document.querySelectorAll("button[data-job], button[data-use], button[data-keep], button[data-keep-rewrite], button[data-rewrite], [data-write-more], [data-keep-transcription], #make, #install, #get-band, #w-go, #t-go, #refit-go")) b.disabled = job.status === "running";
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
  if (watching.status === "running") { showJob(watching); await refreshWriting(); await refreshRewrite(); setTimeout(poll, 2000); return; }
  saveForm();
  try { models = await api("/api/models"); } catch { /* keep the last answer */ }
  try {
    [songs, writings, rewrites, transcriptions] = await Promise.all([
      api("/api/songs"), api("/api/writing"), api("/api/rewrites"), api("/api/transcriptions")]);
    renderSongList();
    renderWritingList();
  } catch { /* keep the last lists */ }
  if (watching.status === "done" && watching.label.startsWith("Keep") && watching.song) {
    location.hash = `#/song/${encodeURIComponent(watching.song)}/song`;
    return;                       // the hash change draws the kept song
  }
  const rewritten = watching.status === "done" && watching.label.match(/^Rewriting the \w+ \((again|higher|simpler)\)$/);
  if (rewritten && watching.song) {
    location.hash = `#/rewrite/${encodeURIComponent(watching.song)}/${rewritten[1]}`;
    return;
  }
  await route();    // shows the new take or score, then the finished job
  restoreForm();
}

async function refreshRewrite() {
  const w = location.hash.match(/^#\/rewrite\/([^/]+)\/(again|higher|simpler)$/);
  if (!w) return;
  if ([...document.querySelectorAll("audio")].some((a) => !a.paused)) return;
  try {
    const d = await api(`/api/rewrites/${w[1]}/${w[2]}`);
    const box = $("#candidates");
    if (box) box.innerHTML = `<ul class="styles candidates">${
      (d.candidates || []).map((c) => rewriteCandidateItem(d, c)).join("")}</ul>`;
    for (const b of document.querySelectorAll("[data-keep-rewrite]")) {
      b.addEventListener("click", () => start({ action: "keep-rewrite", song: decodeURIComponent(w[1]), how: w[2],
        seed: Number(b.dataset.keepRewrite), replace: d.song_exists }));
    }
  } catch { /* keep the last list */ }
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
  [songs, voices, training, models, writings, rewrites, transcriptions] = await Promise.all([
    api("/api/songs"), api("/api/voices"), api("/api/training"), api("/api/models"),
    api("/api/writing"), api("/api/rewrites"), api("/api/transcriptions")]);
  renderSongList();
  renderWritingList();
  renderTraining(training);
  const jobs = await api("/api/jobs");
  watching = jobs.find((j) => j.status === "running") || null;
  window.addEventListener("hashchange", route);
  await route();
  setTimeout(refreshTraining, 15000);
  poll();
}

main().catch((e) => { page.innerHTML = `<div class="empty"><p>Copyist couldn't start: ${esc(e.message)}</p></div>`; });
