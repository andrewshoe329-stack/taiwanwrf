"""Tests for html_template.py — shared page rendering."""
import html as html_mod

from html_template import render_page, NAV_PAGES


class TestRenderPage:
    """render_page produces valid HTML5 structure."""

    def test_returns_html5_doctype(self):
        page = render_page(body_html="<p>Hello</p>")
        assert page.startswith("<!DOCTYPE html>")

    def test_contains_body_html(self):
        page = render_page(body_html="<p>Test content</p>")
        assert "<p>Test content</p>" in page

    def test_contains_title(self):
        page = render_page(title_key="page_title")
        assert "<title>" in page
        assert "</title>" in page

    def test_active_nav_link(self):
        page = render_page(nav_active="/hourly")
        assert 'class="active"' in page

    def test_build_utc_displayed(self):
        page = render_page(build_utc="2025-01-15T12:00:00Z")
        assert "2025-01-15T12:00:00Z" in page

    def test_default_build_utc_generated(self):
        """When no build_utc provided, a timestamp is still generated."""
        page = render_page(body_html="")
        assert 'id="ts"' in page

    def test_download_bar_present(self):
        page = render_page(
            download_link="https://example.com/data.grb2",
            download_name="test.grb2",
            download_size="5MB",
        )
        assert "download-bar" in page
        assert "test.grb2" in page

    def test_download_bar_absent_without_link(self):
        page = render_page(body_html="<p>No download</p>")
        assert "download-bar" not in page

    def test_download_link_escaped(self):
        page = render_page(
            download_link='https://example.com/file?a=1&b=2',
            download_name='<script>alert(1)</script>',
            download_size='1MB',
        )
        assert '&amp;' in page  # & should be escaped
        assert '&lt;script&gt;' in page  # XSS attempt escaped

    def test_extra_head_injected(self):
        page = render_page(extra_head='<style>.foo{color:red}</style>')
        assert '<style>.foo{color:red}</style>' in page

    def test_lang_toggle_present(self):
        page = render_page(body_html="")
        assert "lang-toggle" in page

    def test_main_content_landmark(self):
        page = render_page(body_html="")
        assert 'id="main-content"' in page

    def test_skip_nav_link(self):
        page = render_page(body_html="")
        assert 'href="#main-content"' in page


class TestNavPages:
    """NAV_PAGES registry is well-formed."""

    def test_nav_pages_not_empty(self):
        assert len(NAV_PAGES) > 0

    def test_nav_pages_have_three_elements(self):
        for entry in NAV_PAGES:
            assert len(entry) == 3, f"NAV_PAGES entry should be (href, key, icon): {entry}"

    def test_nav_pages_start_with_slash(self):
        for href, _key, _icon in NAV_PAGES:
            assert href.startswith("/"), f"NAV_PAGES href should start with /: {href}"
