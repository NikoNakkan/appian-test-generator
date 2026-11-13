// Import: paste a folder or zip path, or drop a zip. Shown on the welcome page and in the side
// panel. Running imports show progress; when one finishes, its snapshot opens.
const importState = { polling: null, watching: false };

function renderImportForm(box) {
  box.innerHTML = `
    <form class="import-row" data-import>
      <input name="path" type="text" placeholder="C:\\exports\\MyApp or C:\\exports\\MyApp.zip" aria-label="Export path">
      <button class="primary" type="submit">Import</button>
    </form>
    <p class="error" data-import-error hidden></p>
    <label class="drop" tabindex="0">Or drop a <b>.zip</b> export here
      <input type="file" accept=".zip" aria-label="Choose zip export" data-import-file></label>
    <div data-jobs></div>`;
  const drop = box.querySelector(".drop");
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload(box, e.dataTransfer.files[0]); });
  box.querySelector("[data-import-file]").addEventListener("change", (e) => upload(box, e.target.files[0]));
  box.querySelector("[data-import]").addEventListener("submit", (e) => {
    e.preventDefault();
    const path = e.target.path.value.trim();
    if (!path) return fail(box, "Paste the path to an export folder or zip first.");
    start(box, () => getJSON("/api/import", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path }) }));
  });
  pollJobs();
}

function openImport() {
  openPanel(`<div class="panel-head"><h3>Import an export</h3></div><div id="panel-import"></div>
    <div class="dz-section"><h4>Earlier imports</h4>${table(["Export", "Imported", "Checks", ""], state.snapshots.map((s) => [
      `${esc(s.name)}<br><span class="hint">Appian ${esc(s.version)} · ${fmt(s.objects)} objects</span>`,
      `<span class="mono">${esc(s.created.slice(0, 16).replace("T", " "))}</span>`,
      pill(`${s.passed}/${s.checks}`, s.passed === s.checks ? "ok" : "bad"),
      s.id === state.sid ? `<span class="hint">open</span>` : `<button data-snapshot="${s.id}">Open</button>`]))
      || `<p class="hint">None yet.</p>`}</div>`, { kind: "import" });
  renderImportForm($("#panel-import"));
}

const fail = (box, msg) => { const e = box.querySelector("[data-import-error]"); e.textContent = msg; e.hidden = false; };

function upload(box, file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".zip")) return fail(box, "Drop a .zip export, or paste a folder path above.");
  start(box, () => getJSON(`/api/upload?name=${encodeURIComponent(file.name)}`, { method: "POST", body: file }));
}

async function start(box, request) {
  box.querySelector("[data-import-error]").hidden = true;
  try { await request(); importState.watching = true; pollJobs(); } catch (e) { fail(box, e.message); }
}

async function pollJobs() {
  clearTimeout(importState.polling);
  const jobs = await getJSON("/api/jobs");
  const html = jobs.slice(0, 3).map((j) => {
    const pct = j.state === "done" ? 100 : j.total ? Math.round((j.done / j.total) * 100) : 0;
    const stage = j.state === "running" ? `${j.stage || "starting"}${j.total > 1 ? ` ${fmt(j.done)} / ${fmt(j.total)}` : ""}` : j.state;
    return `<div class="job"><div class="job-head"><b>${esc(j.root || j.source)}</b>
      ${pill(stage, { done: "ok", failed: "bad", running: "ext" }[j.state] || "idle")}</div>
      <div class="bar" role="progressbar" aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><span style="width:${pct}%"></span></div>
      ${j.messages.map((m) => `<span class="hint">${esc(m)}</span>`).join("")}</div>`;
  }).join("");
  document.querySelectorAll("[data-jobs]").forEach((el) => (el.innerHTML = html));
  const running = jobs.some((j) => j.state === "running" || j.state === "queued");
  const finished = jobs.find((j) => j.state === "done" && j.snapshots.length);
  $("#import-btn").textContent = running ? "Importing…" : "Import";
  if (running) {
    importState.watching = true;
    importState.polling = setTimeout(pollJobs, 700);
  } else if (finished && importState.watching) {
    importState.watching = false;
    closePanel();
    openSnapshot(finished.snapshots[finished.snapshots.length - 1]);
  }
}

document.addEventListener("click", async (e) => {
  const b = e.target.closest("#panel [data-snapshot]");
  if (b) { closePanel(); await openSnapshot(+b.dataset.snapshot); }
});
