const DEFAULTS = { apiBase: "http://127.0.0.1:8011", apiToken: "" };
const TYPE_COLORS = {
  thesis: "#6366f1", evidence: "#0ea5e9", organization: "#8b5cf6", cohesion: "#06b6d4",
  vocabulary: "#f59e0b", grammar: "#ef4444", syntax: "#f97316", conventions: "#ec4899",
  style: "#14b8a6", praise: "#22c55e",
};

const $ = (id) => document.getElementById(id);
let current = null; // last grade result

async function settings() {
  const s = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...s };
}

function setStatus(msg, kind) {
  const el = $("status");
  el.textContent = msg || "";
  el.className = "status" + (kind ? " " + kind : "");
}

// ---- selection plumbing ----
async function loadPendingSelection() {
  const { pendingText } = await chrome.storage.session.get("pendingText");
  if (pendingText) {
    $("essay").value = pendingText;
    chrome.storage.session.remove("pendingText");
    grade();
  }
}
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "selection" && msg.text) {
    $("essay").value = msg.text;
    grade();
  }
});

$("grabBtn").addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;
  try {
    const [{ result }] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => window.getSelection().toString(),
    });
    if (result && result.trim()) {
      $("essay").value = result.trim();
      setStatus("Selected text grabbed — click “Grade”.");
    } else {
      setStatus("No text is selected on this page.", "warn");
    }
  } catch (e) {
    setStatus("Can't read this page (it may be restricted) — please paste manually.", "warn");
  }
});

$("settingsBtn").addEventListener("click", () => chrome.runtime.openOptionsPage());
$("gradeBtn").addEventListener("click", grade);
$("showAll").addEventListener("change", (e) => toggleAll(e.target.checked));

function syncMode() {
  $("frq").style.display = $("mode").value === "ap" ? "" : "none";
}
$("mode").addEventListener("change", syncMode);
syncMode();

const ROW_META = [
  ["A_thesis", "Row A · Thesis", 1],
  ["B_evidence_commentary", "Row B · Evidence & Commentary", 4],
  ["C_sophistication", "Row C · Sophistication", 1],
];

function renderAP(data) {
  $("result").hidden = true;
  $("apResult").hidden = false;
  $("apTotal").textContent = data.total ?? "–";
  $("apLabel").textContent = data.frq_label || "";
  $("apRows").innerHTML = ROW_META.map(([key, label, max]) => {
    const r = data.rows[key] || {};
    const rationale = r.rationale || r.commentary || "";
    const gate = r.grammar_gate_applied
      ? '<span class="warn"> · grammar cap applied</span>' : "";
    return `<div class="ap-row">
      <div class="ap-row-head"><b>${label}</b><span class="ap-score">${r.score}/${max}</span>${gate}</div>
      <p class="muted">${esc(rationale)}</p></div>`;
  }).join("");
  $("apComment").textContent = data.overall_comment || "";
  $("apFixes").innerHTML = (data.top_fixes || []).map((f) => `<li>${esc(f)}</li>`).join("");
  $("apFixesCard").hidden = !(data.top_fixes || []).length;
}

// ---- grading ----
async function grade() {
  const text = $("essay").value.trim();
  if (!text) { setStatus("Paste or grab an essay first.", "warn"); return; }
  const cfg = await settings();
  const ap = $("mode").value === "ap";
  setStatus(ap ? "⏳ Scoring on the AP rubric, please wait…"
               : "⏳ The teacher is grading, please wait…");
  $("gradeBtn").disabled = true;
  const base = cfg.apiBase.replace(/\/$/, "");
  const endpoint = ap ? "/api/ap_grade" : "/api/grade";
  const payload = ap
    ? { text, frq_type: $("frq").value }
    : { text, essay_type: "argumentative essay" };
  try {
    const resp = await fetch(base + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": cfg.apiToken },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || ("HTTP " + resp.status));
    current = data;
    if (ap) renderAP(data);
    else { $("apResult").hidden = true; render(data); }
    setStatus("");
  } catch (e) {
    setStatus("Grading failed: " + e.message, "warn");
  } finally {
    $("gradeBtn").disabled = false;
  }
}

// ---- rendering ----
function render(data) {
  $("result").hidden = false;
  $("overall").textContent = data.scores.overall ?? "–";

  const dims = ["cohesion", "syntax", "vocabulary", "phraseology", "grammar", "conventions"];
  const labels = { cohesion: "Cohesion", syntax: "Syntax", vocabulary: "Vocabulary", phraseology: "Phraseology", grammar: "Grammar", conventions: "Conventions" };
  $("bars").innerHTML = dims.map((d) => {
    const v = data.scores[d] ?? 0;
    return `<div class="bar"><span>${labels[d]}</span><i><b style="width:${(v / 5) * 100}%"></b></i><em>${v}</em></div>`;
  }).join("");

  $("summary").textContent = data.summary || "";
  $("strengths").innerHTML = (data.strengths || []).map((s) => `<li>${esc(s)}</li>`).join("");
  $("priorities").innerHTML = (data.priorities || []).map((p) => `<li>${esc(p)}</li>`).join("");
  $("annCount").textContent = (data.annotations || []).length + " notes";

  buildEssay(data.text || $("essay").value, data.annotations || []);
  $("showAll").checked = false;
}

function buildEssay(text, anns) {
  // located, non-overlapping spans in order
  const located = anns
    .map((a, i) => ({ ...a, _idx: i }))
    .filter((a) => a.located && a.start >= 0)
    .sort((a, b) => a.start - b.start);
  const spans = [];
  let lastEnd = -1;
  for (const a of located) {
    if (a.start < lastEnd) continue;
    spans.push(a);
    lastEnd = a.end;
  }
  const body = $("essayBody");
  body.innerHTML = "";
  let cursor = 0;
  for (const a of spans) {
    if (a.start > cursor) body.appendChild(document.createTextNode(text.slice(cursor, a.start)));
    const mark = document.createElement("mark");
    mark.className = "ann";
    mark.style.borderBottomColor = TYPE_COLORS[a.type] || "#94a3b8";
    mark.textContent = text.slice(a.start, a.end);
    mark.dataset.idx = a._idx;
    mark.title = a.type;
    mark.addEventListener("click", () => toggleComment(mark, a));
    body.appendChild(mark);
    cursor = a.end;
  }
  if (cursor < text.length) body.appendChild(document.createTextNode(text.slice(cursor)));
  // map idx -> annotation for showAll
  body._anns = {};
  spans.forEach((a) => (body._anns[a._idx] = a));
}

function toggleComment(mark, a) {
  const next = mark.nextElementSibling;
  if (next && next.classList && next.classList.contains("inline-comment")) {
    next.remove();
    return;
  }
  mark.insertAdjacentElement("afterend", commentEl(a));
}

function commentEl(a) {
  const div = document.createElement("div");
  div.className = "inline-comment";
  div.style.borderLeftColor = TYPE_COLORS[a.type] || "#94a3b8";
  const sug = a.suggestion ? `<p class="sug">💡 ${esc(a.suggestion)}</p>` : "";
  div.innerHTML = `<span class="ctype">${esc(a.type)}</span><p>${esc(a.comment)}</p>${sug}`;
  return div;
}

function toggleAll(on) {
  const body = $("essayBody");
  body.querySelectorAll(".inline-comment").forEach((n) => n.remove());
  if (!on) return;
  body.querySelectorAll("mark.ann").forEach((mark) => {
    const a = body._anns[mark.dataset.idx];
    if (a) mark.insertAdjacentElement("afterend", commentEl(a));
  });
}

function esc(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

loadPendingSelection();
