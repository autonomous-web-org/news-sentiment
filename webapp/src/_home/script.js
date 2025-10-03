"use strict";

const root = document.documentElement;
const btn = document.getElementById('toggle-theme-btn');

// Apply theme and sync aria-pressed + storage
function applyTheme(theme) {
    const isDark = theme === 'dark';
    root.classList.toggle('dark', isDark);
    if (btn) btn.setAttribute('aria-pressed', String(isDark));
    try { localStorage.setItem('theme', theme); } catch (_) { }
}

// Initialize from storage or system preference
function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem('theme'); } catch (_) { }
    if (!theme) {
        const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        theme = prefersDark ? 'dark' : 'light';
    }
    applyTheme(theme);
}

// Register click handler
function registerToggle() {
    if (!btn) return;
    btn.addEventListener('click', () => {
        const nextTheme = root.classList.contains('dark') ? 'light' : 'dark';
        applyTheme(nextTheme);
    });
}

// Boot
initTheme();
registerToggle();



const rowsEl = document.getElementById("sentiment-rows");
const input = document.getElementById("ticker");
const statusEl = document.getElementById("status");
const btnExcel = document.getElementById("download-excel");
const btnJSON = document.getElementById("download-json");

let currentTicker = "";
  let currentData = []; // [{ date: "YYYY-MM-DD", score: "0|1|2" }, ...]

  function setStatus(msg) {
    if (statusEl) statusEl.textContent = msg || "";
}

  // Minimal CSV parser for simple comma-separated, quoted or unquoted fields.
function parseCSV(text) {
    const lines = text.trim().split(/\r?\n/);
    if (lines.length === 0) return { headers: [], rows: [] };

    const headers = splitCSVLine(lines[0]);
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      if (!lines[i]) continue;
      const fields = splitCSVLine(lines[i]);
      const obj = {};
      headers.forEach((h, idx) => (obj[h] = fields[idx] ?? ""));
      rows.push(obj);
  }
  return { headers, rows };
}

  // Split a CSV line respecting simple quotes
function splitCSVLine(line) {
    const out = [];
    let cur = "";
    let inQuotes = false;

    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        if (inQuotes && line[i + 1] === '"') {
          cur += '"';
          i++;
      } else {
          inQuotes = !inQuotes;
      }
  } else if (ch === "," && !inQuotes) {
    out.push(cur);
    cur = "";
} else {
    cur += ch;
}
}
out.push(cur);
return out;
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

async function loadTicker(tickerRaw) {
    const ticker = (tickerRaw || "").trim();
    if (!ticker) {
      setStatus("Enter a ticker symbol to load data.");
      currentTicker = "";
      currentData = [];
      clearTable();
      return;
  }

  setStatus(`Loading ${ticker.toUpperCase()}...`);
    // Convention: CSV files are named lowercased, e.g., aapl.csv
    // Sample confirms "date,sentiment" header with numeric values 0,1,2 [attached].
  const base = "./assets/data/";
  const urlLower = `${base}${ticker.toLowerCase()}.csv`;

  try {
      const res = await fetch(urlLower);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const text = await res.text();
      const { headers, rows } = parseCSV(text);

      // Expecting headers: date, sentiment
      const dateKey = headers.find(h => h.toLowerCase() === "date") || "date";
      const newsKey = headers.find(h => h.toLowerCase() === "sentiment") || "sentiment";

      // Map to table shape
      const data = rows.map(r => ({
        date: r[dateKey],
        score: r[newsKey],
    }));

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

// Generic debounce utility
  function debounce(fn, delay = 300) {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), delay);
    };
  }


  const debouncedLoad = debounce(() => {
    if (!input) return;
    const v = input.value.trim();
    if (v) loadTicker(v);
  }, 900);

  // Trigger on Enter or when input loses focus (optional)
input?.addEventListener("keyup", (e) => {
    debouncedLoad();
    // if (e.key === "Enter") loadTicker(input.value);
});
input?.addEventListener("change", () => loadTicker(input.value));

  // Downloads
btnExcel?.addEventListener("click", () => {
    if (!currentData.length) return;
    // Create CSV compatible with Excel
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
