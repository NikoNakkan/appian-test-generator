// The data a test needs, as shown in Tests: per process path, per screen, per rule.
function typeCell(v) {
  const fields = v.fields?.length
    ? `<details class="fields"><summary>${esc(v.type)} · ${v.fields.length} fields</summary>
        <div class="field-grid">${v.fields.map((f) => `<span><code class="code-inline">${esc(f.name)}</code> <span class="hint">${esc(f.type)}</span></span>`).join("")}</div></details>`
    : esc(v.type) + (v.kind === "outside this export" ? ` <span class="hint">(from another app, fields unknown)</span>` : "");
  return fields;
}

function dataTable(rows, cols) {
  if (!rows.length) return "";
  return `<div class="table-wrap"><table><tr>${cols.map(([h]) => `<th>${h}</th>`).join("")}</tr>${rows.map((r) =>
    `<tr>${cols.map(([, f]) => `<td>${f(r)}</td>`).join("")}</tr>`).join("")}</table></div>`;
}

function namedList(items) {
  return items.map((x) => x.uuid ? `<a href="#" data-panel="${esc(x.uuid)}">${esc(x.name)}</a>` : esc(x.name)).join(", ");
}

// Record types with where their rows go: table, sync, related records, computed fields.
function recordTable(items) {
  return dataTable(items, [
    ["Record", (r) => `<a href="#" data-panel="${esc(r.uuid)}">${esc(r.name)}</a>`],
    ["Rows go in", (r) => r.source === "RDBMS_TABLE" ? `table <code class="code-inline">${esc(r.table)}</code>${r.sync?.frequency ? `<br><span class="hint">synced record: sync after inserting</span>` : ""}`
      : r.source === "EXPRESSION" ? `<span class="hint">an expression or API: fake it</span>` : `<span class="hint">${esc(r.source || "unknown")}</span>`],
    ["Related records", (r) => r.related.map((x) => `${esc(x.name)} <span class="hint">${esc(x.kind.replace(/_/g, " ").toLowerCase())}</span>`).join("<br>")],
    ["Appian calculates", (r) => r.computed.map(esc).join(", ")],
  ]);
}

const inputCols = [["Input", (v) => `<code class="code-inline">ri!${esc(v.name)}</code>`], ["Type", typeCell],
  ["Values to try", (v) => esc(v.try.join("; ")) || `<span class="hint">any valid value</span>`],
  ["Saved by developers", (v) => v.saved.map((x) => `<code class="code-inline">${esc(x)}</code>`).join("<br>")]];

function block(title, body) { return body ? `<div class="data-block"><b>${title}</b>${body}</div>` : ""; }

function renderPathData(d) {
  if (d.error) return `<p class="error">${esc(d.error)}</p>`;
  const needs = [...new Set(d.conditions.flatMap((c) => c.needs))];
  return [
    block("Start the process with", dataTable(d.start_inputs, [["Input", (v) => `<code class="code-inline">${esc(v.name)}</code>`], ["Type", typeCell]])
      || `<p class="hint">No start inputs.</p>`),
    block("The data must be such that", needs.length ? `<ul class="needs">${needs.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : ""),
    block("Variables those conditions use", dataTable(d.condition_variables, [["Variable", (v) => `<code class="code-inline">${esc(v.name)}</code>`], ["Type", typeCell]])),
    block("People fill in", d.user_tasks.map((t) => `<div class="task-fill"><div>${esc(t.task)} <span class="hint">· ${t.groups.length ? t.groups.map(esc).join(", ") : "no group set"}</span></div>
      <div class="hint">${t.fills.map((f) => `<code class="code-inline">${esc(f.variable)}</code> ← ${f.where?.length ? f.where.map(esc).join(", ") : `form value <code class="code-inline">${esc(f.from_form)}</code>`}`).join("<br>")}</div></div>`).join("")),
    block("Set by the process itself (no data needed)", d.computed.length ? `<p class="hint">${d.computed.map((c) => `<code class="code-inline">${esc(c.variable)}</code> by ${esc(c.by)}`).join(", ")}</p>` : ""),
    block("Database records it reads", recordTable(d.records_read)),
    block("Records it writes", d.records_written.length ? `<p>${namedList(d.records_written)}</p>` : ""),
    block("Records it deletes", d.records_deleted.length ? `<p>${namedList(d.records_deleted)}</p>` : ""),
    block("Outside systems it calls", d.outside_systems.length ? `<p>${namedList(d.outside_systems)}</p><p class="hint">Need a test version or a fake.</p>` : ""),
    block("Sub-processes it starts (tested on their own)", d.subprocesses.length ? `<p>${namedList(d.subprocesses)}</p>` : ""),
  ].join("");
}

function renderScreenData(d) {
  return [
    block("How people get here", `<ul class="needs">${d.routes.map((r) => `<li><b>${esc(r.how)}</b>: ${esc(r.where)}${r.url ? `<br><code class="code-inline">${esc(r.url)}</code>` : ""}</li>`).join("")}</ul>`),
    block("Inputs it is opened with", dataTable(d.inputs, inputCols) || `<p class="hint">No inputs.</p>`),
    block("Fields a person fills in", dataTable(d.fields, [
      ["Label", (f) => f.label ? (f.computed_label ? `<span class="hint">computed:</span> <code class="code-inline">${esc(f.label)}</code>` : `<b>${esc(f.label)}</b>`) : `<span class="hint">no label</span>`],
      ["Kind", (f) => esc(f.kind) + (f.choices.length ? `<br><span class="hint">${f.choices.map(esc).join(" / ")}</span>` : "")],
      ["Input", (f) => f.inputs.map((i) => `<code class="code-inline">${esc(i)}</code>`).join(" ")],
      ["Rules", (f) => [f.required && "required", f.conditional && "shown sometimes"].filter(Boolean).join(", ")],
      ["Defined in", (f) => `<span class="hint">${esc(f.in)}</span>`],
    ])),
    block("Buttons and actions", dataTable(d.actions, [["Label", (a) => `<b>${esc(a.label)}</b> <span class="hint">${esc(a.kind)}</span>`],
      ["What it does", (a) => a.does.map(esc).join("<br>")]])),
    block("Files to upload", d.file_uploads ? `<p>${d.file_uploads} upload field${d.file_uploads > 1 ? "s" : ""}: have sample files ready.</p>` : ""),
    block("Built from", d.parts ? `<p>${d.parts} smaller interface${d.parts > 1 ? "s" : ""}</p>` : ""),
    block("Database records it reads", recordTable(d.records_read)),
    block("Records its buttons write", d.records_written.length ? `<p>${namedList(d.records_written)}</p>` : ""),
    block("Records its buttons delete", d.records_deleted.length ? `<p>${namedList(d.records_deleted)}</p>` : ""),
    block("Outside systems it calls", d.outside_systems.length ? `<p>${namedList(d.outside_systems)}</p><p class="hint">Need a test version or a fake.</p>` : ""),
    block("Tests saved in Appian", d.saved_tests.length ? `<p>${d.saved_tests.map(esc).join(", ")}</p><p class="hint">Saved inputs only; no expected results were saved.</p>` : ""),
  ].join("");
}

function renderRuleData(d) {
  if (!d.inputs.length && !d.records_read.length && !d.outside_systems.length) return "";
  return [
    block("Inputs", dataTable(d.inputs, inputCols)),
    block("Database records it reads", recordTable(d.records_read)),
    block("Tests saved in Appian", d.saved_tests.length ? `<p>${d.saved_tests.map(esc).join(", ")}</p>` : ""),
    block("Outside systems it calls", d.outside_systems.length ? `<p>${namedList(d.outside_systems)}</p>` : ""),
  ].join("");
}
