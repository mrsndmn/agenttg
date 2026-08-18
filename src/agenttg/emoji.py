"""Offline emoji rendering for the PNG table renderer.

The HTML handed to ``wkhtmltoimage`` used to pull ``twemoji.min.js`` off a public
CDN and let it rewrite emoji in the browser.  That made every table render an
outbound network call: on a host behind a flaky proxy the fetch fails, and
``wkhtmltoimage`` then **exits non-zero for the whole render** (its network-error
exit code is set independently of ``--load-error-handling``), so a perfectly good
PNG was thrown away.

Here we do the same substitution *before* the browser ever runs, against SVGs
vendored under ``assets/twemoji/svg``.  Rendering is therefore fully offline and
deterministic.  Anything without a vendored asset is left as literal text.

Asset names follow twemoji's own convention: codepoints as lowercase hex joined
by ``-``, with ``U+FE0F`` (variation selector 16) stripped unless the sequence is
a ZWJ sequence.
"""

from __future__ import annotations

import base64
import html
import os
import re
from functools import cache
from pathlib import Path

_ZWJ = "‍"
_VS16 = "️"

_ASSETS_DIR_ENV = "AGENTTG_TWEMOJI_ASSETS_DIR"
_DEFAULT_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "twemoji" / "svg"

# Characters that may take part in an emoji sequence.  Bare digits, ``#`` and
# ``*`` are included on purpose: they only form emoji as keycaps, and since no
# bare-digit asset exists (there is no ``31.svg``) the longest-match lookup below
# leaves ordinary numbers untouched.  The same argument covers box-drawing and
# other symbols swept up by the U+2190-U+2BFF range -- twemoji ships no asset for
# them, so they stay literal.  ``©``/``®``/``™`` are excluded from the run class
# entirely: they are ordinary punctuation far more often than they are emoji, so
# they are matched only in their explicit ``+ U+FE0F`` form.
_SEQUENCE_CHARS = (
    "0-9#*"
    "‍⃣️"  # ZWJ, combining enclosing keycap, variation selector 16
    "←-⯿"  # arrows, misc technical, geometric shapes, dingbats
    "〰〽㊗㊙"
    "\U0001f000-\U0001faff"  # the emoji planes proper
    "\U000e0020-\U000e007f"  # tag characters (subdivision flags)
)
_SCAN_RE = re.compile(f"[©®™]{_VS16}|[{_SEQUENCE_CHARS}]+")

_TAG_RE = re.compile(r"(<[^>]*>)")
_SKIP_BLOCK_RE = re.compile(r"(?is)((?:<script\b.*?</script\s*>)|(?:<style\b.*?</style\s*>))")


def assets_dir() -> Path:
    """Directory holding the vendored twemoji SVGs (``AGENTTG_TWEMOJI_ASSETS_DIR``)."""
    override = os.environ.get(_ASSETS_DIR_ENV, "").strip()
    return Path(override) if override else _DEFAULT_ASSETS_DIR


def asset_stem(sequence: str) -> str:
    """Return twemoji's asset name for *sequence*, sans extension.

    Mirrors twemoji's ``grabTheRightIcon``: ``U+FE0F`` is dropped unless the
    sequence contains a zero-width joiner.
    """
    if _ZWJ not in sequence:
        sequence = sequence.replace(_VS16, "")
    return "-".join(f"{ord(ch):x}" for ch in sequence)


_SVG_OPEN_RE = re.compile(rb"<svg\b([^>]*)>")
_VIEWBOX_RE = re.compile(rb"""viewBox\s*=\s*["']\s*[-\d.]+\s+[-\d.]+\s+([\d.]+)\s+([\d.]+)""")


def _with_intrinsic_size(raw: bytes) -> bytes:
    """Give a ``viewBox``-only SVG explicit ``width``/``height`` attributes.

    twemoji's SVGs declare a ``viewBox`` and nothing else.  wkhtmltoimage's
    ancient QtWebKit will not derive an intrinsic width from that, so it renders
    the image at half the width the CSS asks for; spelling the size out fixes the
    aspect ratio.
    """
    match = _SVG_OPEN_RE.search(raw)
    if match is None or b"width=" in match.group(1):
        return raw
    box = _VIEWBOX_RE.search(match.group(1))
    if box is None:
        return raw
    attrs = b' width="%s" height="%s"' % (box.group(1), box.group(2))
    return raw[: match.end(1)] + attrs + raw[match.end(1) :]


@cache
def _data_uri(stem: str, directory: str) -> str | None:
    """Return a base64 ``data:`` URI for one asset, or None when it is absent."""
    if not stem:
        return None
    try:
        raw = (Path(directory) / f"{stem}.svg").read_bytes()
    except OSError:
        return None
    payload = base64.b64encode(_with_intrinsic_size(raw)).decode("ascii")
    return "data:image/svg+xml;base64," + payload


def _render_run(run: str, directory: str, class_name: str) -> str:
    """Replace every vendored emoji in *run* with an ``<img>``, longest match first."""
    out: list[str] = []
    i = 0
    while i < len(run):
        for end in range(len(run), i, -1):
            uri = _data_uri(asset_stem(run[i:end]), directory)
            if uri is None:
                continue
            alt = html.escape(run[i:end], quote=True)
            out.append(f'<img class="{class_name}" src="{uri}" alt="{alt}"/>')
            i = end
            break
        else:
            out.append(run[i])
            i += 1
    return "".join(out)


def emojify_html(html_text: str, class_name: str = "emoji") -> str:
    """Rewrite emoji in *html_text* text nodes as inline SVG ``<img>`` elements.

    Markup is left alone: tags, and whole ``<script>``/``<style>`` blocks, pass
    through untouched, so only rendered text is affected.  Emoji with no vendored
    asset stay literal.
    """
    directory = str(assets_dir())

    def _sub(match: re.Match[str]) -> str:
        return _render_run(match.group(0), directory, class_name)

    parts: list[str] = []
    for block in _SKIP_BLOCK_RE.split(html_text):
        if not block:
            continue
        if _SKIP_BLOCK_RE.fullmatch(block):
            parts.append(block)
            continue
        for chunk in _TAG_RE.split(block):
            parts.append(chunk if chunk.startswith("<") else _SCAN_RE.sub(_sub, chunk))
    return "".join(parts)
