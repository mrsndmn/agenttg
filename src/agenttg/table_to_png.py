"""Render a markdown table to PNG using pandoc + wkhtmltoimage.

System requirements: pandoc, wkhtmltoimage (from wkhtmltopdf package).
Python requirements: Pillow.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

_WKHTMLTOIMAGE_LOCAL = Path.home() / ".local/wkhtmltox/usr/local/bin/wkhtmltoimage"


def _resolve_wkhtmltoimage(custom_path: str | None = None) -> str:
    """Return path to wkhtmltoimage.

    Search order: custom_path > ~/.local install > system PATH.
    Raises RuntimeError if not found.
    """
    if custom_path and Path(custom_path).exists():
        return custom_path
    if _WKHTMLTOIMAGE_LOCAL.exists():
        return str(_WKHTMLTOIMAGE_LOCAL)
    system_path = shutil.which("wkhtmltoimage")
    if system_path:
        return system_path
    raise RuntimeError(
        "wkhtmltoimage not found. Install wkhtmltopdf:\n"
        "  apt-get install wkhtmltopdf\n"
        "  # or download from https://wkhtmltopdf.org/downloads.html"
    )


_STYLE_BLOCK = """
<style>
  body {
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    margin: 16px;
    width: fit-content;
    max-width: 100%;
    box-sizing: border-box;
  }
  table {
    border-collapse: collapse;
    width: 100%;
    max-width: 100%;
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

_TWEMOJI_SCRIPT = """
<script src="https://twemoji.maxcdn.com/v/latest/twemoji.min.js" crossorigin="anonymous"></script>
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
  if (typeof twemoji !== 'undefined') {{
    twemoji.parse(document.body, {{ folder: '72x72', ext: '.png', className: 'emoji' }});
  }}
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
    body.style.maxWidth = '100%';
  }}
}})();
</script>
"""


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
    highlight_max: bool = True,
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
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
        f.write(md_content)
        md_path = Path(f.name)
        own_md = True

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False) as f:
            html_path = Path(f.name)

        try:
            result = subprocess.run(
                [
                    "pandoc",
                    str(md_path),
                    "-f",
                    "markdown",
                    "-t",
                    "html",
                    "--standalone",
                    "-o",
                    str(html_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"pandoc error: {result.stderr}")

            html_content = html_path.read_text(encoding="utf-8")
            if "</head>" in html_content:
                html_content = html_content.replace("</head>", _STYLE_BLOCK + "</head>")
            if "</body>" in html_content:
                script_block = _make_script_block(highlight_max)
                html_content = html_content.replace(
                    "</body>", _TWEMOJI_SCRIPT + script_block + "</body>"
                )
            html_path.write_text(html_content, encoding="utf-8")

            result = subprocess.run(
                [
                    _resolve_wkhtmltoimage(wkhtmltoimage_path),
                    "--width",
                    str(width),
                    "--enable-local-file-access",
                    "--quiet",
                    str(html_path),
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(f"wkhtmltoimage error: {result.stderr}")

            _crop_right_white_padding(output_path)
            return output_path
        finally:
            if html_path.exists():
                html_path.unlink()
    finally:
        if own_md and md_path.exists():
            md_path.unlink()
