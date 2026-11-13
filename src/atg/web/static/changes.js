// Changes: compare this snapshot with an earlier one of the same app, and list the tests to run.
const changeState = { base: null, data: null };
const VERDICT_PILL = { rerun: "ext", new: "ok", redesign: "bad", retire: "idle", skip: "idle" };

async function renderChanges() {
  const q = changeState.base ? `?base=${changeState.base}` : "";
  const r = (changeState.data = await getJSON(`/api/snapshots/${state.sid}/changes${q}`));
  const older = state.snapshots.filter((s) => s.id < state.sid);
  const head = `<div class="page-head"><div class="title-row"><h2>Changes and tests to rerun</h2>
      ${older.length ? `<label class="inline">Compare with <select id="chg-base">${older.map((s) =>
        `<option value="${s.id}">${esc(s.name)} · #${s.id} · ${esc(s.created.slice(0, 10))}</option>`).join("")}</select></label>` : ""}</div>
    <p class="hint">What changed since an earlier import of this app, what that affects through its dependencies, and which tests to rerun.</p></div>`;
  if (r.error) { $("#chg-page").innerHTML = head + empty(esc(r.error)); return; }
  const count = (kind, verdict) => r.summary[kind]?.[verdict] || 0;
  const tiles = [[r.changes.length, "objects changed"], [r.affected.length, "affected through dependencies"],
    [count("path", "rerun"), "test paths to rerun", "ext"], [count("path", "new"), "new test paths"],
    [count("path", "retire"), "paths to retire"], [count("path", "skip"), "paths unaffected"]];
  $("#chg-page").innerHTML = head + `
    <div class="kpis">${tiles.map(([v, l, c]) => `<div class="kpi ${c || ""}"><b>${fmt(v)}</b><span>${l}</span></div>`).join("")}</div>
    <div class="card"><h3>What changed</h3><p class="sub">Click one to see the difference.</p>
      ${r.changes.length ? `<div class="change-list">${r.changes.map((c) => `<button class="change-row" data-diff="${esc(c.uuid)}" data-status="${c.status}">
        <span class="pill ${c.status === "removed" ? "bad" : c.status === "added" ? "ok" : "ext"}">${c.status}</span>
        <span class="hint">${esc(TYPE[c.type] || c.type)}</span><b>${esc(c.name)}</b></button>`).join("")}</div>`
        : `<div class="empty">Nothing changed between these two snapshots.</div>`}
      ${r.affected.length ? `<details class="affected"><summary>${r.affected.length} objects affected through dependencies</summary>
        <div class="table-wrap"><table><tr><th>Object</th><th>Why</th></tr>${r.affected.map((a) => `<tr>
          <td><a href="#" data-panel="${esc(a.uuid)}">${esc(a.name)}</a> <span class="hint">${esc(TYPE[a.type] || a.type)}</span></td>
          <td class="hint">uses ${a.via.map(esc).join(" → ")}</td></tr>`).join("")}</table></div></details>` : ""}
    </div>
    ${section2("Features to retest", r.features, (v) => `<b>${esc(v.item)}</b>`)}
    <div class="card"><h3>Test paths</h3>
      <p class="sub">A path reruns when it passes through a changed node, or a node that uses something changed. ${fmt(count("path", "skip"))} paths are unaffected and skipped.</p>
      ${r.processes.length ? r.processes.map((p) => `<details class="proc"><summary><b>${esc(p.name)}</b>
          ${["rerun", "new", "retire"].map((v) => { const n = p.paths.filter((x) => x.verdict === v).length; return n ? `<span class="pill ${VERDICT_PILL[v]}">${n} ${v}</span>` : ""; }).join(" ")}
          <a href="#" data-open-app="${esc(p.uuid)}">open</a></summary>
        ${p.paths.map((x) => `<div class="verdict"><span class="pill ${VERDICT_PILL[x.verdict]}">${x.verdict}</span><span>${esc(x.item)}</span>
          <span class="hint">${x.reasons.map(esc).join("; ")}</span></div>`).join("")}</details>`).join("")
        : `<div class="empty">No test path is affected.</div>`}
    </div>
    ${section2("Rule and screen tests", r.rules, (v) => `<a href="#" data-panel="${esc(v.ref)}">${esc(v.item)}</a> <span class="hint">${esc(TYPE[v.owner] || v.owner)}</span>`)}`;
  if ($("#chg-base")) $("#chg-base").value = r.base;
}

function section2(title, rows, name) {
  if (!rows.length) return "";
  return `<div class="card"><h3>${title}</h3>${rows.map((v) => `<div class="verdict">
    <span class="pill ${VERDICT_PILL[v.verdict]}">${v.verdict}</span><span>${name(v)}</span>
    <span class="hint">${v.reasons.map(esc).join("; ")}</span></div>`).join("")}</div>`;
}

async function showDiff(uuid) {
  const r = changeState.data;
  const c = r.changes.find((x) => x.uuid === uuid);
  if (c.status !== "changed") {
    openPanel(`<div class="panel-head"><span class="pill idle">${esc(TYPE[c.type] || c.type)}</span><h3>${esc(c.name)}</h3></div>
      <p>This object was ${c.status}.</p>${c.status === "added" ? `<button data-open-app="${esc(uuid)}">Open in App</button>` : ""}`);
    return;
  }
  const d = await getJSON(`/api/snapshots/${state.sid}/object-diff?uuid=${encodeURIComponent(uuid)}&base=${r.base}`);
  openPanel(`<div class="panel-head"><span class="pill idle">${esc(TYPE[c.type] || c.type)}</span><h3>${esc(c.name)}</h3>
      <div class="hint">snapshot #${r.base} → #${r.head}</div></div>
    ${d.parts.map((p) => `<div class="dz-section"><h4>${esc(p.label)}</h4><pre class="code diff">${p.lines.map((l) =>
      `<span class="${l.startsWith("+") ? "add" : l.startsWith("-") ? "del" : l.startsWith("@@") ? "hunk" : ""}">${esc(l)}</span>`).join("\n")}</pre></div>`).join("")
      || `<p class="hint">Only housekeeping changed.</p>`}
    <div class="panel-actions"><button data-open-app="${esc(uuid)}">Open in App</button></div>`, { kind: "diff", uuid });
}

document.addEventListener("DOMContentLoaded", () => {
  $("#chg-page").addEventListener("change", (e) => {
    if (e.target.id === "chg-base") { changeState.base = +e.target.value || null; renderChanges(); }
  });
  $("#chg-page").addEventListener("click", (e) => { const d = e.target.closest("[data-diff]"); if (d) showDiff(d.dataset.diff); });
});
