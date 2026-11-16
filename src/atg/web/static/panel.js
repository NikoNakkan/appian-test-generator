// The side panel: one drawer on the right for quick looks (an object, a process node, a diff)
// and for Health and Import. Back walks the stack of what was opened; Esc closes it.
const panel = { stack: [], depsSid: null, uses: null, usedBy: null, names: null };
const PREVIEW_LINES = 14;

function openPanel(html, entry) {
  $("#panel-body").innerHTML = html;
  $("#panel").hidden = false;
  $("#panel").scrollTop = 0;
  // Reopening what is already on top (after a decision, say) replaces it, so Back goes back.
  if (entry && JSON.stringify(panel.stack.at(-1)) === JSON.stringify(entry)) panel.stack.pop();
  if (entry) panel.stack.push(entry);
  $("#panel-back").hidden = panel.stack.length < 2;
}

function closePanel() {
  $("#panel").hidden = true;
  panel.stack = [];
}

// Who uses what, for every object: loaded once per snapshot.
async function depsIndex() {
  if (panel.depsSid === state.sid) return;
  const d = await api("dependencies");
  panel.names = new Map(d.objects.map(([u, t, n]) => [u, [t, n]]));
  panel.uses = new Map(); panel.usedBy = new Map();
  for (const [a, b] of d.edges) {
    if (b < 0) continue;
    const ua = d.objects[a][0], ub = d.objects[b][0];
    (panel.uses.get(ua) || panel.uses.set(ua, []).get(ua)).push(ub);
    (panel.usedBy.get(ub) || panel.usedBy.set(ub, []).get(ub)).push(ua);
  }
  panel.depsSid = state.sid;
}

const refLinks = (list, max = 5) => list.slice(0, max).map((u) =>
  `<a href="#" data-panel="${esc(u)}">${esc(panel.names.get(u)?.[1] || u)}</a>`).join(", ") + (list.length > max ? ` +${list.length - max}` : "");

async function panelObject(uuid) {
  const [o, decisions] = await Promise.all([api("object", { uuid }), api("decisions", { uuid }), depsIndex()]);
  if (o.error) return openPanel(`<p class="error">${esc(o.error)}</p>`);
  const d = o.details, facts = [];
  if (d.inputs?.length) facts.push(["Inputs", d.inputs.map((i) => `${mono("ri!" + i.name)} <span class="hint">${esc(i.type)}</span>`).join("<br>")]);
  if (d.constant) facts.push(["Value", `${esc(d.constant.type)} = ${mono(d.constant.values.join(", ") || "empty")}`]);
  if (d.variables?.length) facts.push(["Variables", String(d.variables.length)]);
  if (d.fields?.length) facts.push(["Fields", `${d.fields.length}: ${d.fields.slice(0, 6).map((f) => mono(f.name)).join(", ")}${d.fields.length > 6 ? "…" : ""}`]);
  if (o.entry_points.length) facts.push([o.type === "site" ? "Pages" : "Actions", o.entry_points.map((e) => esc(e.name)).join(", ")]);
  if (decisions.length) facts.push(["Decision points", String(decisions.length)]);
  const usedBy = panel.usedBy.get(uuid) || [], uses = panel.uses.get(uuid) || [];
  if (usedBy.length) facts.push([`Used by (${usedBy.length})`, refLinks(usedBy)]);
  if (uses.length) facts.push([`Uses (${uses.length})`, refLinks(uses)]);
  openPanel(`
    <div class="panel-head">${pill(TYPE[o.type] || o.type)}<h3>${esc(o.name)}</h3></div>
    ${o.description ? `<p class="panel-desc">${esc(o.description)}</p>` : ""}
    ${facts.length ? `<dl class="facts">${facts.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join("")}</dl>` : ""}
    ${o.code.length ? codePreview(o.code) : ""}
    <div class="panel-actions"><button class="primary" data-open-app="${esc(uuid)}">Open in App</button></div>`, { kind: "object", uuid });
}

function codePreview(segments) {
  const lines = segments.map(([t]) => t).join("").split("\n").length;
  if (lines <= PREVIEW_LINES) return renderCode(segments);
  return `<div class="code-preview">${renderCode(segments)}<button class="show-all">Show all ${lines} lines</button></div>`;
}

document.addEventListener("click", (e) => {
  const p = e.target.closest("[data-panel]");
  if (p) { e.preventDefault(); panelObject(p.dataset.panel); return; }
  const open = e.target.closest("[data-open-app]");
  if (open) { e.preventDefault(); closePanel(); openInApp(open.dataset.openApp); return; }
  const all = e.target.closest(".show-all");
  if (all) { all.parentElement.classList.add("open"); all.remove(); }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#panel").hidden) closePanel(); });
document.addEventListener("DOMContentLoaded", () => {
  $("#panel-close").addEventListener("click", closePanel);
  $("#panel-back").addEventListener("click", () => {
    panel.stack.pop();
    const prev = panel.stack.pop();
    if (prev?.kind === "object") panelObject(prev.uuid);
    else if (prev?.kind === "node") showNode(prev.pm, prev.gui);
    else if (prev?.kind === "diff") showDiff(prev.uuid);
    else if (prev?.kind === "health") openHealth();
    else if (prev?.kind === "import") openImport();
    else if (prev?.kind === "draft") openDraft(prev.key);
  });
});
