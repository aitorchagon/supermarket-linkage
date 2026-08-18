"""Unit tests for InputValidator and postal-code checks."""

from supermarket_linkage.consts import (
    MAX_LINE_LENGTH,
    MAX_LINES,
    MAX_TOTAL_BYTES,
    WARN_LINES,
)
from supermarket_linkage.validation.input_validator import InputValidator
from supermarket_linkage.validation.postal_code_validator import is_valid_postal_code


def test_accepts_single_line() -> None:
    result = InputValidator().validate("arroz basmati 1500 g")
    assert result.ok
    assert result.lines == ["arroz basmati 1500 g"]


def test_accepts_normal_ten_line_list() -> None:
    text = "\n".join(f"item {i}" for i in range(10))
    result = InputValidator().validate(text)
    assert result.ok
    assert result.error is None
    assert len(result.lines) == 10
    assert result.warnings == []


def test_rejects_over_max_lines() -> None:
    text = "\n".join(f"item {i}" for i in range(MAX_LINES + 1))
    result = InputValidator().validate(text)
    assert not result.ok
    assert result.lines == []
    assert "Too many lines" in (result.error or "")


def test_rejects_over_max_total_bytes() -> None:
    # Unique lines so we fail on bytes, not duplicate ratio.
    chunk = "x" * 80
    lines = [f"{i:04d}{chunk}" for i in range(700)]
    text = "\n".join(lines)
    assert len(text.encode("utf-8")) > MAX_TOTAL_BYTES
    result = InputValidator().validate(text)
    assert not result.ok
    assert "bytes" in (result.error or "").lower()


def test_rejects_overlong_line() -> None:
    text = "a" * (MAX_LINE_LENGTH + 100)
    result = InputValidator().validate(text)
    assert not result.ok
    assert "characters" in (result.error or "")


def test_rejects_duplicate_spam() -> None:
    text = "\n".join(["leche entera 1l"] * 100)
    result = InputValidator().validate(text)
    assert not result.ok
    assert "Duplicate" in (result.error or "")


def test_strips_null_bytes_and_other_controls() -> None:
    text = "leche\x00 entera\x07 1l\npan\x1f integral"
    result = InputValidator().validate(text)
    assert result.ok
    assert result.lines == ["leche entera 1l", "pan integral"]


def test_skips_empty_lines() -> None:
    text = "a\n\n  \n\tb\n"
    result = InputValidator().validate(text)
    assert result.ok
    assert result.lines == ["a", "b"]


def test_rejects_empty_paste() -> None:
    result = InputValidator().validate("\n\n  \n")
    assert not result.ok
    assert "No non-empty" in (result.error or "")


def test_warns_above_warn_lines() -> None:
    text = "\n".join(f"item {i}" for i in range(WARN_LINES + 1))
    result = InputValidator().validate(text)
    assert result.ok
    assert len(result.warnings) == 1
    assert "Long list" in result.warnings[0]


def test_keeps_tabs_and_newlines_during_strip() -> None:
    # Tabs inside a line are kept by CONTROL_CHARS; strip() still trims edges.
    text = "leche\tentera\npan"
    result = InputValidator().validate(text)
    assert result.ok
    assert result.lines == ["leche\tentera", "pan"]


def test_postal_code_valid() -> None:
    assert is_valid_postal_code("28001")
    assert is_valid_postal_code("00000")


def test_postal_code_invalid() -> None:
    assert not is_valid_postal_code("")
    assert not is_valid_postal_code("2800")
    assert not is_valid_postal_code("280001")
    assert not is_valid_postal_code("28O01")
    assert not is_valid_postal_code("'; DROP TABLE--")
    assert not is_valid_postal_code("28001\n")
