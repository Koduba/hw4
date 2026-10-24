"""Append-only audit trail of agent loop activity: output/audit_trail.json.

Every chat turn adds entries (run_start → model_response / tool_call / tool_result /
retry … → run_end) with time, tool name, short args/result and the stop reason.

Append-only, never wiped:
- The file is a JSON array so it opens in any viewer, but it is never re-read
  and rewritten. New entries are spliced in before the closing "]" (the bytes of
  earlier entries are never touched), under an exclusive file lock so concurrent
  requests can't interleave.
- Nothing in the app deletes or truncates it ("New chat" only clears chat history).

Privacy: who is "guest"/"user:<id>", text is truncated, and emails / card-like
numbers are masked before anything is written.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from models import AuditEntry

AUDIT_PATH = Path(os.getenv("AUDIT_PATH", Path(__file__).resolve().parent.parent / "output" / "audit_trail.json"))
SHORT = 240  # max characters for any text field in the trail
_lock = threading.Lock()

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def mask(text: str | None, limit: int = SHORT) -> str | None:
    """Truncate and hide emails / card-like numbers."""
    if text is None:
        return None
    text = CARD_RE.sub("[number removed]", EMAIL_RE.sub("[email]", str(text)))
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize(content) -> str:
    """Short, readable tool result: the tool's own one-line summary if it has one,
    otherwise compact JSON (counts first for search-style results)."""
    if isinstance(content, str):
        return content
    if getattr(content, "summary", None):
        return content.summary
    if hasattr(content, "products") and hasattr(content, "total_matches"):  # SearchResults
        ids = ", ".join(p.product_id for p in content.products[:5])
        return f"{content.total_matches} matches; top: {ids}" + (f" | note: {content.note}" if content.note else "")
    if hasattr(content, "model_dump_json"):
        return content.model_dump_json(exclude_none=True)
    return repr(content)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def append(entries: list[AuditEntry]) -> None:
    """Append entries to the JSON array without rewriting what's already there."""
    if not entries:
        return
    rows = ",\n".join("  " + json.dumps(e.model_dump(exclude_none=True), ensure_ascii=False) for e in entries)
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(AUDIT_PATH, "a+b") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size == 0:
                f.write(("[\n" + rows + "\n]\n").encode())
                return
            # Find the final "]" and splice the new rows in before it.
            back = min(size, 64)
            f.seek(size - back)
            tail = f.read(back)
            close = tail.rfind(b"]")
            if close == -1:  # not our format; never destroy it, start a fresh valid array after it
                f.write(("\n[\n" + rows + "\n]\n").encode())
                return
            cut = size - back + close
            f.seek(0)
            empty = f.read(cut).strip() == b"["
            f.truncate(cut)  # only removes the closing bracket (and trailing newline)
            f.seek(cut)
            f.write(((rows if empty else ",\n" + rows) + "\n]\n").encode())
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class RunAudit:
    """Collects one chat turn's entries; written in a single append at the end."""

    def __init__(self, who: str):
        self.run_id = f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:6]}"
        self.who = who
        self.entries: list[AuditEntry] = []

    def add(self, event: str, timestamp: str | None = None, **fields) -> None:
        for key in ("message", "tool_args", "result_summary", "detail"):
            if key in fields:
                fields[key] = mask(fields[key])
        self.entries.append(
            AuditEntry(timestamp=timestamp or now(), run_id=self.run_id, step=len(self.entries) + 1,
                       event=event, who=self.who, **fields)
        )

    def from_messages(self, messages) -> None:
        """Turn PydanticAI messages from this run into tool/model/retry entries."""
        for m in messages:
            kind = getattr(m, "kind", "")
            ts = getattr(m, "timestamp", None)
            ts = ts.isoformat(timespec="milliseconds").replace("+00:00", "Z") if ts else None
            if kind == "response":
                usage = getattr(m, "usage", None)
                calls = [p for p in m.parts if getattr(p, "part_kind", "") == "tool-call"]
                self.add("model_response", ts,
                         finish_reason=str(getattr(m, "finish_reason", None) or ("tool_call" if calls else "stop")),
                         tokens_in=getattr(usage, "input_tokens", None), tokens_out=getattr(usage, "output_tokens", None),
                         detail=f"{len(calls)} tool call(s)" if calls else None)
                for p in calls:
                    final = p.tool_name.startswith("final_result")
                    args = p.args if isinstance(p.args, str) else json.dumps(p.args, ensure_ascii=False)
                    self.add("tool_call", ts, tool_name="final_answer" if final else p.tool_name, tool_args=args)
            elif kind == "request":
                for p in m.parts:
                    pk = getattr(p, "part_kind", "")
                    pts = getattr(p, "timestamp", None)
                    pts = pts.isoformat(timespec="milliseconds").replace("+00:00", "Z") if pts else ts
                    if pk == "tool-return":
                        name = "final_answer" if p.tool_name.startswith("final_result") else p.tool_name
                        content = summarize(p.content)
                        retry = name == "final_answer" and "Final result processed" not in content
                        self.add("retry" if retry else "tool_result", pts, tool_name=name, result_summary=content)
                    elif pk == "retry-prompt":
                        self.add("retry", pts, tool_name=getattr(p, "tool_name", None), detail=str(p.content))

    def write(self) -> None:
        try:
            append(self.entries)
        except Exception:  # auditing must never break a shopper's chat
            import logging
            logging.getLogger("uvicorn.error").exception("audit trail write failed")
