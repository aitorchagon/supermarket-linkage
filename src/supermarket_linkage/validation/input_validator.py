"""Shopping-list paste limits and sanitization (Decision 14)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from supermarket_linkage.consts import (
    MAX_DUPLICATE_RATIO,
    MAX_LINE_LENGTH,
    MAX_LINES,
    MAX_TOTAL_BYTES,
    MIN_LINE_LENGTH,
    WARN_LINES,
)
from supermarket_linkage.regex_consts import CONTROL_CHARS


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a paste.

    ``ok`` True → ``lines`` ready for the pipeline; ``error`` is None.
    ``ok`` False → ``error`` set; ``lines`` empty.
    ``warnings`` may be non-empty even when ``ok`` (e.g. soft line warn).
    """

    ok: bool
    lines: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None


class InputValidator:
    """Validate and sanitize raw shopping-list text."""

    def validate(self, text: str) -> ValidationResult:
        """Sanitize paste and enforce size / spam caps.

        Pre: ``text`` is the raw textarea (any length, any control chars).
        Post: On success, non-empty ``lines`` with controls stripped, empties
        dropped, each line length in ``[MIN_LINE_LENGTH, MAX_LINE_LENGTH]``,
        count ≤ ``MAX_LINES``, UTF-8 size ≤ ``MAX_TOTAL_BYTES``, and (when
        more than one line) duplicate ratio ≤ ``MAX_DUPLICATE_RATIO``. Soft
        ``WARN_LINES`` goes to warnings.
        On failure, ``ok`` is False and ``error`` explains why.
        """
        if not isinstance(text, str):
            return ValidationResult(ok=False, error="Input must be a string.")

        raw_bytes = len(text.encode("utf-8"))
        if raw_bytes > MAX_TOTAL_BYTES:
            return ValidationResult(
                ok=False,
                error=f"Paste exceeds {MAX_TOTAL_BYTES} bytes ({raw_bytes}).",
            )

        cleaned = CONTROL_CHARS.sub("", text)
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        lines: list[str] = []
        for raw_line in cleaned.split("\n"):
            line = raw_line.strip()
            if len(line) < MIN_LINE_LENGTH:
                continue
            if len(line) > MAX_LINE_LENGTH:
                return ValidationResult(
                    ok=False,
                    error=(
                        f"Line exceeds {MAX_LINE_LENGTH} characters "
                        f"({len(line)})."
                    ),
                )
            lines.append(line)

        if not lines:
            return ValidationResult(ok=False, error="No non-empty lines.")

        if len(lines) > MAX_LINES:
            return ValidationResult(
                ok=False,
                error=f"Too many lines ({len(lines)}); max is {MAX_LINES}.",
            )

        if len(lines) > 1 and _duplicate_ratio(lines) > MAX_DUPLICATE_RATIO:
            return ValidationResult(
                ok=False,
                error="Duplicate-line spam detected.",
            )

        warnings: list[str] = []
        if len(lines) > WARN_LINES:
            warnings.append(
                f"Long list ({len(lines)} lines); processing may take minutes."
            )

        return ValidationResult(ok=True, lines=lines, warnings=warnings)


def _duplicate_ratio(lines: list[str]) -> float:
    """Fraction of lines matching the most common line.

    Pre: ``lines`` non-empty.
    Post: Value in (0, 1]; 1.0 means every line is identical.
    """
    counts = Counter(lines)
    return counts.most_common(1)[0][1] / len(lines)
