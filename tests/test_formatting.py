"""Unit tests for agenttg formatting functions."""

from __future__ import annotations

from agenttg import (
    escape_html,
    escape_markdownv2,
    format_markdown,
    split_body_into_segments,
    split_text,
)

# ---------------------------------------------------------------------------
# Complex test input (ML research output)
# ---------------------------------------------------------------------------

FINAL_OUTPUT_MESSAGE = """
[TEST] This is a test message.

## Summary

### Best model per benchmark (all experiments)

| Benchmark | Best model | Score |
|-----------|-----------|-------|
| ARC | ft_emb scaled (Job 4) | **50.03** |
| HellaSwag | ft_emb POC (Job 2) | **30.23** (baseline 1B: 30.13) |
| MMLU | original 1B | **40.80** (both fine-tunes regress) |
| MMLU-Pro | ft_linear_proj scaled (Job 3) | **10.28** |

### Key findings

1. **POC collapse (Job 1) was a training-stability artefact, not an architectural failure.** At scale (10k steps, 4 GPU, full data), the linear-projection model produces fully coherent outputs. The collapse in the POC was likely due to the freshly-initialised `linear` layer receiving large early Adam updates that overwhelmed the frozen embedding signal.

2. **MMLU regression is the dominant concern at 10k steps.** Both scaled fine-tuning modes regress on MMLU: plain embeddings −4.0 pts, linear projection −9.4 pts. This points to catastrophic forgetting of knowledge recall with extended training.

3. **Linear projection shows a consistent MMLU-Pro advantage** (+0.56 vs plain embeddings, +0.79 vs original 1B). The architecture may genuinely help with harder multi-step reasoning, but hurts factual recall (MMLU).

4. **HellaSwag regresses slightly for both scaled models** (~1–2 pts), suggesting the training distribution doesn't align with commonsense completion.

### Anomalies

- The POC linear-projection collapse (HellaSwag=0.07, MMLU=0.00) was extreme and is fully explained by the missing zero-init on the `linear` layer. The scaled run proves the architecture works when stable.

### Recommended next steps (priority order)

1. **Evaluate intermediate checkpoints (2k, 5k steps)** of the scaled runs to find the MMLU inflection point — this is the cheapest insight and should be done before any new training.
2. **Explicitly zero-init the `linear` layer** and re-run the POC (500 steps) to get a clean, collapse-free baseline on the small scale.
3. **Lower LR for the projection path** (separate param group, 0.1× multiplier) to reduce MMLU forgetting while preserving the MMLU-Pro gains.
4. **Add weight decay / L2 regularisation** on `low_dim_embed` + `linear` parameters to constrain projection magnitude.
5. **Ablate `embedding_low_dim`** (64 / 128 / 256) once stability is confirmed — the MMLU-Pro advantage may be rank-sensitive.
"""


# ---------------------------------------------------------------------------
# escape_markdownv2 tests
# ---------------------------------------------------------------------------


def test_escape_markdownv2_preserves_bold_and_code():
    text = "The `linear` layer and **POC collapse** matter."
    out = escape_markdownv2(text)
    assert "PLACEHOLDER" not in out
    assert "`" in out and "linear" in out
    assert "*" in out and "POC collapse" in out
    assert out.strip().endswith("\\.") or out.strip().endswith(".")


def test_escape_markdownv2_no_placeholders_in_output():
    texts = [
        "**bold** and `code` and __underline__",
        "1. **Evaluate** (2k, 5k steps) and `linear` layer.",
        "`low_dim_embed` + `linear` parameters",
    ]
    for text in texts:
        out = escape_markdownv2(text)
        assert "PLACEHOLDER" not in out, f"Placeholder leaked for input: {text!r}"
    out0 = escape_markdownv2(texts[0])
    assert "*" in out0 and "`" in out0


def test_escape_markdownv2_nested_bold_and_code():
    text = "5. **Ablate `embedding_low_dim`** (64 / 128 / 256) once stability is confirmed."
    out = escape_markdownv2(text)
    assert not any(ord(c) >= 0xE000 and ord(c) <= 0xE0FF for c in out), "Placeholder char leaked"
    assert "embedding_low_dim" in out
    assert "`" in out and "*" in out


def test_escape_markdownv2_empty_string():
    assert escape_markdownv2("") == ""


def test_escape_markdownv2_plain_text():
    out = escape_markdownv2("Hello world")
    assert out == "Hello world"


def test_escape_markdownv2_special_chars():
    out = escape_markdownv2("Price: $10.00 (50% off)")
    assert "\\." in out
    assert "\\(" in out
    assert "\\)" in out


# ---------------------------------------------------------------------------
# format_markdown tests
# ---------------------------------------------------------------------------


def test_format_markdown_wraps_tables_in_code_block():
    text = """| A | B |
|---|---|
| 1 | 2 |"""
    out = format_markdown(text)
    assert out.startswith("```")
    assert "| A | B |" in out
    assert "| 1 | 2 |" in out
    assert out.rstrip().endswith("```")


def test_format_markdown_headers_with_emoji_and_bold():
    text = "## Summary\n\n### Key findings"
    out = format_markdown(text)
    assert "➡️ *" in out
    assert "Summary" in out
    assert "Key findings" in out
    assert out.count("➡️") == 2


def test_format_markdown_no_placeholders_in_output():
    out = format_markdown(FINAL_OUTPUT_MESSAGE.strip())
    assert "PLACEHOLDER" not in out
    assert "__PLACEHOLDER" not in out
    assert "linear" in out
    assert "Key findings" in out
    assert "POC" in out


def test_format_markdown_preserves_bold_and_code_in_paragraphs():
    text = """### Section

1. **First item** with `code` here.
2. **Second** and `more_code`."""
    out = format_markdown(text)
    assert "PLACEHOLDER" not in out
    assert "First item" in out
    assert "code" in out
    assert "Second" in out
    assert "more" in out and "code" in out


# ---------------------------------------------------------------------------
# split_text tests
# ---------------------------------------------------------------------------


def test_split_text_short_text():
    assert split_text("hello") == ["hello"]


def test_split_text_empty_text():
    assert split_text("") == []


def test_split_text_exact_limit():
    text = "a" * 4096
    result = split_text(text, limit=4096)
    assert len(result) == 1
    assert result[0] == text


def test_split_text_prefers_newline_boundary():
    line1 = "a" * 2500
    line2 = "b" * 2500
    text = line1 + "\n" + line2
    result = split_text(text, limit=4096)
    assert len(result) == 2
    assert result[0] == line1 + "\n"
    assert result[1] == line2


def test_split_text_long_single_line():
    text = "x" * 5000
    result = split_text(text, limit=4096)
    assert len(result) == 2
    assert len(result[0]) == 4096
    assert result[0] + result[1] == text


# ---------------------------------------------------------------------------
# escape_html tests
# ---------------------------------------------------------------------------


def test_escape_html_all_special_chars():
    assert (
        escape_html("<script>alert('xss')</script>") == "&lt;script&gt;alert('xss')&lt;/script&gt;"
    )
    assert escape_html("A & B") == "A &amp; B"
    assert escape_html("a < b > c") == "a &lt; b &gt; c"


def test_escape_html_no_special_chars():
    assert escape_html("hello world") == "hello world"


# ---------------------------------------------------------------------------
# split_body_into_segments tests
# ---------------------------------------------------------------------------


def test_split_body_into_segments_text_only():
    segments = split_body_into_segments("Hello\nWorld")
    assert len(segments) == 1
    assert segments[0].kind == "text"
    assert segments[0].content == "Hello\nWorld"


def test_split_body_into_segments_table():
    body = "intro\n| A | B |\n|---|---|\n| 1 | 2 |\noutro"
    segments = split_body_into_segments(body)
    assert len(segments) == 3
    assert segments[0].kind == "text"
    assert segments[1].kind == "table"
    assert segments[2].kind == "text"
    assert "| A | B |" in segments[1].content


def test_split_body_into_segments_mixed_content():
    body = FINAL_OUTPUT_MESSAGE.strip()
    segments = split_body_into_segments(body)
    kinds = [s.kind for s in segments]
    assert "text" in kinds
    assert "table" in kinds
