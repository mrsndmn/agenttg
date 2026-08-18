"""Renderer robustness: no network, bounded runtime, judged by output not exit code."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from PIL import Image

from agenttg import table_to_png as ttp


@pytest.fixture
def stub_binaries(monkeypatch):
    monkeypatch.setattr(ttp, "_resolve_pandoc", lambda: "pandoc")
    monkeypatch.setattr(ttp, "_resolve_wkhtmltoimage", lambda custom=None: "wkhtmltoimage")


def _fake_run(png_bytes: bytes | None, rc: int, stderr: str = ""):
    """Return a subprocess.run stand-in: pandoc succeeds, wkhtmltoimage is scripted."""

    def run(argv, capture_output=True, text=True, timeout=None):
        if argv[0] == "pandoc":
            Path(argv[-1]).write_text(
                "<html><head></head><body><table><tbody>"
                "<tr><td>✅ 3</td></tr></tbody></table></body></html>"
            )
            return subprocess.CompletedProcess(argv, 0, "", "")
        if png_bytes is not None:
            Path(argv[-1]).write_bytes(png_bytes)
        return subprocess.CompletedProcess(argv, rc, "", stderr)

    return run


@pytest.fixture
def png_bytes(tmp_path):
    path = tmp_path / "seed.png"
    Image.new("RGB", (40, 20), "white").save(path)
    return path.read_bytes()


def test_no_remote_asset_is_referenced(stub_binaries, monkeypatch, tmp_path, png_bytes):
    """The generated HTML must not reach out to any network resource."""
    seen: dict[str, str] = {}

    def run(argv, capture_output=True, text=True, timeout=None):
        if argv[0] == "pandoc":
            Path(argv[-1]).write_text(
                "<html><head></head><body><table><tbody><tr><td>✅ 3</td></tr></tbody></table></body></html>"
            )
            return subprocess.CompletedProcess(argv, 0, "", "")
        seen["html"] = Path(argv[-2]).read_text()
        Path(argv[-1]).write_bytes(png_bytes)
        return subprocess.CompletedProcess(argv, 0, "", "")

    monkeypatch.setattr(ttp.subprocess, "run", run)
    ttp.md_table_to_png("| a |\n|---|\n| ✅ |", output_path=tmp_path / "out.png")

    assert "twemoji.maxcdn" not in seen["html"]
    assert "http://" not in seen["html"] and "https://" not in seen["html"].replace(
        'xmlns="http://www.w3.org/', ""
    )
    assert "data:image/svg+xml;base64," in seen["html"], "emoji should be inlined"


def test_nonzero_exit_is_tolerated_when_a_valid_png_was_written(
    stub_binaries, monkeypatch, tmp_path, png_bytes
):
    """wkhtmltoimage exits 1 on any asset load error even after rendering fine."""
    monkeypatch.setattr(
        ttp.subprocess,
        "run",
        _fake_run(
            png_bytes, rc=1, stderr="Exit with code 1 due to network error: UnknownNetworkError"
        ),
    )
    out = ttp.md_table_to_png("| a |\n|---|\n| 1 |", output_path=tmp_path / "out.png")
    assert out.exists()


def test_nonzero_exit_without_an_image_still_fails(stub_binaries, monkeypatch, tmp_path):
    monkeypatch.setattr(ttp.subprocess, "run", _fake_run(None, rc=1, stderr="boom"))
    with pytest.raises(RuntimeError, match="wkhtmltoimage error"):
        ttp.md_table_to_png("| a |\n|---|\n| 1 |", output_path=tmp_path / "out.png")


def test_truncated_output_is_not_mistaken_for_success(stub_binaries, monkeypatch, tmp_path):
    monkeypatch.setattr(ttp.subprocess, "run", _fake_run(b"\x89PNG\r\n\x1a\n truncated", rc=1))
    with pytest.raises(RuntimeError, match="wkhtmltoimage error"):
        ttp.md_table_to_png("| a |\n|---|\n| 1 |", output_path=tmp_path / "out.png")


def test_stale_output_file_is_not_mistaken_for_success(
    stub_binaries, monkeypatch, tmp_path, png_bytes
):
    stale = tmp_path / "out.png"
    stale.write_bytes(png_bytes)
    monkeypatch.setattr(ttp.subprocess, "run", _fake_run(None, rc=1, stderr="boom"))
    with pytest.raises(RuntimeError, match="wkhtmltoimage error"):
        ttp.md_table_to_png("| a |\n|---|\n| 1 |", output_path=stale)


def test_a_stalled_binary_raises_instead_of_hanging(stub_binaries, monkeypatch, tmp_path):
    def run(argv, capture_output=True, text=True, timeout=None):
        assert timeout, "every subprocess must be bounded"
        if argv[0] == "pandoc":
            Path(argv[-1]).write_text("<html><head></head><body></body></html>")
            return subprocess.CompletedProcess(argv, 0, "", "")
        raise subprocess.TimeoutExpired(argv, timeout)

    monkeypatch.setattr(ttp.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="timed out"):
        ttp.md_table_to_png("| a |\n|---|\n| 1 |", output_path=tmp_path / "out.png")
