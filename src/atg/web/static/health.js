// Health: is the map complete? Each layer with its checks, the decision points found, and how
// the numbers moved since the previous import. Opens in the side panel from the checks chip.
const METRIC = { objects: "Objects", processes: "Processes", nodes: "Process nodes", flows: "Connections",
  gateway_rules: "Gateway rules", references: "References", external: "Outside dependencies", unknowns: "Unknowns",
  sail_parsed: "SAIL sources parsed", decisions: "Decision points", paths: "Test paths" };

async function openHealth() {
  const [p, checks] = await Promise.all([api("progress"), api("checks")]);
  const most = Math.max(1, ...p.decisions.map((d) => d.count));
  openPanel(`<div class="panel-head"><h3>Health of the map</h3>
      <p class="hint">A layer is done when all its checks pass: each compares what was stored with counts taken from the raw files.</p></div>
    <div class="layers">${p.layers.map((l) => layerRow(l, checks.filter((c) => c.layer === l.layer))).join("")}</div>
    ${section("Decision points", p.decisions.map((d) => `<div class="kind-row"><span>${esc(KIND[d.kind] || d.kind)}</span>
      <span class="kind-bar"><span style="width:${Math.round((d.count / most) * 100)}%"></span></span>
      <span class="nums">${fmt(d.count)}</span></div>`).join(""))}
    ${section("Since the previous import", ratchet(p.ratchet))}`, { kind: "health" });
}

function layerRow(l, checks) {
  const status = { passing: "ok", failing: "bad" }[l.status] || "idle";
  const head = `<span class="n">${l.layer}</span><div><b>${esc(l.name)}</b><small>${esc(l.detail || l.goal)}</small></div>${pill(l.status, status)}`;
  if (!checks.length) return `<div class="layer">${head}</div>`;
  return `<details class="layer-box ${status}" ${checks.some((c) => !c.ok) ? "open" : ""}><summary class="layer">${head}</summary>
    <div class="checks">${checks.map((c) => `<div class="check">${pill(c.ok ? "PASS" : "FAIL", c.ok ? "ok" : "bad")}
      <span>${esc(c.name)}</span><span class="nums">raw ${fmt(c.expected)} · stored ${fmt(c.actual)}</span>
      ${c.details.length ? `<div class="details">${c.details.map(esc).join("\n")}</div>` : ""}</div>`).join("")}</div></details>`;
}

function ratchet(rows) {
  if (rows.every((r) => r.before == null)) return `<p class="hint">First import of this app: nothing to compare yet.</p>`;
  return table(["Metric", "Before", "Now", "Change"], rows.map((r) => {
    const d = r.now - r.before, worse = r.metric === "unknowns" ? d > 0 : d < 0;
    const cls = d === 0 ? "same" : worse ? "down" : "up";
    return [METRIC[r.metric] || r.metric, fmt(r.before), fmt(r.now),
      `<span class="delta ${cls}">${d === 0 ? "same" : (d > 0 ? "+" : "") + fmt(d)}${worse ? " · check this" : ""}</span>`];
  }));
}
