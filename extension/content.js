// Resident grader on Google Docs: a floating button opens a panel; "scan" pulls
// the whole document and grades it via the user's local backend.
(function () {
  if (window.__egxLoaded) return;
  window.__egxLoaded = true;

  const TYPE_COLORS = {
    thesis: "#6366f1", evidence: "#0ea5e9", organization: "#8b5cf6", cohesion: "#06b6d4",
    vocabulary: "#f59e0b", grammar: "#ef4444", syntax: "#f97316", conventions: "#ec4899",
    style: "#14b8a6", praise: "#22c55e",
    commentary: "#0284c7", reasoning: "#7c3aed", sophistication: "#d946ef",
  };
  const TYPE_LABELS = {
    thesis: "Row A · Thesis", evidence: "Row B · Evidence", commentary: "Row B · Commentary",
    reasoning: "Row B · Reasoning", sophistication: "Row C · Sophistication",
    grammar: "Grammar", praise: "Strength",
  };
  const DIM_LABELS = { cohesion: "Cohesion", syntax: "Syntax", vocabulary: "Vocabulary", phraseology: "Phraseology", grammar: "Grammar", conventions: "Conventions" };

  function docId() {
    const m = location.pathname.match(/\/document\/d\/([^/]+)/);
    return m ? m[1] : "";
  }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  // ---- build UI ----
  const launcher = document.createElement("button");
  launcher.id = "egx-launcher";
  launcher.textContent = "📝 Grade";
  launcher.title = "Essay Grader";
  document.body.appendChild(launcher);

  const panel = document.createElement("div");
  panel.id = "egx-panel";
  panel.hidden = true;
  panel.innerHTML = `
    <div class="egx-head">
      <span>📝 Essay Grader</span>
      <button id="egx-close" title="Close">✕</button>
    </div>
    <div class="egx-body">
      <div class="egx-controls">
        <select id="egx-mode" title="Grading mode">
          <option value="ap">AP score (official rubric)</option>
          <option value="quick">Quick language check</option>
        </select>
        <select id="egx-frq" title="AP free-response question type">
          <option value="rhetorical_analysis">Rhetorical Analysis</option>
          <option value="argument">Argument</option>
          <option value="synthesis">Synthesis</option>
        </select>
      </div>
      <button id="egx-scan" class="egx-btn">Scan this document &amp; grade</button>
      <p id="egx-status" class="egx-status"></p>
      <div id="egx-result" hidden></div>
    </div>`;
  document.body.appendChild(panel);

  launcher.addEventListener("click", () => { panel.hidden = !panel.hidden; });
  panel.querySelector("#egx-close").addEventListener("click", () => { panel.hidden = true; });
  panel.querySelector("#egx-scan").addEventListener("click", scan);
  const modeSel = panel.querySelector("#egx-mode");
  const frqSel = panel.querySelector("#egx-frq");
  const syncMode = () => { frqSel.style.display = modeSel.value === "ap" ? "" : "none"; };
  modeSel.addEventListener("change", syncMode);
  syncMode();

  function status(msg, kind) {
    const el = panel.querySelector("#egx-status");
    el.textContent = msg || "";
    el.className = "egx-status" + (kind ? " egx-" + kind : "");
  }

  async function scan() {
    const btn = panel.querySelector("#egx-scan");
    btn.disabled = true;
    const ap = modeSel.value === "ap";
    status(ap ? "⏳ Fetching the document and scoring on the AP rubric…"
              : "⏳ Fetching the document and grading, please wait…");
    try {
      const res = await chrome.runtime.sendMessage({
        type: "scanDoc", docId: docId(),
        mode: modeSel.value, frqType: frqSel.value,
      });
      if (!res || res.error) throw new Error(res ? res.error : "No response");
      if (ap) renderAP(res.data); else render(res.data);
      status("");
    } catch (e) {
      status("✗ " + e.message, "warn");
    } finally {
      btn.disabled = false;
    }
  }

  // ---- AP render ----
  const AP_ROWS = [
    ["A_thesis", "Row A · Thesis", 1],
    ["B_evidence_commentary", "Row B · Evidence & Commentary", 4],
    ["C_sophistication", "Row C · Sophistication", 1],
  ];
  function renderAP(data) {
    const r = panel.querySelector("#egx-result");
    r.hidden = false;
    const rows = AP_ROWS.map(([key, label, max]) => {
      const row = data.rows[key] || {};
      const why = esc(row.rationale || row.commentary || "");
      const gate = row.grammar_gate_applied
        ? '<span class="egx-warn"> · grammar cap</span>' : "";
      return `<div class="egx-aprow"><div class="egx-aprow-h"><b>${label}</b>` +
        `<span class="egx-apscore">${row.score}/${max}</span>${gate}</div>` +
        `<p class="egx-muted">${why}</p></div>`;
    }).join("");
    const anns = data.annotations || [];
    const commentsCard = anns.length
      ? `<div class="egx-card">
          <div class="egx-annhead"><h3>Margin notes <span class="egx-muted">${anns.length} notes</span></h3>
            <label class="egx-toggle"><input type="checkbox" id="egx-all"> Show all</label></div>
          <p class="egx-muted egx-tiny">Each note is tagged to its rubric row. Click a highlight to show/hide its comment.</p>
          <article id="egx-essay" class="egx-essay"></article>
        </div>`
      : "";
    r.innerHTML =
      `<div class="egx-aptotal">${data.total ?? "–"}<small>/6</small>` +
      `<span class="egx-muted"> ${esc(data.frq_label || "")}</span></div>` +
      `<div class="egx-aprows">${rows}</div>` +
      `<div class="egx-card"><h3>Teacher's comment</h3><p>${esc(data.overall_comment || "")}</p></div>` +
      ((data.top_fixes || []).length
        ? `<div class="egx-card"><h3>Top fixes</h3><ol>${
            data.top_fixes.map((f) => `<li>${esc(f)}</li>`).join("")}</ol></div>`
        : "") +
      commentsCard;
    if (anns.length) {
      buildEssay(data.text || "", anns);
      r.querySelector("#egx-all").addEventListener("change", (e) => toggleAll(e.target.checked));
    }
  }

  // ---- render ----
  function render(data) {
    const r = panel.querySelector("#egx-result");
    r.hidden = false;
    const dims = ["cohesion", "syntax", "vocabulary", "phraseology", "grammar", "conventions"];
    const bars = dims.map((d) => {
      const v = data.scores[d] ?? 0;
      return `<div class="egx-bar"><span>${DIM_LABELS[d]}</span><i><b style="width:${(v / 5) * 100}%"></b></i><em>${v}</em></div>`;
    }).join("");
    r.innerHTML = `
      <div class="egx-overall"><div class="egx-score">${data.scores.overall ?? "–"}<small>/5</small></div><div class="egx-bars">${bars}</div></div>
      <div class="egx-card"><h3>Teacher's comment</h3><p>${esc(data.summary || "")}</p></div>
      <details class="egx-card"><summary>Strengths / Top fixes</summary>
        <div class="egx-two">
          <div><b class="egx-good">✓ Done well</b><ul>${(data.strengths || []).map((s) => `<li>${esc(s)}</li>`).join("")}</ul></div>
          <div><b class="egx-warn">→ Fix first</b><ol>${(data.priorities || []).map((p) => `<li>${esc(p)}</li>`).join("")}</ol></div>
        </div>
      </details>
      <div class="egx-card">
        <div class="egx-annhead"><h3>Comments <span class="egx-muted">${(data.annotations || []).length} notes</span></h3>
          <label class="egx-toggle"><input type="checkbox" id="egx-all"> Show all</label></div>
        <p class="egx-muted egx-tiny">Click a highlight to show/hide its comment.</p>
        <article id="egx-essay" class="egx-essay"></article>
      </div>`;
    buildEssay(data.text || "", data.annotations || []);
    r.querySelector("#egx-all").addEventListener("change", (e) => toggleAll(e.target.checked));
  }

  function buildEssay(text, anns) {
    const located = anns.map((a, i) => ({ ...a, _idx: i })).filter((a) => a.located && a.start >= 0).sort((a, b) => a.start - b.start);
    const spans = [];
    let lastEnd = -1;
    for (const a of located) { if (a.start < lastEnd) continue; spans.push(a); lastEnd = a.end; }
    const body = panel.querySelector("#egx-essay");
    body.innerHTML = "";
    body._anns = {};
    let cursor = 0;
    for (const a of spans) {
      if (a.start > cursor) body.appendChild(document.createTextNode(text.slice(cursor, a.start)));
      const mark = document.createElement("mark");
      mark.className = "egx-ann";
      mark.style.borderBottomColor = TYPE_COLORS[a.type] || "#94a3b8";
      mark.textContent = text.slice(a.start, a.end);
      mark.dataset.idx = a._idx;
      mark.title = a.type;
      mark.addEventListener("click", () => toggleComment(mark, a));
      body.appendChild(mark);
      body._anns[a._idx] = a;
      cursor = a.end;
    }
    if (cursor < text.length) body.appendChild(document.createTextNode(text.slice(cursor)));
  }

  function commentEl(a) {
    const div = document.createElement("div");
    div.className = "egx-comment";
    div.style.borderLeftColor = TYPE_COLORS[a.type] || "#94a3b8";
    div.innerHTML = `<span class="egx-ctype">${esc(TYPE_LABELS[a.type] || a.type)}</span><p>${esc(a.comment)}</p>` +
      (a.suggestion ? `<p class="egx-sug">💡 ${esc(a.suggestion)}</p>` : "");
    return div;
  }
  function toggleComment(mark, a) {
    const n = mark.nextElementSibling;
    if (n && n.classList && n.classList.contains("egx-comment")) { n.remove(); return; }
    mark.insertAdjacentElement("afterend", commentEl(a));
  }
  function toggleAll(on) {
    const body = panel.querySelector("#egx-essay");
    body.querySelectorAll(".egx-comment").forEach((n) => n.remove());
    if (!on) return;
    body.querySelectorAll("mark.egx-ann").forEach((mark) => {
      const a = body._anns[mark.dataset.idx];
      if (a) mark.insertAdjacentElement("afterend", commentEl(a));
    });
  }
})();
