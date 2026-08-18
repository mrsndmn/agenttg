"""Offline emoji substitution for the PNG table renderer."""

from __future__ import annotations

import pytest

from agenttg.emoji import asset_stem, assets_dir, emojify_html


def _img_count(html: str) -> int:
    return html.count('<img class="emoji"')


def test_assets_are_vendored():
    svgs = list(assets_dir().glob("*.svg"))
    assert len(svgs) > 3000, f"twemoji assets missing from {assets_dir()}"


@pytest.mark.parametrize(
    ("sequence", "stem"),
    [
        ("✅", "2705"),
        ("❌", "274c"),
        ("⚠️", "26a0"),  # VS16 stripped
        ("👍🏻", "1f44d-1f3fb"),  # skin tone modifier kept
        ("👩‍💻", "1f469-200d-1f4bb"),  # ZWJ sequence keeps every codepoint
        ("#️⃣", "23-20e3"),  # keycap
    ],
)
def test_asset_stem_matches_twemoji_naming(sequence, stem):
    assert asset_stem(sequence) == stem
    assert (assets_dir() / f"{stem}.svg").exists()


def test_emoji_becomes_inline_svg_data_uri():
    out = emojify_html("<td>✅ 3</td>")
    assert _img_count(out) == 1
    assert "data:image/svg+xml;base64," in out
    assert 'alt="✅"' in out
    assert "3</td>" in out
    assert "http" not in out, "rendering must not reference any remote URL"


def test_zwj_sequence_renders_as_one_image():
    out = emojify_html("<p>👩‍💻</p>")
    assert _img_count(out) == 1


def test_unknown_emoji_is_left_as_text():
    # U+1FAFF has no twemoji asset; it must survive untouched rather than break.
    out = emojify_html("<p>\U0001faff</p>")
    assert out == "<p>\U0001faff</p>"


@pytest.mark.parametrize(
    "text",
    [
        "<td>31</td>",  # bare digits are not keycaps
        "<td>a100.8gpu</td>",
        "<td>2026-08-18 17:33:43</td>",
        "<td>#42 * 7</td>",
        "<td>a → b</td>",  # plain arrow, no twemoji asset
        "<td>│ ├── tree</td>",  # box drawing
        "<td>(c) 2026 ACME (tm)</td>",
    ],
)
def test_ordinary_text_is_untouched(text):
    assert emojify_html(text) == text


def test_tags_and_attributes_are_not_rewritten():
    html = '<img src="x.png" alt="✅"/><td>✅</td>'
    out = emojify_html(html)
    # Only the text node is substituted; the pre-existing tag is passed through.
    assert out.startswith('<img src="x.png" alt="✅"/>')
    assert _img_count(out) == 1


def test_script_and_style_blocks_are_skipped():
    html = "<style>/* ✅ */</style><script>var x = '✅';</script><td>✅</td>"
    out = emojify_html(html)
    assert "<style>/* ✅ */</style>" in out
    assert "var x = '✅';" in out
    assert _img_count(out) == 1


def test_custom_assets_dir_is_honoured(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTTG_TWEMOJI_ASSETS_DIR", str(tmp_path))
    assert emojify_html("<td>✅</td>") == "<td>✅</td>"
