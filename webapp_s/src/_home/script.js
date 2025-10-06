"use strict";

const root = document.documentElement;
const btn = document.getElementById('toggle-theme-btn');


// Helper: detach the whole <tbody>, run action, then reattach immediately
function withTbodyTemporarilyDetachedSync(action) {
  const tbody = rowsEl; // rowsEl should be the <tbody> element
  if (!tbody || !tbody.parentNode) { action(); return; }
  const parent = tbody.parentNode;
  const nextSibling = tbody.nextSibling;

  // Remove <tbody> from live DOM (moves the node)
  parent.removeChild(tbody);

  try {
    // Perform the synchronous action (e.g., theme toggle) while table is detached
    action();
  } finally {
    setTimeout(() => {
      // Reattach in the original position without rAF
    if (nextSibling) parent.insertBefore(tbody, nextSibling);
    else parent.appendChild(tbody);
  }, 500);
  }
}

// Wrap theme application so the <tbody> is detached during the toggle
function applyTheme(theme) {
  const isDark = theme === 'dark';
  withTbodyTemporarilyDetachedSync(() => {
    root.classList.toggle('dark', isDark);
    if (btn) btn.setAttribute('aria-pressed', String(isDark));
    localStorage.setItem('theme', theme);
  });
}


function initTheme() {
  let theme = null;
  try { theme = localStorage.getItem('theme'); } catch (_) { }
  if (!theme) {
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    theme = prefersDark ? 'dark' : 'light';
  }
  applyTheme(theme);
}
function registerToggle() {
  if (!btn) return;
  btn.addEventListener('click', () => {
    const nextTheme = root.classList.contains('dark') ? 'light' : 'dark';
    applyTheme(nextTheme);
  });
}
initTheme();
registerToggle();

const rowsEl = document.getElementById("sentiment-rows");
const tickerInp = document.getElementById("ticker");
const exchangeInp = document.getElementById("exchange");
const statusEl = document.getElementById("status");
const btnExcel = document.getElementById("download-excel");
const btnJSON = document.getElementById("download-json");

let currentTicker = "";
let currentData = []; // [{ date: "YYYY-MM-DD", score: 0|1|2 }]

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg || "";
}

function clearTable() {
  if (rowsEl) rowsEl.innerHTML = "";
}

function renderRows(items) {
  clearTable();
  if (!rowsEl) return;
  const frag = document.createDocumentFragment();
  for (const row of items) {
    const tr = document.createElement("tr");

    const th = document.createElement("th");
    th.scope = "row";
    th.className = "p-4 whitespace-nowrap text-sm font-medium";
    th.textContent = row.date;

    const td = document.createElement("td");
    td.className = "p-4 whitespace-nowrap text-sm text-center";
    td.textContent = String(row.score);

    tr.appendChild(th);
    tr.appendChild(td);
    frag.appendChild(tr);
  }
  rowsEl.appendChild(frag);
}

// Base URL of the Flask API (adjust if hosted under a path)
const API_BASE = "https://api.autonomousweb.org"

// Parse text/plain response "YYYY-MM-DD|score" per line
function parsePipeText(text) {
  const out = [];
  const lines = text.split(/\r?\n/);
  for (const ln of lines) {
    if (!ln) continue;
    const [date, scoreStr] = ln.split("|");
    if (!date) continue;
    const s = Number.parseInt((scoreStr || "").trim(), 10);
    if (!Number.isFinite(s)) continue;
    out.push({ date: date.trim(), score: s });
  }
  return out;
}

async function loadTicker(tickerRaw, exchangeRaw) {
  const ticker = (tickerRaw || "").trim();
  const exchange = (exchangeRaw || "").trim();
  if (!ticker || !exchange) {
    setStatus("Select an exchange and enter a ticker symbol to load data.");
    currentTicker = "";
    currentData = [];
    clearTable();
    return;
  }

  setStatus(`Loading ${ticker.toUpperCase()}...`);

  const url = `${API_BASE}/sentiment?exchange=${encodeURIComponent(exchange.toLowerCase())}&ticker=${encodeURIComponent(ticker.toUpperCase())}`;

  try {
    const res = await fetch(url, { headers: { "Accept": "text/plain" }, cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const text = await res.text();
    const data = parsePipeText(text);

    currentTicker = ticker.toUpperCase();
    currentData = data;
    renderRows(currentData);
    setStatus(`${currentTicker} loaded: ${currentData.length} rows.`);
  } catch (err) {
    console.error(err);
    setStatus(`No data found for ${ticker.toUpperCase()}.`);
    currentTicker = "";
    currentData = [];
    clearTable();
  }
}

// Debounce
function debounce(fn, delay = 300) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), delay);
  };
}

const debouncedLoad = debounce(() => {
  if (!tickerInp || !exchangeInp) return;
  const v = tickerInp.value.trim();
  const exchange = exchangeInp.value.trim();
  loadTicker(v, exchange);
}, 600);

tickerInp?.addEventListener("keyup", () => debouncedLoad());
tickerInp?.addEventListener("change", () => debouncedLoad());
exchangeInp?.addEventListener("change", () => debouncedLoad());

// Downloads
btnExcel?.addEventListener("click", () => {
  if (!currentData.length) return;
  const header = "Date,Sentiment score";
  const body = currentData.map(r => `${r.date},${r.score}`).join("\n");
  const csv = `${header}\n${body}`;
  downloadBlob(csv, `${currentTicker || "data"}.csv`, "text/csv;charset=utf-8");
});

btnJSON?.addEventListener("click", () => {
  if (!currentData.length) return;
  const json = JSON.stringify(currentData, null, 2);
  downloadBlob(json, `${currentTicker || "data"}.json`, "application/json");
});

function downloadBlob(content, filename, type) {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}


 const radios = document.querySelectorAll('input[name="view-toggle"]');
              const tablePanel = document.getElementById('table-view-panel');
              const chartPanel = document.getElementById('chart-view-panel');

              function setView(view) {
                const isTable = view === 'table';
                tablePanel.classList.toggle('hidden', !isTable);
                chartPanel.classList.toggle('hidden', isTable);
                tablePanel.setAttribute('aria-hidden', String(!isTable));
                chartPanel.setAttribute('aria-hidden', String(isTable));
              }

              radios.forEach(r => r.addEventListener('change', (e) => setView(e.target.value)));
              const checked = document.querySelector('input[name="view-toggle"]:checked');
              setView(checked ? checked.value : 'table');