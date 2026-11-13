// Shared by every view: state, fetch, escaping, labels for Appian types, small HTML builders.
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n) => (n == null ? "–" : Number(n).toLocaleString("en-US"));
const trunc = (s, m) => (s.length > m ? s.slice(0, m - 1) + "…" : s);

// The one piece of app state: which snapshot is open and which view shows it.
const state = { snapshots: [], sid: null, view: "tests" };
const current = () => state.snapshots.find((s) => s.id === state.sid);
const api = (view, params = {}) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== "")).toString();
  return getJSON(`/api/snapshots/${state.sid}/${view}${q ? "?" + q : ""}`);
};

async function getJSON(url, options) {
  const res = await fetch(url, options);
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `Request failed (${res.status})`);
  return body;
}

const TYPE = { rule: "Expression rule", interface: "Interface", constant: "Constant", processModel: "Process",
  recordType: "Record type", integration: "Integration", group: "Group", site: "Site", datatype: "Data type",
  decision: "Decision", report: "Report", connectedSystem: "Connected system", webApi: "Web API", dataStore: "Data store" };
const TYPE_ORDER = ["processModel", "interface", "rule", "decision", "constant", "recordType", "datatype",
  "integration", "connectedSystem", "webApi", "dataStore", "group", "site", "report"];
const rank = (t) => { const r = TYPE_ORDER.indexOf(t); return r < 0 ? 99 : r; };
const KIND = { if: "If / else", null_check: "Empty check", compare: "Comparison", ui_condition: "Screen condition",
  loop: "Loop (0, 1, many)", or: "Any of (or)", and: "All of (and)", match: "Match", choose: "Choose" };

const mono = (t) => `<code class="code-inline">${esc(t)}</code>`;
const pill = (text, kind = "idle") => `<span class="pill ${kind}">${esc(text)}</span>`;
function section(title, body) { return body ? `<div class="dz-section"><h4>${title}</h4>${body}</div>` : ""; }
function table(headers, rows) {
  if (!rows.length) return "";
  return `<div class="table-wrap"><table><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr>${rows.map((r) =>
    `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</table></div>`;
}
const empty = (text) => `<div class="empty">${text}</div>`;

// Segmented control: [["scenario", "Scenario"], ...] with one pressed.
const segmented = (name, options, picked) => `<div class="seg" role="tablist">${options.map(([v, l]) =>
  `<button role="tab" data-${name}="${v}" aria-selected="${v === picked}">${l}</button>`).join("")}</div>`;
