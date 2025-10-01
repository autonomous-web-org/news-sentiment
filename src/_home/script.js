"use strict";

  const root = document.documentElement;
  const btn = document.getElementById('toggle-theme-btn');

  // Apply theme and sync aria-pressed + storage
  function applyTheme(theme) {
    const isDark = theme === 'dark';
    root.classList.toggle('dark', isDark);
    if (btn) btn.setAttribute('aria-pressed', String(isDark));
    try { localStorage.setItem('theme', theme); } catch (_) {}
  }

  // Initialize from storage or system preference
  function initTheme() {
    let theme = null;
    try { theme = localStorage.getItem('theme'); } catch (_) {}
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
