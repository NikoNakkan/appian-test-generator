// Tests (home): every test on the left (screens, process paths, rules), filtered by kind or by
// feature. With nothing picked, the page shows the summary: counts, test users, feature sign-off.
const testsState = { sid: null, data: null, kind: "all", feature: "", members: null, features: [], pick: null, path: 1, tab: "scenario" };
const KINDS = [["all", "All"], ["screen", "Screens"], ["process", "Processes"], ["rule", "Rules"]];
const SIGNOFF = { approved: "ok", edit: "ok", rejected: "bad", waiting: "idle", "needs re-approval": "ext" };

async function renderTests() {
  if (testsState.sid !== state.sid) {
    [testsState.data, testsState.features] = await Promise.all([api("tests"), api("features")]);
    Object.assign(testsState, { sid: state.sid, feature: "", members: null });
  }
  $("#ts-kinds").innerHTML = segmented("kind", KINDS, testsState.kind);
  $("#ts-feature").innerHTML = `<option value="">All features</option>` + testsState.features.map((f) =>
    `<option value="${esc(f.key)}">${esc(f.name)} · ${esc(f.approval.status)}</option>`).join("");
  $("#ts-feature").value = testsState.feature;
  renderTestList();
  if (testsState.pick) showTest(testsState.pick.kind, testsState.pick.uuid);
  else renderTestsHome();
}

function renderTestList() {
  const d = testsState.data, q = $("#ts-q").value.trim().toLowerCase(), k = testsState.kind;
  const keep = (x) => x.name.toLowerCase().includes(q) && (!testsState.members || testsState.members.has(x.uuid));
  const row = (kind, x, meta) => `<button class="row" data-kind="${kind}" data-uuid="${esc(x.uuid)}"
    aria-current="${testsState.pick?.uuid === x.uuid}"><span>${esc(x.name)}</span><small>${meta}</small></button>`;
  const group = (kind, title, items, meta) => (k === "all" || k === kind) && items.length
    ? `<div class="group-h"><span>${title}</span><span>${items.length}</span></div>${items.map((x) => row(kind, x, meta(x))).join("")}` : "";
  $("#ts-list").innerHTML = [
    group("screen", "Screens", d.screens.filter(keep), (s) => esc(s.how.join(", "))),
    group("process", "Processes", d.processes.filter(keep), (p) => `${fmt(p.path_count)} path${p.path_count > 1 ? "s" : ""}`),
    group("rule", "Rules", d.rules.filter(keep), (r) => `${r.inputs} input${r.inputs === 1 ? "" : "s"}`),
  ].join("") || `<p class="hint pad">No tests match.</p>`;
}

async function renderTestsHome() {
  const d = testsState.data, users = await api("test-users");
  const paths = d.processes.reduce((n, p) => n + p.path_count, 0);
  const counts = testsState.features.reduce((c, f) => ((c[f.approval.status] = (c[f.approval.status] || 0) + 1), c), {});
  $("#ts-page").innerHTML = `
    <div class="page-head"><h2>Tests for ${esc(current().name)}</h2>
      <p class="hint">Pick a test on the left to see its UAT scenario and the data it needs.</p></div>
    <div class="kpis">
      <div class="kpi"><b>${fmt(d.screens.length)}</b><span>screens</span></div>
      <div class="kpi"><b>${fmt(paths)}</b><span>process paths in ${fmt(d.processes.length)} processes</span></div>
      <div class="kpi"><b>${fmt(d.rules.length)}</b><span>rules</span></div>
      <div class="kpi"><b>${fmt(users.length)}</b><span>groups need test users</span></div>
    </div>
    ${section("Feature sign-off", `<p>${testsState.features.length} features proposed from the app's entry points.
        ${Object.entries(counts).map(([s, n]) => pill(`${n} ${s}`, SIGNOFF[s])).join(" ")}</p>
      <p class="hint">A person approves, renames or rejects each feature in an Excel sheet. Filter the list by feature on the left.</p>
      <div class="actions"><a class="button" href="/api/snapshots/${state.sid}/features-sheet">Download sheet</a>
        <label class="button">Upload filled sheet<input type="file" id="sheet-file" accept=".xlsx" hidden></label></div>
      <div id="sheet-result"></div>`)}
    ${section("Test users needed", table(["Group", "User tasks", "Users", "Used in"], users.map((r) => [esc(r.group), fmt(r.tasks), r.users_needed,
      `<span class="hint">${r.processes.slice(0, 3).map(esc).join(", ")}${r.processes.length > 3 ? ` +${r.processes.length - 3}` : ""}</span>`])))}`;
}

async function uploadSheet(file) {
  const out = $("#sheet-result");
  if (!file.name.toLowerCase().endsWith(".xlsx")) { out.innerHTML = `<p class="error">Upload the .xlsx sheet.</p>`; return; }
  try {
    const r = await getJSON(`/api/snapshots/${state.sid}/features-sheet`, { method: "POST", body: file });
    testsState.features = await api("features");
    await renderTestsHome();
    $("#sheet-result").innerHTML = `<p>${r.applied} decision${r.applied === 1 ? "" : "s"} saved, ${r.skipped_blank} left blank.</p>` +
      (r.problems.length ? `<ul class="error">${r.problems.map((p) => `<li>${esc(p)}</li>`).join("")}</ul>` : "");
  } catch (e) { out.innerHTML = `<p class="error">${esc(e.message)}</p>`; }
}

async function pickFeature(key) {
  testsState.feature = key;
  testsState.members = key ? new Set((await api("feature", { key })).members.map((m) => m.uuid)) : null;
  renderTestList();
}

document.addEventListener("DOMContentLoaded", () => {
  $("#ts-q").addEventListener("input", renderTestList);
  $("#ts-feature").addEventListener("change", (e) => pickFeature(e.target.value));
  $("#ts-kinds").addEventListener("click", (e) => {
    const b = e.target.closest("[data-kind]");
    if (b) { testsState.kind = b.dataset.kind; $("#ts-kinds").innerHTML = segmented("kind", KINDS, testsState.kind); renderTestList(); }
  });
  $("#ts-list").addEventListener("click", (e) => { const b = e.target.closest("[data-uuid]"); if (b) showTest(b.dataset.kind, b.dataset.uuid); });
  $("#ts-page").addEventListener("change", (e) => { if (e.target.id === "sheet-file" && e.target.files[0]) uploadSheet(e.target.files[0]); });
});
