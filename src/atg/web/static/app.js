// Shell: four views (Tests, App, Changes, Analysis), the snapshot picker, and the header buttons.
// Health checks and Import open in the side panel; with no snapshot yet, the welcome page shows.
const VIEWS = { tests: () => renderTests(), app: () => renderBrowse(), changes: () => renderChanges(), analysis: () => renderAnalysis() };

function show(view) {
  const wanted = view in VIEWS ? view : "tests";
  state.view = state.sid ? wanted : "welcome";
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.dataset.view !== state.view));
  document.querySelectorAll("#tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.view === state.view)));
  $("#tabs").hidden = !state.sid;
  if (state.sid && location.hash.slice(1) !== state.view) history.replaceState(null, "", "#" + state.view);
  if (state.view === "welcome") renderImportForm($("#welcome-import"));
  else VIEWS[state.view]();
}

async function loadSnapshots(selectId) {
  state.snapshots = await getJSON("/api/snapshots");
  if (selectId) state.sid = selectId;
  if (!state.snapshots.some((s) => s.id === state.sid)) state.sid = state.snapshots[0]?.id ?? null;
  $("#snapshot").innerHTML = state.snapshots.map((s) =>
    `<option value="${s.id}">${esc(s.name)} · #${s.id} · ${esc(s.created.slice(0, 10))}</option>`).join("");
  $("#snapshot").hidden = !state.snapshots.length;
  if (state.sid) $("#snapshot").value = state.sid;
  const cur = current();
  $("#subtitle").textContent = cur ? `Appian ${cur.version} · ${fmt(cur.objects)} objects` : "";
  const ok = cur && cur.passed === cur.checks;
  $("#health-btn").hidden = !cur;
  $("#health-btn").className = `chip ${ok ? "ok" : "bad"}`;
  $("#health-btn").textContent = cur ? `${ok ? "✓" : "!"} ${cur.passed}/${cur.checks} checks` : "";
}

// Called when an import finishes: open its snapshot in whichever view is showing.
async function openSnapshot(id) {
  await loadSnapshots(id);
  resetViews();
  show(state.view === "welcome" ? "tests" : state.view);
}

function resetViews() {
  testsState.sid = browseState.sid = null;
  testsState.pick = null;
  browseState.current = null;
  changeState.base = null;
}

async function boot() {
  $("#tabs").addEventListener("click", (e) => { const b = e.target.closest("[data-view]"); if (b) show(b.dataset.view); });
  window.addEventListener("hashchange", () => { if (location.hash.slice(1) !== state.view) show(location.hash.slice(1)); });
  $("#snapshot").addEventListener("change", async (e) => { await loadSnapshots(+e.target.value); resetViews(); show(state.view); });
  $("#health-btn").addEventListener("click", openHealth);
  $("#import-btn").addEventListener("click", openImport);
  await loadSnapshots();
  show(location.hash.slice(1));
  pollJobs();
}

boot();
