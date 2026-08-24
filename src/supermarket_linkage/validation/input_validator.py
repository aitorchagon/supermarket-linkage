from __future__ import annotations

from typing import List, Optional
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
from supermarket_linkage.regex_consts import CONTROL_CHARS, POSTAL_CODE, QUANTITY


def is_valid_postal_code(code: str) -> bool:
    """
    This function returns True if and only if postal code is valid (it has 5 numbers).
    """
    return bool(POSTAL_CODE.fullmatch(code))

@dataclass(frozen=True)
class ValidationResult:
    """
    This is the outcome of validating a paste. if lines are ready for the pipeline,
    we return ok, error if not ok. 
    """

    ok: bool
    lines: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    error: Optional[str] = None


class InputValidator:
    """
    This class allows to validate and sanitize raw shopping-list text.
    """

    def validate(self, text: str) -> ValidationResult:
        """
        This function allows to sanitize past text and enforce size or spam caps.
        As an input, we have the raw text area; as an output, we have non-empty lines with
        controls stripped, empties dropped, capped at MAX_LINES and MAX_TOTAL_BYTES, avoid duplicates. 
        """
        if not isinstance(text, str):
            return ValidationResult(ok=False, error="Input must be a string.")

        raw_bytes = len(text.encode("utf-8"))
        if raw_bytes > MAX_TOTAL_BYTES:
            return ValidationResult(
                ok=False,
                error=f"Pasted text exceeds {MAX_TOTAL_BYTES} bytes ({raw_bytes}).",
            )

        cleaned = CONTROL_CHARS.sub("", text)
        cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")

        lines: List[str] = []
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
            return ValidationResult(ok=False, error="The pasted text is empty, please provide some text.")

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

        warnings: List[str] = []
        if len(lines) > WARN_LINES:
            warnings.append(
                f"Long list ({len(lines)} lines); processing may take minutes."
            )
        multi_qty = [line for line in lines if len(QUANTITY.findall(line)) >= 2]
        if multi_qty:
            warnings.append(
                "Parece que hay más de un producto en la misma línea. "
                "Pon un producto por línea (Enter entre ellos)."
            )

        return ValidationResult(ok=True, lines=lines, warnings=warnings)


def _duplicate_ratio(lines: List[str]) -> float:
    """
    This function calculates the fraction of lines that matches
    the most common line, to determine whether we have duplicates.
    We cannot do unique directly as it is free text and duplicates can come in
    different sizes.
    """
    counts = Counter(lines)
    return counts.most_common(1)[0][1] / len(lines)
