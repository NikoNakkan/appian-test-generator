// Read-only SAIL viewer: syntax colouring, plus links on references to other objects.
// Segments come from the API as [text, uuid | "outside" | null].
const SAIL_TOKENS = new RegExp([
  String.raw`(?<comment>/\*[\s\S]*?\*/)`,
  String.raw`(?<string>"(?:[^"]|"")*")`,
  String.raw`(?<variable>\b(?:local|ri|pv|ac|fv|fn|rv|rf|rsp|pp|tp|cons)![\w.]+)`,
  String.raw`(?<func>\b(?:a|rule|recordType|type|processModel|group|webApi)![\w.]+)`,
  String.raw`(?<keyword>\b(?:if|and|or|not|true|false|null|choose|index|with|load)\b)`,
  String.raw`(?<number>\b\d+(?:\.\d+)?\b)`,
  String.raw`(?<key>\b[A-Za-z_]\w*(?=\s*:(?!=)))`,
].join("|"), "g");

function highlightSail(text) {
  let out = "", pos = 0;
  for (const m of text.matchAll(SAIL_TOKENS)) {
    out += esc(text.slice(pos, m.index));
    const kind = Object.keys(m.groups).find((k) => m.groups[k] !== undefined);
    out += `<span class="tok-${kind}">${esc(m[0])}</span>`;
    pos = m.index + m[0].length;
  }
  return out + esc(text.slice(pos));
}

function renderCode(segments, { inline = false } = {}) {
  if (!segments || !segments.length) return inline ? "" : `<p class="hint">No expression.</p>`;
  const body = segments.map(([text, link]) => {
    if (!link) return highlightSail(text);
    if (link === "outside") return `<span class="tok-outside" title="An object from another app, not in this export">${esc(text)}</span>`;
    return `<a class="tok-link" href="#" data-open="${esc(link)}">${esc(text)}</a>`;
  }).join("");
  return inline ? `<code class="code-inline">${body}</code>` : `<pre class="code">${body}</pre>`;
}

// Any rendered reference opens a summary of its object in the side panel.
document.addEventListener("click", (e) => {
  const a = e.target.closest(".tok-link[data-open]");
  if (!a) return;
  e.preventDefault();
  panelObject(a.dataset.open);
});
