"""Shared HTML page template for the multi-page forecast site.

All page generators call ``render_page()`` to wrap their content in a
complete HTML5 document with shared header, navigation, and footer.
This replaces the ad-hoc shell assembly that used to live in main.yml.
"""

import html as html_mod
from datetime import datetime, timezone, timedelta

from i18n import T, T_str, bilingual


# ── Page registry ────────────────────────────────────────────────────────────
# Each entry: (href, i18n_key, icon)
NAV_PAGES = [
    ('/',         'nav_dashboard',  ''),
    ('/hourly',   'nav_hourly',     ''),
    ('/surf',     'nav_spots',      ''),
    ('/accuracy', 'nav_accuracy',   ''),
]


def render_page(
    *,
    title_key: str = 'page_title',
    nav_active: str = '/',
    body_html: str = '',
    extra_head: str = '',
    build_utc: str = '',
    download_link: str = '',
    download_name: str = '',
    download_size: str = '',
) -> str:
    """Generate a complete HTML5 page with shared chrome.

    Parameters
    ----------
    title_key : str
        i18n key for the ``<title>`` tag.
    nav_active : str
        The ``href`` of the currently active nav link (e.g. ``'/'``).
    body_html : str
        The page-specific HTML content to inject into ``<main>``.
    extra_head : str
        Additional ``<head>`` content (e.g. page-specific ``<style>``).
    build_utc : str
        ISO-8601 build timestamp for the "last updated" bar.
    download_link, download_name, download_size : str
        Optional GRIB2 download link details.
    """
    if not build_utc:
        build_utc = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    title_en = T_str(title_key, 'en')
    title_zh = T_str(title_key, 'zh')

    # Navigation links
    nav_items = []
    for href, key, icon in NAV_PAGES:
        active = ' class="active"' if href == nav_active else ''
        nav_items.append(
            f'<a href="{href}"{active}>{T(key)}</a>'
        )
    nav_html = '\n              '.join(nav_items)

    # Download bar
    dl_bar = ''
    if download_link:
        safe_link = html_mod.escape(download_link)
        safe_name = html_mod.escape(download_name)
        safe_size = html_mod.escape(download_size)
        dl_bar = f'''
      <div class="download-bar">
        <a href="{safe_link}">{T('download_wrf')}</a>
        <span>{safe_name} &middot; {safe_size}</span>
      </div>'''

    return f'''<!DOCTYPE html>
<html lang="en" id="html-root">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#0f172a">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <link rel="manifest" href="/manifest.json">
  <link rel="apple-touch-icon" href="/icon-192.png">
  <link rel="stylesheet" href="/styles.css">
  <title>{title_en} | {title_zh}</title>
  <script>
  // Language auto-detect: saved pref > browser language > English default
  (function(){{
    var saved = localStorage.getItem('tw-forecast-lang');
    if (saved) {{ document.documentElement.setAttribute('lang', saved); return; }}
    var bLang = (navigator.language || '').toLowerCase();
    if (bLang.startsWith('zh')) document.documentElement.setAttribute('lang', 'zh');
  }})();
  </script>
  {extra_head}
</head>
<body>
  <a href="#main-content" class="skip-nav">Skip to content</a>

  <header class="site-header">
    <div class="header-inner">
      <a href="/" class="site-title-link">
        <h1 class="site-title">
          <span lang="en"><span class="highlight">Taiwan</span> Sail &amp; Surf</span>
          <span lang="zh"><span class="highlight">&#21488;&#28771;</span> &#24070;&#33337;&#34909;&#28010;</span>
        </h1>
      </a>
      <nav class="site-nav" aria-label="Main navigation">
        {nav_html}
      </nav>
      <button class="lang-toggle" onclick="toggleLang()" aria-label="Switch language">
        <span lang="en">&#20013;&#25991;</span><span lang="zh">English</span>
      </button>
    </div>
    <div class="timestamp-bar">
      <span>{T('last_updated')}: <span id="ts">{build_utc}</span></span>
      <span class="age" id="age"></span>
    </div>
  </header>

  <div class="stale-warning" id="stale-warning" role="alert">
    {T('stale_warning')}
    <button onclick="location.reload()">{T('refresh')}</button>
    <button class="stale-dismiss" onclick="this.parentElement.classList.add('dismissed')" aria-label="Dismiss">&times;</button>
  </div>
  {dl_bar}

  <main id="main-content" class="content-wrap">
{body_html}
  </main>

  <footer class="site-footer">
    <div class="footer-inner">
      <span>{bilingual('Data: CWA WRF 3km + ECMWF IFS + WAM', '&#36039;&#26009;&#65306;CWA WRF 3km + ECMWF IFS + WAM')}</span>
      <span class="footer-sep">&middot;</span>
      <span>{bilingual('AI summary by Claude', 'AI &#25688;&#35201;&#30001; Claude &#29986;&#29983;')}</span>
    </div>
  </footer>

  <nav class="bottom-nav" aria-label="Main navigation">
    <a href="/" class="bnav-item">
      <svg class="bnav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
      <span class="bnav-label">{T('nav_dashboard')}</span>
    </a>
    <a href="/hourly" class="bnav-item">
      <svg class="bnav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
      <span class="bnav-label">{T('nav_hourly')}</span>
    </a>
    <a href="/surf" class="bnav-item">
      <svg class="bnav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12c2-3 4-4 6-4s4 2 6 4 4 4 6 4"/><path d="M2 18c2-3 4-4 6-4s4 2 6 4 4 4 6 4"/></svg>
      <span class="bnav-label">{T('nav_spots')}</span>
    </a>
    <a href="/accuracy" class="bnav-item">
      <svg class="bnav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 20V10M12 20V4M6 20v-6"/></svg>
      <span class="bnav-label">{T('nav_accuracy')}</span>
    </a>
  </nav>

  <button id="scroll-top" class="scroll-top" aria-label="Back to top">&#8593;</button>

  <script src="/app.js"></script>
</body>
</html>
'''
