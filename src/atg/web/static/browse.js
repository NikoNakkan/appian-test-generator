// App: every object read-only, grouped by type, as in Appian Designer. A process shows its
// diagram first; every page shows what it uses, what uses it, and links to its tests.
const browseState = { sid: null, objects: null, current: null };

async function renderBrowse() {
  if (browseState.sid !== state.sid) {
    browseState.objects = (await api("dependencies")).objects;
    browseState.sid = state.sid;
  }
  const q = $("#app-q").value.trim().toLowerCase();
  const rows = browseState.objects.filter(([, , n]) => n.toLowerCase().includes(q))
    .sort((a, b) => rank(a[1]) - rank(b[1]) || a[2].localeCompare(b[2]));
  const groups = new Map();
  rows.forEach((r) => (groups.get(r[1]) || groups.set(r[1], []).get(r[1])).push(r));
  $("#app-list").innerHTML = [...groups].map(([t, rs]) =>
    `<div class="group-h"><span>${esc(TYPE[t] || t)}</span><span>${rs.length}</span></div>` +
    rs.map(([u, , n]) => `<button class="row" data-uuid="${esc(u)}" aria-current="${u === browseState.current}">${esc(n)}</button>`).join("")
  ).join("") || `<p class="hint pad">No objects match.</p>`;
  const first = rows.find(([, t]) => t === "processModel") || rows[0];
  if (browseState.current || first) showObject(browseState.current || first[0]);
}

function openInApp(uuid) {
  browseState.current = uuid;
  show("app");
}

async function showObject(uuid) {
  browseState.current = uuid;
  document.querySelectorAll("#app-list .row").forEach((r) => r.setAttribute("aria-current", String(r.dataset.uuid === uuid)));
  const [o, decisions] = await Promise.all([api("object", { uuid }), api("decisions", { uuid }), depsIndex()]);
  if (browseState.current !== uuid) return;
  if (o.error) { $("#app-page").innerHTML = `<p class="error">${esc(o.error)}</p>`; return; }
  const d = o.details, uses = panel.uses.get(uuid) || [], usedBy = panel.usedBy.get(uuid) || [];
  const tested = o.type === "processModel" || o.type === "interface" || o.type === "rule" || o.type === "decision";
  const refs = (list) => list.length ? `<div class="ref-list">${list.map((u) => `<a href="#" data-panel="${esc(u)}">
    <span class="hint">${esc(TYPE[panel.names.get(u)?.[0]] || "")}</span> ${esc(panel.names.get(u)?.[1] || u)}</a>`).join("")}</div>` : "";
  $("#app-page").innerHTML = `
    <div class="page-head"><div class="title-row">${pill(TYPE[o.type] || o.type)}<h2>${esc(o.name)}</h2>
      ${tested ? `<button data-tests="${esc(uuid)}" data-tkind="${o.type === "processModel" ? "process" : o.type === "interface" ? "screen" : "rule"}">See its tests</button>` : ""}</div>
      ${o.description ? `<p class="hint">${esc(o.description)}</p>` : ""}</div>
    ${o.type === "processModel" ? `<div id="app-diagram" class="diagram"></div>` : ""}
    ${section("Rule inputs", table(["Name", "Type", "Description"], (d.inputs || []).map((i) => [mono(i.name), esc(i.type), esc(i.description)])))}
    ${d.constant ? section("Value", `<p>${esc(d.constant.type)} = ${d.constant.values.map(mono).join(", ") || "<i>empty</i>"}</p>`) : ""}
    ${section("Process variables", table(["Name", "Type", "Parameter", "Required"], (d.variables || []).map((v) => [mono("pv!" + v.name), esc(v.type), v.parameter ? "yes" : "", v.required ? "yes" : ""])))}
    ${section("Fields", table(["Name", "Label", "Type", ""], (d.fields || []).map((f) => [mono(f.name), esc(f.label || ""), esc(f.type), (f.is_id ? "record id " : "") + (f.segments?.length ? renderCode(f.segments, { inline: true }) : "")])))}
    ${o.code.length ? section(o.type === "interface" ? "Interface definition" : "Definition", renderCode(o.code)) : ""}
    ${(d.views || []).map((v) => section(`View: ${esc(v.name)}`, renderCode(v.segments))).join("")}
    ${section(o.type === "site" ? "Pages" : "Actions", table(["Kind", "Title", "Opens"], o.entry_points.map((e) => [esc(e.kind), esc(e.name),
      e.target_name === "outside this export" ? `<span class="hint">outside this export</span>` : `<a href="#" data-panel="${esc(e.target)}">${esc(e.target_name)}</a>`])))}
    ${section(`Decision points (${decisions.length})`, table(["Kind", "Condition", "Ways"], decisions.slice(0, 80).map((x) =>
      [esc(KIND[x.kind] || x.kind), mono(x.condition), `${x.outcomes}${x.literals.length ? ` · ${esc(x.literals.join(", "))}` : ""}`])))}
    ${section(`Uses (${uses.length})`, refs(uses))}
    ${section(`Used by (${usedBy.length})`, refs(usedBy))}
    <details class="more">${`<summary>All settings</summary>`}${table(["Setting", "Value"], (d.settings || []).map((s) =>
      [esc(s.label), s.segments ? renderCode(s.segments, { inline: true }) : esc(s.value)])) || `<p class="hint">None.</p>`}</details>`;
  if (o.type === "processModel") drawDiagram($("#app-diagram"), uuid);
}

document.addEventListener("DOMContentLoaded", () => {
  $("#app-q").addEventListener("input", renderBrowse);
  $("#app-list").addEventListener("click", (e) => { const b = e.target.closest("[data-uuid]"); if (b) showObject(b.dataset.uuid); });
  $("#app-page").addEventListener("click", (e) => {
    const t = e.target.closest("[data-tests]");
    if (t) { testsState.pick = { kind: t.dataset.tkind, uuid: t.dataset.tests }; show("tests"); }
  });
});
