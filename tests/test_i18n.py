"""Tests for i18n.py — bilingual translation infrastructure."""

from i18n import STRINGS, T, T_str, bilingual, SPOT_DESC_KEYS


class TestStringsDict:
    def test_all_keys_have_both_languages(self):
        for key, val in STRINGS.items():
            assert 'en' in val, f"Key '{key}' missing 'en'"
            assert 'zh' in val, f"Key '{key}' missing 'zh'"

    def test_no_empty_translations(self):
        for key, val in STRINGS.items():
            assert val['en'].strip(), f"Key '{key}' has empty 'en'"
            assert val['zh'].strip(), f"Key '{key}' has empty 'zh'"

    def test_spot_desc_keys_exist(self):
        for spot_id, key in SPOT_DESC_KEYS.items():
            assert key in STRINGS, f"SPOT_DESC_KEYS['{spot_id}'] → '{key}' not in STRINGS"


class TestT:
    def test_output_format(self):
        html = T('good')
        assert 'lang="en"' in html
        assert 'lang="zh"' in html

    def test_contains_both_texts(self):
        html = T('good')
        assert 'Good' in html
        assert '好' in html

    def test_returns_string(self):
        assert isinstance(T('firing'), str)

    def test_missing_key_returns_placeholder(self):
        result = T('nonexistent_key_xyz')
        assert 'nonexistent_key_xyz' in result


class TestTStr:
    def test_english(self):
        assert T_str('firing', 'en') == 'Firing!'

    def test_chinese(self):
        assert T_str('firing', 'zh') == '超讚！'

    def test_returns_plain_string(self):
        result = T_str('good', 'en')
        assert '<span' not in result


class TestBilingual:
    def test_format(self):
        html = bilingual('hello', '你好')
        assert 'lang="en"' in html
        assert 'lang="zh"' in html
        assert 'hello' in html
        assert '你好' in html
