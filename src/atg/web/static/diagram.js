// A process diagram: nodes left to right by distance from the start, gateways as hexagons.
// Drawn into any container (Tests shows a path on it, App shows the whole process); clicking a
// node opens its properties in the side panel.
const NODE_COLOR = { gate: "var(--c-gate)", user: "var(--c-user)", sub: "var(--c-sub)", svc: "var(--c-svc)", end: "var(--faint)" };
const LEGEND = [["end", "Start / end"], ["gate", "Gateway"], ["user", "User task"], ["sub", "Sub-process"], ["svc", "Automatic"]];

function nodeKind(id) {
  if (id === "core.0" || id === "core.1") return "end";
  if (["core.2", "core.3", "core.4", "core.5"].includes(id)) return "gate";
  if (id === "internal.17") return "user";
  if (id === "internal.38") return "sub";
  return "svc";
}

async function drawDiagram(box, pm) {
  const { nodes, flows } = await api("process", { uuid: pm });
  const has = new Set(nodes.map((n) => n[0]));
  const conns = flows.filter((f) => f[2] === 0 && has.has(f[0]) && has.has(f[1]));
  const next = new Map(); conns.forEach((f) => (next.get(f[0]) || next.set(f[0], []).get(f[0])).push(f[1]));
  const depth = new Map(), queue = nodes.filter((n) => n[1] === "core.0").map((n) => n[0]);
  queue.forEach((g) => depth.set(g, 0));
  while (queue.length) { const g = queue.shift(); for (const t of next.get(g) || []) if (!depth.has(t)) { depth.set(t, depth.get(g) + 1); queue.push(t); } }
  let maxD = Math.max(0, ...depth.values()); nodes.forEach((n) => { if (!depth.has(n[0])) depth.set(n[0], ++maxD); });
  const cols = new Map(); nodes.forEach((n) => { const d = depth.get(n[0]); (cols.get(d) || cols.set(d, []).get(d)).push(n[0]); });
  const CW = 170, RH = 78, PAD = 36, nw = 132, nh = 40, tallest = Math.max(1, ...[...cols.values()].map((c) => c.length));
  const W = PAD * 2 + (maxD + 1) * CW, H = PAD * 2 + tallest * RH + 30, pos = new Map();
  cols.forEach((c, d) => c.forEach((g, k) => pos.set(g, [PAD + d * CW + nw / 2, PAD + (H - PAD * 2 - c.length * RH) / 2 + k * RH + nh / 2])));
  const rule = (a, b) => flows.find((f) => f[2] === 1 && f[0] === a && f[1] === b);
  const dflt = (a, b) => flows.some((f) => f[2] === 2 && f[0] === a && f[1] === b);
  let s = `<svg width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="Process diagram">
    <defs><marker id="ah" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M1 1L9 5L1 9" fill="none" stroke="var(--c-edge)" stroke-width="1.6"/></marker></defs>`;
  conns.forEach(([a, b, , lab]) => {
    const [x1, y1] = pos.get(a), [x2, y2] = pos.get(b), back = depth.get(b) <= depth.get(a);
    const r = rule(a, b), tag = r ? r[3] || "rule" : dflt(a, b) ? "default" : lab;
    const yb = Math.max(y1, y2) + nh / 2 + 22;
    const d = back ? `M${x1} ${y1 + nh / 2} C ${x1} ${yb}, ${x2} ${yb}, ${x2} ${y2 + nh / 2 + 4}`
      : `M${x1 + nw / 2} ${y1} C ${x1 + nw / 2 + 30} ${y1}, ${x2 - nw / 2 - 30} ${y2}, ${x2 - nw / 2 - 3} ${y2}`;
    s += `<path data-edge="${a}-${b}" d="${d}" fill="none" stroke="var(--c-edge)" stroke-width="1.2" ${back ? 'stroke-dasharray="4 3"' : ""} marker-end="url(#ah)"/>`;
    if (tag) s += `<text x="${(x1 + x2) / 2}" y="${back ? yb - 4 : (y1 + y2) / 2 - 6}" font-size="11" text-anchor="middle" fill="${r ? "var(--c-gate)" : "var(--muted)"}">${esc(tag.slice(0, 18))}</text>`;
  });
  nodes.forEach(([g, id, lab]) => {
    const [x, y] = pos.get(g), col = NODE_COLOR[nodeKind(id)], l = x - nw / 2, r = x + nw / 2, t = y - nh / 2, b = y + nh / 2;
    s += `<g data-node="${g}" style="cursor:pointer" tabindex="0" role="button" aria-label="${esc(lab)}">`;
    s += nodeKind(id) === "gate"
      ? `<polygon points="${l + 12},${t} ${r - 12},${t} ${r},${y} ${r - 12},${b} ${l + 12},${b} ${l},${y}" fill="var(--panel)" stroke="${col}" stroke-width="2"/>`
      : `<rect x="${l}" y="${t}" width="${nw}" height="${nh}" rx="${nodeKind(id) === "end" ? nh / 2 : 7}" fill="var(--panel)" stroke="${col}" stroke-width="1.6"/>`;
    s += `<rect x="${l + 12}" y="${y - 4}" width="8" height="8" rx="2" fill="${col}"/><text x="${l + 26}" y="${y + 4}" font-size="11.5" fill="var(--ink)">${esc(trunc(lab, 16))}</text></g>`;
  });
  box.innerHTML = `<div class="flow" data-pm="${esc(pm)}">${s}</svg></div>
    <div class="legend">${LEGEND.map(([k, l]) => `<span><i style="background:${NODE_COLOR[k]}"></i>${l}</span>`).join("")}
      <span class="hint">Click a node for its properties.</span></div>`;
}

// Dim everything except one test path's route (null clears it).
function highlightPath(box, path) {
  const svg = box.querySelector("svg");
  if (!svg) return;
  const nodes = new Set(path ? path.steps : []);
  const edges = new Set(path ? path.steps.slice(1).map((s, i) => `${path.steps[i]}-${s}`) : []);
  if (path) path.decisions.forEach((d) => edges.add(`${d.gateway}-${d.to}`));
  svg.classList.toggle("has-path", !!path);
  svg.querySelectorAll("[data-node]").forEach((g) => g.classList.toggle("on-path", nodes.has(+g.dataset.node)));
  svg.querySelectorAll("[data-edge]").forEach((e) => e.classList.toggle("on-path", edges.has(e.dataset.edge)));
}

const nodeAt = (e) => { const g = e.target.closest(".flow [data-node]"); return g && [g.closest(".flow").dataset.pm, +g.dataset.node]; };
document.addEventListener("click", (e) => { const n = nodeAt(e); if (n) showNode(...n); });
document.addEventListener("keydown", (e) => {
  const n = (e.key === "Enter" || e.key === " ") && nodeAt(e);
  if (n) { e.preventDefault(); showNode(...n); }
});
