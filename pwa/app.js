/* ═══════════════════════════════════════════════════════════════════════════
   Taiwan Sail & Surf Forecast — Shared JavaScript
   Extracted from inline scripts for multi-page PWA support.
   ═══════════════════════════════════════════════════════════════════════════ */

// ── Language toggle ─────────────────────────────────────────────────────────
function toggleLang() {
  var html = document.documentElement;
  var next = html.getAttribute('lang') === 'zh' ? 'en' : 'zh';
  html.setAttribute('lang', next);
  localStorage.setItem('tw-forecast-lang', next);
}

// ── Timestamp age tracking ──────────────────────────────────────────────────
(function () {
  var tsEl = document.getElementById('ts');
  var ageEl = document.getElementById('age');
  if (!tsEl || !ageEl) return;

  var ts = new Date(tsEl.textContent);
  if (isNaN(ts.getTime())) return;

  function update() {
    var diff = Date.now() - ts.getTime();
    var m = Math.round(diff / 60000);
    var h = Math.round(diff / 3600000);
    if (m < 60) ageEl.textContent = m + 'm ago';
    else ageEl.textContent = h + 'h ago';
    ageEl.className = 'age ' + (h < 8 ? 'age-fresh' : h < 24 ? 'age-stale' : 'age-old');

    // Show stale banner if data is old (>6h)
    if (h >= 6) {
      var sw = document.getElementById('stale-warning');
      if (sw && !sw.classList.contains('visible')) {
        sw.classList.add('visible');
      }
    }
  }
  update();
  setInterval(update, 60000);
})();

// ── Service worker registration ─────────────────────────────────────────────
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(function () {});
  navigator.serviceWorker.addEventListener('message', function (e) {
    if (e.data && e.data.type === 'CACHE_HIT') {
      var sw = document.getElementById('stale-warning');
      if (sw) sw.classList.add('visible');
    }
  });
}

// ── Active nav tracking (highlight current page) ────────────────────────────
(function () {
  var path = window.location.pathname;
  // Normalize: strip trailing slash except for root
  if (path !== '/' && path.endsWith('/')) path = path.slice(0, -1);
  // Also handle .html extension
  path = path.replace(/\.html$/, '');
  // Map /index to /
  if (path === '/index') path = '/';

  var links = document.querySelectorAll('.site-nav a');
  links.forEach(function (a) {
    var href = a.getAttribute('href');
    if (href === path || (path.startsWith('/spots/') && href === '/surf')) {
      a.classList.add('active');
    }
  });
})();

// ── Smooth scroll for anchor links ──────────────────────────────────────────
document.addEventListener('click', function (e) {
  var target = e.target.closest('a[href^="#"]');
  if (!target) return;
  var id = target.getAttribute('href').slice(1);
  var el = document.getElementById(id);
  if (el) {
    e.preventDefault();
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
});

// ── Intersection Observer for on-page section nav ───────────────────────────
(function () {
  var sections = document.querySelectorAll('section[id]');
  var navLinks = document.querySelectorAll('.page-nav a');
  if (!window.IntersectionObserver || !sections.length || !navLinks.length) return;

  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        navLinks.forEach(function (a) { a.classList.remove('active'); });
        var link = document.querySelector('.page-nav a[href="#' + entry.target.id + '"]');
        if (link) link.classList.add('active');
      }
    });
  }, { rootMargin: '-20% 0px -60% 0px' });
  sections.forEach(function (s) { observer.observe(s); });
})();
