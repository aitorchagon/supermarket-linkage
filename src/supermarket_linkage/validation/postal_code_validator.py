"""Spanish postal-code checks."""

from supermarket_linkage.regex_consts import POSTAL_CODE


def is_valid_postal_code(code: str) -> bool:
    """Return True iff ``code`` matches ``^\\d{5}$``.

    Pre: ``code`` is a stripped user string (may be empty or garbage).
    Post: True only for exactly five ASCII digits; no side effects.
    """
    return bool(POSTAL_CODE.fullmatch(code))
