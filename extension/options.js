const DEFAULTS = { apiBase: "http://127.0.0.1:8011", apiToken: "" };

async function load() {
  const s = await chrome.storage.local.get(DEFAULTS);
  document.getElementById("apiBase").value = s.apiBase;
  document.getElementById("apiToken").value = s.apiToken;
}

document.getElementById("save").addEventListener("click", async () => {
  await chrome.storage.local.set({
    apiBase: document.getElementById("apiBase").value.trim() || DEFAULTS.apiBase,
    apiToken: document.getElementById("apiToken").value.trim(),
  });
  const ok = document.getElementById("ok");
  ok.textContent = "Saved ✓";
  setTimeout(() => (ok.textContent = ""), 1500);
});

load();
