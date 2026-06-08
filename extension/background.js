// Side panel + context menu (for arbitrary pages) and the Google Docs scan flow.
const DEFAULTS = { apiBase: "http://127.0.0.1:8011", apiToken: "" };

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "grade-selection",
    title: "Grade selection with Essay Grader",
    contexts: ["selection"],
  });
});

chrome.action.onClicked.addListener((tab) => {
  chrome.sidePanel.open({ windowId: tab.windowId }).catch(() => {});
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "grade-selection") return;
  const text = (info.selectionText || "").trim();
  await chrome.storage.session.set({ pendingText: text, pendingAt: Date.now() });
  try { await chrome.sidePanel.open({ windowId: tab.windowId }); } catch (e) {}
  chrome.runtime.sendMessage({ type: "selection", text }).catch(() => {});
});

// ---- messages from the Google Docs content script ----
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "scanDoc") {
    handleScan(msg.docId, msg.mode, msg.frqType)
      .then(sendResponse)
      .catch((e) => sendResponse({ error: String(e.message || e) }));
    return true; // async
  }
});

async function settings() {
  const s = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...s };
}

async function handleScan(docId, mode, frqType) {
  if (!docId) return { error: "Couldn't read the document ID (use this on a Google Docs page)." };
  // 1) pull the full doc text via Google's export endpoint (uses the user's login cookies)
  let text = "";
  try {
    const exp = await fetch(
      `https://docs.google.com/document/d/${docId}/export?format=txt`,
      { credentials: "include" }
    );
    if (!exp.ok) return { error: `Couldn't read the document (HTTP ${exp.status}). Make sure you're signed in and have access.` };
    text = (await exp.text()).trim();
  } catch (e) {
    return { error: "Failed to read the document: " + (e.message || e) };
  }
  if (!text) return { error: "The document is empty." };
  // export returns a login/redirect HTML page when not authed or no access
  const head = text.slice(0, 200).toLowerCase();
  if (head.startsWith("<!doctype") || head.startsWith("<html") || head.includes("<title>")) {
    return { error: "That wasn't the document text (you may be signed out of Google, lack access, or this isn't a doc page)." };
  }
  if (text.length < 20) return { error: "The document is too short to grade." };

  // 2) grade it via the user's own local backend
  const cfg = await settings();
  const ap = mode === "ap";
  const endpoint = ap ? "/api/ap_grade" : "/api/grade";
  const payload = ap
    ? { text, frq_type: frqType || "rhetorical_analysis" }
    : { text, essay_type: "argumentative essay" };
  try {
    const resp = await fetch(cfg.apiBase.replace(/\/$/, "") + endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-API-Key": cfg.apiToken },
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) return { error: data.error || ("Grading service returned HTTP " + resp.status) };
    return { ok: true, data };
  } catch (e) {
    return { error: "Can't reach the local grading backend (" + cfg.apiBase + "). Make sure start.command is running." };
  }
}
