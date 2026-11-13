// One test's page: for a process, its paths and the diagram with the picked route; then two
// tabs, the UAT scenario (copyable as text) and the test data it needs.
const SCEN_PARTS = [["preconditions", "Before you start"], ["steps", "Steps"], ["expected", "Expected result"], ["to_confirm", "To confirm with the business"]];
const testCache = { pm: null, paths: null, scenario: null };

async function showTest(kind, uuid, path) {
  testsState.pick = { kind, uuid };
  if (path) testsState.path = path;
  document.querySelectorAll("#ts-list .row").forEach((r) => r.setAttribute("aria-current", String(r.dataset.uuid === uuid)));
  const d = testsState.data;
  const item = d.processes.find((p) => p.uuid === uuid) || d.screens.find((s) => s.uuid === uuid) || d.rules.find((r) => r.uuid === uuid);
  if (!item) {
    $("#ts-page").innerHTML = `<div class="page-head"><a href="#" class="back" data-home>← All tests</a></div>
      ${empty("This object has no test of its own: it is part of the screens, processes or rules that use it.")}`;
    return;
  }
  if (kind === "process" && !item.paths.some((p) => p.no === testsState.path)) testsState.path = item.paths[0].no;
  if (kind === "rule") testsState.tab = "data";
  const params = { uuid, path: kind === "process" ? testsState.path : null };
  $("#ts-page").innerHTML = `<p class="hint">Working it out…</p>`;
  const [data, scen, paths] = await Promise.all([
    api("test-data", params),
    kind === "rule" ? null : api("scenario", params),
    kind === "process" && testCache.pm !== uuid ? api("paths", { uuid }) : testCache.paths,
  ]);
  if (testsState.pick?.uuid !== uuid) return;
  Object.assign(testCache, { scenario: scen, pm: kind === "process" ? uuid : testCache.pm, paths });
  const label = { screen: "Screen", process: "Process", rule: "Rule" }[kind];
  $("#ts-page").innerHTML = `
    <div class="page-head"><a href="#" class="back" data-home>← All tests</a>
      <div class="title-row">${pill(label)}<h2>${esc(item.name)}</h2>
        <button data-open-app="${esc(uuid)}">Open in App</button></div></div>
    ${kind === "process" ? processBlock(item) : ""}
    ${kind === "rule" ? "" : segmented("tab", [["scenario", "UAT scenario"], ["data", "Test data"]], testsState.tab)}
    <div class="tab-body">${testsState.tab === "scenario" && scen ? renderScenario(scen)
      : kind === "process" ? renderPathData(data) : kind === "screen" ? renderScreenData(data)
      : renderRuleData(data) || `<p class="hint">No inputs and no data to set up: call it and check the result.</p>`}</div>`;
  if (kind === "process") {
    const box = $("#ts-diagram");
    await drawDiagram(box, uuid);
    highlightPath(box, paths.paths.find((p) => p.no === testsState.path));
  }
}

function processBlock(proc) {
  return `<div class="path-list">${proc.paths.map((p) => `<button class="path-btn" data-path="${p.no}" aria-pressed="${p.no === testsState.path}">
      <b>Path ${p.no}</b><span>${esc(p.route)}</span>${p.tasks ? `<small>${p.tasks} user task${p.tasks > 1 ? "s" : ""}</small>` : ""}</button>`).join("")}</div>
    <div id="ts-diagram" class="diagram"></div>`;
}

function renderScenario(s) {
  if (s.error) return `<p class="hint">${esc(s.error)}</p>`;
  const part = ([k, title]) => s[k].length
    ? `<div class="data-block"><b>${title}</b><${k === "steps" ? "ol" : "ul"} class="needs">${s[k].map((x) => `<li>${esc(x)}</li>`).join("")}</${k === "steps" ? "ol" : "ul"}></div>` : "";
  return `<div class="scenario"><div class="title-row"><b>${esc(s.title)}</b><button class="copy" data-copy>Copy as text</button></div>
    ${SCEN_PARTS.map(part).join("")}</div>`;
}

function scenarioText(s) {
  return [s.title, ...SCEN_PARTS.filter(([k]) => s[k].length).map(([k, title]) =>
    `\n${title}:\n` + s[k].map((x, i) => `${k === "steps" ? `${i + 1}.` : "-"} ${x}`).join("\n"))].join("\n");
}

document.addEventListener("DOMContentLoaded", () => {
  $("#ts-page").addEventListener("click", (e) => {
    const pick = testsState.pick;
    if (e.target.closest("[data-home]")) {
      e.preventDefault(); testsState.pick = null; renderTestList(); return renderTestsHome();
    }
    const c = e.target.closest("[data-copy]");
    if (c) return navigator.clipboard.writeText(scenarioText(testCache.scenario)).then(() => (c.textContent = "Copied"));
    const p = e.target.closest("[data-path]");
    if (p) return showTest("process", pick.uuid, +p.dataset.path);
    const t = e.target.closest("[data-tab]");
    if (t) { testsState.tab = t.dataset.tab; showTest(pick.kind, pick.uuid); }
  });
});
