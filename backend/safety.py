"""Code-level safety guards around the agent (the prompt rules are in prompts/prompt.md).

Input:  redact_input()  removes card numbers, passwords and SSNs from the shopper's
        message BEFORE it reaches the model, the chat history table or the audit trail.
Output: reply_problem()  rejects replies with links or with someone else's email address;
        the output validator turns that into a ModelRetry so the model rewrites it.
"""

from __future__ import annotations

import re

CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
PASSWORD_RE = re.compile(r"(?i)\b(password|passcode|pwd|pw)\b(\s*(is|=|:)\s*|\s+)(\S+)")
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)\S+")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def _luhn_ok(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
        alt = not alt
    return total % 10 == 0


def redact_input(text: str) -> tuple[str, list[str]]:
    """Return (cleaned text, list of what was removed)."""
    removed: list[str] = []

    def card(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            removed.append("card number")
            return "[card number removed]"
        return m.group(0)

    text = CARD_RE.sub(card, text)
    if SSN_RE.search(text):
        removed.append("social security number")
        text = SSN_RE.sub("[SSN removed]", text)
    if PASSWORD_RE.search(text):
        removed.append("password")
        text = PASSWORD_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}[password removed]", text)
    return text, removed


def reply_problem(reply: str, customer_email: str | None) -> str | None:
    """Why a reply is unsafe to show, or None if it's fine."""
    if URL_RE.search(reply):
        return "Don't include links or web addresses. The website already shows product cards; describe items by name instead."
    found = [e.rstrip(".") for e in EMAIL_RE.findall(reply)]  # "…@yale.edu." at the end of a sentence
    others = [e for e in found if not customer_email or e.lower() != customer_email.lower()]
    if others:
        return "Don't include email addresses other than the shopper's own. Never share anyone else's contact details."
    return None
