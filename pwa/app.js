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
  document.dispatchEvent(new Event('langchange'));
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

  // Apply to top site-nav links
  var links = document.querySelectorAll('.site-nav a');
  links.forEach(function (a) {
    var href = a.getAttribute('href');
    if (href === path || (path.startsWith('/spots/') && href === '/surf')) {
      a.classList.add('active');
    }
  });

  // Apply same logic to bottom nav links
  var bottomLinks = document.querySelectorAll('.bottom-nav a');
  bottomLinks.forEach(function (a) {
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

// ── Stale warning dismiss ───────────────────────────────────────────────────
(function () {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.stale-dismiss');
    if (!btn) return;
    var warning = document.getElementById('stale-warning');
    if (warning) warning.classList.add('dismissed');
  });
})();

// ── Scroll-to-top button ────────────────────────────────────────────────────
(function () {
  var scrollBtn = document.getElementById('scroll-top');
  if (!scrollBtn) return;

  var throttled = false;
  window.addEventListener('scroll', function () {
    if (throttled) return;
    throttled = true;
    setTimeout(function () {
      throttled = false;
      if (window.scrollY > 400) {
        scrollBtn.classList.add('visible');
      } else {
        scrollBtn.classList.remove('visible');
      }
    }, 100);
  });

  scrollBtn.addEventListener('click', function () {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
})();

// ── Column toggle (tablet) ──────────────────────────────────────────────────
(function () {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.col-toggle');
    if (!btn) return;
    var desktop = btn.closest('.fc-desktop');
    if (!desktop) return;
    var table = desktop.querySelector('.fc-table');
    if (!table) return;
    table.classList.toggle('show-all-cols');

    // Toggle button text: swap visibility of the two span pairs
    var spans = btn.querySelectorAll('span[lang]');
    spans.forEach(function (s) {
      var hidden = s.style.display === 'none';
      s.style.display = hidden ? '' : 'none';
    });
  });
})();

// ── Pull-to-refresh (standalone PWA only) ───────────────────────────────────
(function () {
  if (!window.matchMedia('(display-mode: standalone)').matches) return;

  var startY = 0;
  var pulling = false;
  var indicator = document.createElement('div');
  indicator.className = 'ptr-indicator';
  indicator.textContent = 'Release to refresh';
  indicator.style.cssText = 'position:fixed;top:0;left:50%;transform:translateX(-50%);' +
    'padding:8px 16px;background:#1e293b;color:#93c5fd;border-radius:0 0 8px 8px;' +
    'font-size:13px;z-index:9999;visibility:hidden;transition:opacity 0.2s;opacity:0;';
  document.body.appendChild(indicator);

  document.addEventListener('touchstart', function (e) {
    if (window.scrollY === 0) {
      startY = e.touches[0].clientY;
      pulling = true;
    }
  }, { passive: true });

  document.addEventListener('touchmove', function (e) {
    if (!pulling) return;
    var dy = e.touches[0].clientY - startY;
    if (dy > 80) {
      indicator.style.visibility = 'visible';
      indicator.style.opacity = '1';
    } else {
      indicator.style.visibility = 'hidden';
      indicator.style.opacity = '0';
    }
  }, { passive: true });

  document.addEventListener('touchend', function () {
    if (!pulling) return;
    pulling = false;
    if (indicator.style.visibility === 'visible') {
      location.reload();
    }
    indicator.style.visibility = 'hidden';
    indicator.style.opacity = '0';
  });
})();

// ── Filter count badge ──────────────────────────────────────────────────────
(function () {
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.filter-btn');
    if (!btn) return;
    // Defer count until after the filter click handler has toggled visibility
    setTimeout(function () {
      var visible = document.querySelectorAll('.detail-section:not([hidden])');
      var badge = document.querySelector('.filter-count');
      if (badge) badge.textContent = visible.length;
    }, 0);
  });
})();
