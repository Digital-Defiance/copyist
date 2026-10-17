// The start page: "Starting…" until the engine is ready, or why it stopped.
const q = new URLSearchParams(location.search);
if (q.has("stopped")) {
  document.body.classList.add("stopped");
  document.getElementById("message").textContent =
    "Copyist's engine stopped. Quit Copyist and open it again; if it keeps happening, the details below say why.";
  const detail = q.get("detail");
  if (detail) {
    const pre = document.getElementById("detail");
    pre.textContent = detail;
    pre.hidden = false;
  }
}
