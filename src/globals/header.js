import i18next from 'i18next';
import HttpBackend from 'i18next-http-backend';
import LanguageDetector from 'i18next-browser-languagedetector';

// active nav =========================================================================
const navLinks = document.querySelectorAll(".nav-links");
for (var i = navLinks.length - 1; i >= 0; i--) {
	const z = navLinks[i];

	if (window.location.href.includes(z.href)) {
		z.classList.add('font-bold');
		break;
	}
}

// mobile screen menu button =========================================================================
// document.querySelector("#mobile-navigation-menu-btn").addEventListener("click", (e) => {
// 	const nav = document.querySelector("nav");

// 	nav.classList.toggle("hidden");
// 	nav.classList.toggle("flex");

// 	console.log("clicked!", e)
// });


// internationalization =========================================================================
// helper to pull the lang code out of "#lang-xx"
function detectHashLang() {
  const m = window.location.hash.match(/^#lang\-([a-z]{2})/i);
  return m ? m[1] : null;
}

function detectStoredLang() {
  return localStorage.getItem('lng');
}

document.addEventListener('DOMContentLoaded', () => {
  // 1) pick up initial lang from hash → storage → default
  const initialLang = detectHashLang() || detectStoredLang() || 'en';

  i18next
    .use(HttpBackend)
    .init({
      lng: initialLang,
      fallbackLng: 'en',
      backend: {
        loadPath: '/locales/{{lng}}/messages.json'
      }
    }, (err, t) => {
      if (err) console.error(err);
      updateContent();

      // store initial choice
      localStorage.setItem('lng', i18next.language);

      // sync dropdown
      const sel = document.getElementById('lang-select');
      if (sel) sel.value = i18next.language;
    });

  // 2) when the hash changes (e.g. user clicks a "#lang-hi" link) ...
  window.addEventListener('hashchange', () => {
    const hashLang = detectHashLang();
    if (hashLang && hashLang !== i18next.language) {
      i18next.changeLanguage(hashLang, () => {
        updateContent();
        localStorage.setItem('lng', hashLang);
      });
      const sel = document.getElementById('lang-select');
      if (sel) sel.value = hashLang;
    }
  });

  // 3) when user picks from the dropdown, update the hash
  // const sel = document.getElementById('lang-select');
  // if (sel) {
  //   sel.addEventListener('change', e => {
  //     const newLang = e.target.value;
  //     // update hash (triggers the hashchange listener above)
  //     window.location.hash = 'lang-' + newLang;
  //   });
  // }
});

function updateContent() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    el.innerHTML = i18next.t(key);
  });
}
