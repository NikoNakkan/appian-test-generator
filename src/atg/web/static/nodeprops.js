// A process node's properties in the side panel, in tabs like Designer's node dialog (read-only).
const nodeState = { data: null, pm: null, tab: "General" };

async function showNode(pm, gui) {
  const n = await api("node", { uuid: pm, gui });
  nodeState.pm = pm;
  if (n.error) { openPanel(`<p class="hint">${esc(n.error)}</p>`); return; }
  nodeState.data = n;
  const tabs = nodeTabs(n);
  if (!tabs.some(([t]) => t === nodeState.tab)) nodeState.tab = tabs[1]?.[0] || "General";
  const html = `<div class="panel-head"><span class="pill idle">${esc(n.type_name)}</span>
      <h3>${esc(n.label)}</h3><div class="mono hint">node ${n.gui} · ${esc(n.type_id)}</div></div>
    <div class="node-tabs" role="tablist">${tabs.map(([t]) => `<button role="tab" data-ntab="${t}" aria-selected="${t === nodeState.tab}">${t}</button>`).join("")}</div>
    <div class="node-body">${(tabs.find(([t]) => t === nodeState.tab) || tabs[0])[1]}</div>`;
  const top = panel.stack.at(-1);
  const same = top?.kind === "node" && top.pm === pm && top.gui === gui;
  openPanel(html, same ? null : { kind: "node", pm, gui });
}

function nodeTabs(n) {
  const tabs = [["General", `<table><tr><th>Name</th><td>${esc(n.label)}</td></tr>
      <tr><th>Node type</th><td>${esc(n.type_name)}</td></tr>
      ${n.calls ? `<tr><th>Starts process</th><td>${n.calls.name === "outside this export" ? `<span class="hint">a process outside this export</span>` : `<a href="#" data-panel="${esc(n.calls.uuid)}">${esc(n.calls.name)}</a>`}</td></tr>` : ""}
    </table>`]];
  if (n.is_gateway && n.rules.length) {
    tabs.push(["Conditions", n.rules.map((r) => `<div class="cond-row"><span class="pill ${r.kind === "gateway_default" ? "ext" : "ok"}">${esc(r.label)}</span>
      <span>→ <b>${esc(r.to)}</b> when ${r.phrase ? esc(r.phrase) : r.kind === "gateway_default" ? "no rule above is true" : "always"}
        ${r.segments.length ? `<br>${renderCode(r.segments, { inline: true })}` : ""}</span></div>`).join("")]);
  }
  if (n.inputs.length) tabs.push(["Data", inputsTable(n.inputs)]);
  if (n.outputs.length) {
    tabs.push(["Outputs", `<table><tr><th>Saves into</th><th>Expression</th></tr>${n.outputs.map((o) =>
      `<tr><td><code class="code-inline">pv!${esc(o.target)}</code></td><td>${renderCode(o.segments)}</td></tr>`).join("")}</table>`]);
  }
  if (n.form.length && (n.is_task || n.type_id === "core.0")) tabs.push(["Form", renderCode(n.form)]);
  if (n.is_task) {
    tabs.push(["Assignment", n.assignees.length
      ? `<ul>${n.assignees.map((a) => `<li>${esc(a)}</li>`).join("")}</ul>`
      : `<p class="hint">No group set on the task (assigned through its lane or at run time).</p>`]);
  }
  return tabs;
}

function inputsTable(inputs, depth = 0) {
  const rows = inputs.map((i) => `<tr>
      <td style="padding-left:${8 + depth * 18}px"><code class="code-inline">${esc(i.name)}</code></td>
      <td class="hint">${esc(i.type)}</td>
      <td>${i.segments.length ? renderCode(i.segments, { inline: true }) : i.value ? `<code class="code-inline">${esc(i.value)}</code>` : ""}</td>
      <td>${i.saves_into ? `<code class="code-inline">pv!${esc(i.saves_into)}</code>` : ""}</td></tr>
      ${i.children.length ? inputsTable(i.children, depth + 1).replace(/^<table>[\s\S]*?<\/tr>|<\/table>$/g, "") : ""}`).join("");
  return depth ? rows : `<table><tr><th>Input</th><th>Type</th><th>Value</th><th>Saves into</th></tr>${rows}</table>`;
}

document.addEventListener("DOMContentLoaded", () => {
  $("#panel").addEventListener("click", (e) => {
    const b = e.target.closest("[data-ntab]");
    if (b && nodeState.data) { nodeState.tab = b.dataset.ntab; showNode(nodeState.pm, nodeState.data.gui); }
  });
});
