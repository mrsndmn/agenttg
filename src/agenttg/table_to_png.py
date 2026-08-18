"""Render a markdown table to PNG using pandoc + wkhtmltoimage.

System requirements: pandoc, wkhtmltoimage (from wkhtmltopdf package).
Python requirements: Pillow.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .emoji import emojify_html

logger = logging.getLogger("agenttg")

_WKHTMLTOIMAGE_LOCAL = Path.home() / ".local/wkhtmltox/usr/local/bin/wkhtmltoimage"
_PANDOC_LOCAL = Path.home() / ".local/pandoc/usr/bin/pandoc"

# Neither binary should ever outlive a chat round trip.  Without a cap a stalled
# subprocess wedges the caller indefinitely; raising instead lets the render
# chain fall through to the next mode.
_PANDOC_TIMEOUT_S = 30
_WKHTMLTOIMAGE_TIMEOUT_S = 120


def _resolve_binary(name: str, local_path: Path, custom_path: str | None = None) -> str:
    """Return path to a binary.

    Search order: custom_path > ~/.local install > system PATH.
    Raises RuntimeError if not found.
    """
    if custom_path and Path(custom_path).exists():
        return custom_path
    if local_path.exists():
        return str(local_path)
    system_path = shutil.which(name)
    if system_path:
        return system_path
    raise RuntimeError(f"{name} not found. Install via:\n  bash scripts/install_deps_local.sh\n")


def _resolve_wkhtmltoimage(custom_path: str | None = None) -> str:
    return _resolve_binary("wkhtmltoimage", _WKHTMLTOIMAGE_LOCAL, custom_path)


def _resolve_pandoc() -> str:
    return _resolve_binary("pandoc", _PANDOC_LOCAL)


_STYLE_BLOCK = """
<style>
  body {
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    margin: 16px;
    width: fit-content;
    box-sizing: border-box;
  }
  table {
    border-collapse: collapse;
    font-size: 14px;
    table-layout: auto;
    box-sizing: border-box;
  }
  th, td {
    border: 1px solid #cbd5e1;
    padding: 10px 12px;
    text-align: left;
    box-sizing: border-box;
    white-space: nowrap;
  }
  th { background: #94a3b8; color: #1e293b; font-weight: 600; }
  th:nth-child(n+3), td:nth-child(n+3) { text-align: right; }
  tbody tr:nth-child(even) { background: #f1f5f9; }
  tbody tr:hover { background: #e2e8f0; }
  td.best { background: #bbf7d0; font-weight: 600; }
  img.emoji {
    height: 2em !important;
    width: 2em !important;
    vertical-align: -0.25em;
    margin: 0 0.1em;
  }
</style>
"""


def _make_script_block(highlight_max: bool) -> str:
    """Generate the JavaScript block with conditional highlighting logic."""
    highlight_code = ""
    if highlight_max:
        highlight_code = """
  function isNumericalColumn(col) {
    var hasNumber = false;
    for (var r = 0; r < rows.length; r++) {
      var text = (rows[r].cells[col].textContent || '').trim().replace(/,/g, '');
      if (text === '') continue;
      var n = parseFloat(text);
      if (isNaN(n)) return false;
      hasNumber = true;
    }
    return hasNumber;
  }

  for (var col = 0; col < numCols; col++) {
    if (!isNumericalColumn(col)) continue;
    var values = [];
    for (var r = 0; r < rows.length; r++) {
      var text = (rows[r].cells[col].textContent || '').trim().replace(/,/g, '');
      var n = parseFloat(text);
      values.push(isNaN(n) ? -Infinity : n);
    }
    var maxVal = Math.max.apply(null, values);
    for (var r = 0; r < rows.length; r++) {
      if (values[r] === maxVal) rows[r].cells[col].classList.add('best');
    }
  }
"""

    return f"""
<script>
(function() {{
  var table = document.querySelector('table');
  if (!table || !table.tBodies.length) return;
  var rows = table.tBodies[0].rows;
  var numCols = rows[0].cells.length;
{highlight_code}
  if (table) {{
    var body = document.body;
    var tableWidth = table.scrollWidth;
    var margin = 2 * 16;
    var adaptiveWidth = tableWidth + margin;
    body.style.width = adaptiveWidth + 'px';
  }}
}})();
</script>
"""


def _run(argv: list[str], timeout: int, what: str) -> subprocess.CompletedProcess[str]:
    """Run *argv*, turning a stall into a RuntimeError instead of hanging forever."""
    try:
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"{what} timed out after {timeout}s") from exc


def _is_usable_png(path: Path) -> bool:
    """True when *path* holds an image PIL can decode."""
    try:
        with Image.open(path) as img:
            img.load()
    except Exception:
        return False
    return True


def _is_white(pixel: tuple[int, int, int], white_threshold: int) -> bool:
    r, g, b = pixel
    return r >= white_threshold and g >= white_threshold and b >= white_threshold


def _crop_right_white_padding(
    path: Path,
    white_threshold: int = 250,
    margin: int = 1,
) -> None:
    """Crop image in-place so right white padding equals left white padding."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    pixels = img.load()

    left_padding = 0
    for x in range(w):
        for y in range(h):
            if not _is_white(pixels[x, y], white_threshold):
                break
        else:
            left_padding = x + 1
            continue
        break

    right_content = -1
    for x in range(w - 1, -1, -1):
        for y in range(h):
            if not _is_white(pixels[x, y], white_threshold):
                right_content = x
                break
        else:
            continue
        break

    if right_content < 0:
        return
    new_width = right_content + margin + left_padding
    if new_width < w:
        img.crop((0, 0, new_width, h)).save(path)


def md_table_to_png(
    md_content: str,
    output_path: Path | None = None,
    width: int = 2100,
    highlight_max: bool = False,
    wkhtmltoimage_path: str | None = None,
) -> Path:
    """Convert a markdown table string to a PNG image file.

    Args:
        md_content: Markdown table source (e.g. "| a | b |\\n|---|---|\\n| 1 | 2 |").
        output_path: Where to write the PNG. If None, a temporary file is used.
        width: Output image width in pixels.
        highlight_max: If True, highlight cells with maximum values in numerical columns.
        wkhtmltoimage_path: Custom path to wkhtmltoimage binary.

    Returns:
        Path to the created PNG file. Caller may read bytes or move/delete the file.
    """
    md_path: Path
    own_md = False
    if output_path is None:
        output_path = Path(tempfile.mktemp(suffix=".png"))
    # Cleared up front so "did wkhtmltoimage produce an image?" below can never
    # be answered by a leftover file from an earlier render.
    output_path.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(md_content)
        md_path = Path(f.name)
        own_md = True

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            html_path = Path(f.name)

        try:
            result = _run(
                [
                    _resolve_pandoc(),
                    str(md_path),
                    "-f",
                    "markdown",
                    "-t",
                    "html",
                    "--standalone",
                    "-o",
                    str(html_path),
                ],
                _PANDOC_TIMEOUT_S,
                "pandoc",
            )
            if result.returncode != 0:
                raise RuntimeError(f"pandoc error: {result.stderr}")

            html_content = emojify_html(html_path.read_text(encoding="utf-8"))
            if "</head>" in html_content:
                html_content = html_content.replace("</head>", _STYLE_BLOCK + "</head>")
            if "</body>" in html_content:
                html_content = html_content.replace(
                    "</body>", _make_script_block(highlight_max) + "</body>"
                )
            html_path.write_text(html_content, encoding="utf-8")

            result = _run(
                [
                    _resolve_wkhtmltoimage(wkhtmltoimage_path),
                    "--width",
                    str(width),
                    "--enable-smart-width",
                    "--enable-local-file-access",
                    "--load-error-handling",
                    "ignore",
                    "--load-media-error-handling",
                    "ignore",
                    "--quiet",
                    str(html_path),
                    str(output_path),
                ],
                _WKHTMLTOIMAGE_TIMEOUT_S,
                "wkhtmltoimage",
            )
            # wkhtmltoimage exits non-zero when *any* asset failed to load -- a
            # remote image in a table cell, say -- even though it went on to
            # render and write a complete PNG, and even with the load-error
            # handlers above set to "ignore".  Judge it by its output, not its
            # exit code, and only fail when there is no usable image.
            if result.returncode != 0:
                if not _is_usable_png(output_path):
                    raise RuntimeError(f"wkhtmltoimage error: {result.stderr.strip()}")
                logger.debug(
                    "wkhtmltoimage exited %s but produced a valid PNG: %s",
                    result.returncode,
                    result.stderr.strip(),
                )

            _crop_right_white_padding(output_path)
            return output_path
        finally:
            if html_path.exists():
                html_path.unlink()
    finally:
        if own_md and md_path.exists():
            md_path.unlink()
