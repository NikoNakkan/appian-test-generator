// Analysis: honest progress counts, feature drafts for a person to review, the agent's questions,
// and the lifecycle and access checks. Every decision is previewed before it is kept.
const anState = { tab: "progress", drafts: [], show: "all" };
const reviewer = () => localStorage.getItem("atg-reviewer") || "";
const STATUS_PILL = { approved: "ok", "auto-accepted": "ext", stale: "bad", draft: "idle" };
const SHOW = [["all", "All"], ["draft", "Needs a person"], ["auto-accepted", "Auto-accepted"], ["approved", "Approved"], ["stale", "Stale"]];
const AN_TABS = [["progress", "Progress"], ["drafts", "Feature drafts"], ["questions", "Questions"], ["checks", "Lifecycle and access"]];

async function renderAnalysis() {
  $("#an-page").innerHTML = `<div class="page-head"><div class="title-row"><h2>Analysis</h2>
      <label class="inline">Reviewer <input id="an-who" value="${esc(reviewer())}" placeholder="your name" aria-label="Reviewer name"></label></div>
    <p class="hint">What has been looked at, what is left, and the feature drafts waiting for a person. The counts stay separate on purpose: there is no overall percentage.</p>
    ${segmented("an", AN_TABS, anState.tab)}</div><div id="an-body">${empty("Loading…")}</div>`;
  const body = $("#an-body");
  try { body.innerHTML = await ({ progress: anProgress, drafts: anDrafts, questions: anQuestions, checks: anChecks })[anState.tab](); }
  catch (e) { body.innerHTML = empty(esc(e.message)); }
}

async function anProgress() {
  const r = await api("analysis");
  const rows = r.measures.map((m) => [`<b>${esc(m.measure)}</b>`, m.n == null ? "–" : fmt(m.n),
    m.of == null ? "open set" : fmt(m.of), esc(m.rule), `<span class="hint">${esc(m.supports)}</span>`]);
  const h = r.health;
  return `<div class="kpis">${[[h.open_questions, "open questions"], [h.reads_cut_short, "reads cut short"],
      [h.logic_not_read, "logic not read"], [h.processes_over_path_limit, "processes over the path limit"]]
      .map(([v, l]) => `<div class="kpi ${v ? "ext" : ""}"><b>${fmt(v)}</b><span>${l}</span></div>`).join("")}</div>
    <div class="card"><h3>Measures</h3><p class="sub">Each counts one kind of thing against its own total.</p>
      ${table(["Measure", "Counted", "Of", "Counting rule", "What it lets you say"], rows)}</div>
    <div class="card"><h3>Work items</h3>${table(["Status", "Items"], Object.entries(r.items).map(([s, n]) => [esc(s), fmt(n)]))}</div>`;
}

async function anDrafts() {
  anState.drafts = await api("analysis-drafts");
  if (!anState.drafts.length) return empty("No drafts yet.");
  const shown = anState.drafts.filter((d) => anState.show === "all" || d.status === anState.show);
  const count = (s) => anState.drafts.filter((d) => s === "all" || d.status === s).length;
  return `<div class="card"><h3>Feature drafts</h3><p class="sub">Proposals built by fixed rules, then reviewed by the agent: it names each one in plain words, says what a user does there, and suggests merges. Auto-accepted ones passed every certainty check; the rest need a person. Open one to approve, reject, rename, split or merge it.</p>
    ${segmented("an-show", SHOW.map(([v, l]) => [v, `${l} (${count(v)})`]), anState.show)}
    ${shown.length ? table(["Feature", "Status", "Agent review", "Suggestions", "Doors"], shown.map((d) => [
      `<a href="#" data-an-draft="${esc(d.key)}"><b>${esc(d.name)}</b></a>${d.summary ? `<div>${esc(d.summary)}</div>` : ""}
        ${d.rule_name !== d.name ? `<div class="hint">${esc(d.rule_name)}</div>` : ""}`,
      pill(d.status, STATUS_PILL[d.status]), d.reviewed ? pill("reviewed", "ok") : pill("not yet", "idle"),
      fmt(d.suggest.length), fmt(d.doors.length)])) : empty("None with this status.")}</div>`;
}

async function anQuestions() {
  const qs = await api("analysis-questions");
  if (!qs.length) return empty("The agent has asked nothing yet.");
  return `<div class="card"><h3>Questions from the agent</h3>${qs.map((q) => `<div class="dz-section">
    <p><b>${esc(q.text)}</b> <span class="hint">about ${esc(q.about)}</span></p>
    ${q.status === "answered" ? `<p>${pill("answered", "ok")} ${esc(q.answer)}</p>` : `<textarea id="an-q-${q.id}" rows="2" aria-label="Answer"></textarea>
    <button data-an-answer="${q.id}">Answer</button>`}</div>`).join("")}</div>`;
}

async function anChecks() {
  const [life, access] = await Promise.all([api("analysis-lifecycle"), api("analysis-access")]);
  const list = (xs) => esc(xs.slice(0, 3).join(", ")) + (xs.length > 3 ? ` +${xs.length - 3}` : "");
  return `<div class="card"><h3>Record types: create, read, update, delete</h3>
      ${table(["Record type", "Create", "Read", "Update", "Delete", "Statuses set", "Questions"], life.map((r) => [
        `<b>${esc(r.record_type)}</b>`, list(r.create), list(r.read), list(r.update), list(r.delete),
        esc(Object.entries(r.statuses_set).map(([f, v]) => `${f}: ${v.join(", ")}`).join("; ")), esc(r.gaps.join("; "))]))}</div>
    <div class="card"><h3>Shown versus allowed</h3><p class="sub">Doors whose visibility and role map disagree.</p>
      ${access.length ? table(["Door", "Issue"], access.map((a) => [esc(a.name), esc(a.issue)])) : empty("No disagreement found.")}</div>`;
}

async function openDraft(key) {
  const d = await api("analysis-draft", { key });
  const refs = (xs) => xs.map((x) => `<a href="#" data-panel="${esc(x.id)}">${esc(x.name)}</a>`).join(", ");
  const others = anState.drafts.filter((x) => x.key !== d.key);
  openPanel(`<div class="panel-head">${pill(d.status, STATUS_PILL[d.status])}<h3>${esc(d.name)}</h3></div>
    ${d.reviewed ? section("What it is (agent's review)", `<p>${esc(d.summary)}</p>${d.actor_says ? `<p class="hint">Who: ${esc(d.actor_says)}</p>` : ""}
      <p class="hint">Code name: ${esc(d.rule_name)}</p>`) : section("What it is", `<p class="hint">Not reviewed by the agent yet. Code name: ${esc(d.rule_name)}</p>`)}
    ${section("Agent suggestions", d.suggest.map((s) => `<div>${pill(s.kind.replaceAll("_", " "))} ${esc(nameOf(s.target) || "")} <span class="hint">${esc(s.target ? s.says.slice(s.target.length).replace(/^[:\s]+/, "") : s.says)}</span>
      ${s.kind === "same_feature_as" && s.target && nameOf(s.target) ? `<button data-an-accept="${esc(s.target)}">Merge them</button>` : ""}</div>`).join(""))}
    ${section("Can it be accepted without you?", `<p class="hint">Only when every line below passes. A "not yet" means the agent has more work to do, not that the draft is wrong; you can always approve it yourself.</p>` +
      (d.certainty || []).map((c) => `<div class="check-row">${c.ok ? pill("yes", "ok") : pill("not yet", "bad")} <b>${esc(c.label || c.check)}</b><div class="hint">${esc(c.why)}</div>
        ${c.next ? `<div>→ ${esc(c.next)}</div>` : ""}</div>`).join(""))}
    ${section("Why these belong together", d.why.map((w) => `<div>${esc(w)}</div>`).join(""))}
    ${section("Doubts", d.against.map((w) => `<div>${esc(w)}</div>`).join(""))}
    ${section("Doors", d.doors.map((x) => `<div class="check-row">${esc(x.kind)}: <b>${esc(x.name)}</b>${x.route ? `<div class="hint">Log in as ${esc(x.route.log_in_as)}${x.route.open ? ` · ${esc(x.route.open)}` : ""}</div><ol class="route">${x.route.steps.map((s) => `<li>${esc(s)}</li>`).join("")}</ol>` : ""}
      ${d.doors.length > 1 ? `<button data-an-split="${esc(x.id)}">Split out</button>` : ""}</div>`).join(""))}
    ${section("Core", refs(d.core))}${section("Shared with other features", refs(d.shared))}
    ${section("Data and groups it uses", refs(d.supporting))}
    ${section("Not yet described by the agent", esc(d.unexplained.join(", ")))}
    ${section("Agent claims", d.claims.map((c) => `<div>${pill(c.level)} ${esc(c.predicate)}: ${esc(c.value)}</div>`).join(""))}
    <div class="panel-actions"><button class="primary" data-an-approve="${esc(d.key)}">Approve boundary</button>
      ${d.status === "auto-accepted" ? `<button data-an-reject="${esc(d.key)}">Reject auto-accept</button>` : ""}
      <button data-an-rename="${esc(d.key)}">Rename</button>
      ${others.length ? `<select id="an-merge" aria-label="Merge with">${others.map((o) => `<option value="${esc(o.doors[0].id)}">${esc(o.name)}</option>`).join("")}</select>
      <button data-an-merge="${esc(d.doors[0].id)}">Merge with</button>` : ""}</div>`, { kind: "draft", key });
}

function nameOf(key) {
  return anState.drafts.find((x) => x.key === key)?.name;
}

async function decideUI(body, again) {
  const by = reviewer();
  if (!by) { alert("Type your name in the Reviewer box first."); return; }
  const post = (preview) => getJSON(`/api/snapshots/${state.sid}/decision`, { method: "POST",
    headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, by, preview }) });
  try {
    const p = await post(true);
    const c = p.would_change || {};
    const what = `${(c.removed || []).length} drafts end, ${Object.keys(c.added || {}).length} drafts change`;
    if (!confirm(`${body.kind} ${body.target}\n\nWhat changes: ${what}.\n\nKeep this decision?`)) return;
    await post(false);
    await renderAnalysis();
    if (again) await again();
  } catch (e) { alert(e.message); }
}

document.addEventListener("DOMContentLoaded", () => {
  $("#an-page").addEventListener("click", (e) => {
    const t = e.target.closest("[data-an],[data-an-show],[data-an-draft],[data-an-answer]");
    if (!t) return;
    e.preventDefault();
    if (t.dataset.an) { anState.tab = t.dataset.an; renderAnalysis(); }
    else if (t.dataset.anShow) { anState.show = t.dataset.anShow; renderAnalysis(); }
    else if (t.dataset.anDraft) openDraft(t.dataset.anDraft);
    else decideUI({ kind: "answer", target: t.dataset.anAnswer, payload: { text: $(`#an-q-${t.dataset.anAnswer}`).value } });
  });
  $("#an-page").addEventListener("change", (e) => { if (e.target.id === "an-who") localStorage.setItem("atg-reviewer", e.target.value.trim()); });
  $("#panel-body").addEventListener("click", (e) => {
    const t = e.target.closest("[data-an-approve],[data-an-reject],[data-an-rename],[data-an-split],[data-an-merge],[data-an-accept]");
    if (!t) return;
    const key = panel.stack.at(-1)?.key;
    const reopen = () => openDraft(key);
    if (t.dataset.anApprove) decideUI({ kind: "approve", target: t.dataset.anApprove }, reopen);
    else if (t.dataset.anReject) decideUI({ kind: "reject", target: t.dataset.anReject, reason: "needs a person" }, reopen);
    else if (t.dataset.anRename) { const name = prompt("New name"); if (name) decideUI({ kind: "rename", target: t.dataset.anRename, payload: { name } }, reopen); }
    else if (t.dataset.anAccept) decideUI({ kind: "merge", target: key, payload: { with: t.dataset.anAccept }, reason: "agent suggested it" }, reopen);
    else if (t.dataset.anSplit) decideUI({ kind: "split", target: t.dataset.anSplit }, () => openDraft(t.dataset.anSplit));
    else decideUI({ kind: "merge", target: t.dataset.anMerge, payload: { with: $("#an-merge").value } }, reopen);
  });
});
