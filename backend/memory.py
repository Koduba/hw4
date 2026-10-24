"""Customer memory: who is chatting, and what they've said before.

Logged-in shoppers
    Every turn is stored in the `chat_messages` table (one row per message, scoped
    by user_id from the session cookie) and reloaded when they come back.

Guests
    Can chat, but nothing is written to the database. A short rolling history is
    kept in server memory, keyed by a random HttpOnly `cc_guest` cookie, so the
    conversation still flows within a visit. It expires after GUEST_TTL and is lost
    on server restart, which is fine: persistence is only promised to logged-in users.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import OrderedDict

import db
import tools
from models import ChatMessage, CustomerContext, ProductCard, Showcase

GUEST_TTL_SECONDS = 2 * 60 * 60
GUEST_MAX_MESSAGES = 20
GUEST_MAX_SESSIONS = 500


# ---------- who is chatting ----------

def customer_from_user(row) -> CustomerContext:
    """Session row (auth.current_user) → the customer fields the agent may see."""
    name_parts = (row["name"] or "").split(" ")
    return CustomerContext(
        is_guest=False,
        first_name=row["first_name"] or name_parts[0] or None,
        last_name=row["last_name"] or " ".join(name_parts[1:]) or None,
        email=row["email"],
        member_since=(row["created_at"] or "")[:10] or None,
        user_id=row["id"],
    )


# ---------- saved product cards / showcases ----------

def cards(product_ids: list[str]) -> list[ProductCard]:
    """Cards built from the database (live price and stock), in the given order."""
    return [ProductCard.from_product(p) for p in tools.load_products(product_ids)]


def _from_saved_json(raw: str | None) -> tuple[list[ProductCard], Showcase | None]:
    """Re-load what a past reply showed, with current price/stock.

    Stored shapes: a list of product snapshots (older rows), or
    {"cards": [...], "showcase": {title, query, category, total_matches, id, items: [{product_id, note}]}}.
    Only ids/notes are trusted; everything else is re-read from the database."""
    try:
        data = json.loads(raw or "[]")
    except (ValueError, TypeError):
        return [], None
    snapshots = data.get("cards", []) if isinstance(data, dict) else data
    ids = [p["product_id"] for p in snapshots if isinstance(p, dict) and "product_id" in p]
    restored = cards(list(dict.fromkeys(ids)))

    showcase = None
    saved = data.get("showcase") if isinstance(data, dict) else None
    if isinstance(saved, dict) and saved.get("items"):
        notes = {i["product_id"]: i.get("note") for i in saved["items"] if "product_id" in i}
        products = tools.load_products(list(notes))
        showcase = Showcase(
            id=saved.get("id") or uuid.uuid4().hex,
            title=saved.get("title", "Picked for you"),
            query=saved.get("query", ""),
            category=saved.get("category"),
            total_matches=saved.get("total_matches", len(products)),
            products=[ProductCard.from_product(p, note=notes.get(p.product_id)) for p in products],
        )
    return restored, showcase


def _to_saved_json(products: list[ProductCard], showcase: Showcase | None) -> str:
    saved: dict = {"cards": [p.model_dump() for p in products]}
    if showcase:
        saved["showcase"] = {
            **showcase.model_dump(exclude={"products"}),
            "items": [{"product_id": p.product_id, "note": p.note} for p in showcase.products],
        }
    return json.dumps(saved)


def _viewing(raw: str | None) -> str | None:
    try:
        ctx = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return None
    return ctx.get("product_id") if isinstance(ctx, dict) else None


# ---------- logged-in users: chat_messages table ----------

def load_history(user_id: int, limit: int = 50) -> list[ChatMessage]:
    """The user's own recent messages, oldest first. Always scoped by user_id from the session."""
    with db.read_only() as conn:
        rows = conn.execute(
            "SELECT role, content, products_json, context_json, created_at FROM chat_messages "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    history = []
    for r in reversed(rows):
        if r["role"] not in ("user", "assistant"):
            continue
        restored, showcase = _from_saved_json(r["products_json"])
        history.append(
            ChatMessage(
                role=r["role"],
                content=r["content"],
                products=restored,
                showcase=showcase,
                viewing_product_id=_viewing(r["context_json"]),
                created_at=r["created_at"],
            )
        )
    return history


def count_messages(user_id: int) -> int:
    with db.read_only() as conn:
        return conn.execute("SELECT count(*) FROM chat_messages WHERE user_id = ?", (user_id,)).fetchone()[0]


def save_turn(
    user_id: int,
    message: str,
    reply: str,
    products: list[ProductCard],
    showcase: Showcase | None = None,
    viewing_product_id: str | None = None,
    page_path: str | None = None,
) -> None:
    context = json.dumps({"product_id": viewing_product_id, "path": page_path}) if (viewing_product_id or page_path) else None
    with db.read_write() as conn:
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json, context_json) VALUES (?, 'user', ?, NULL, ?)",
            (user_id, message, context),
        )
        conn.execute(
            "INSERT INTO chat_messages (user_id, role, content, products_json) VALUES (?, 'assistant', ?, ?)",
            (user_id, reply, _to_saved_json(products, showcase)),
        )


def clear_history(user_id: int) -> None:
    with db.read_write() as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id = ?", (user_id,))


# ---------- guests: in-memory only ----------

class GuestMemory:
    """Short-lived, per-guest chat history held in server memory (never in the DB)."""

    def __init__(self, ttl: int = GUEST_TTL_SECONDS, max_messages: int = GUEST_MAX_MESSAGES, max_sessions: int = GUEST_MAX_SESSIONS):
        self.ttl, self.max_messages, self.max_sessions = ttl, max_messages, max_sessions
        self._store: OrderedDict[str, tuple[float, list[ChatMessage]]] = OrderedDict()
        self._lock = threading.Lock()

    def _expire(self) -> None:
        cutoff = time.monotonic() - self.ttl
        for gid in [g for g, (t, _) in self._store.items() if t < cutoff]:
            del self._store[gid]

    def get(self, guest_id: str | None) -> list[ChatMessage]:
        if not guest_id:
            return []
        with self._lock:
            self._expire()
            entry = self._store.get(guest_id)
            return list(entry[1]) if entry else []

    def append(self, guest_id: str, *messages: ChatMessage) -> None:
        with self._lock:
            self._expire()
            _, history = self._store.pop(guest_id, (0.0, []))
            history = (history + list(messages))[-self.max_messages:]
            self._store[guest_id] = (time.monotonic(), history)  # most recently used goes last
            while len(self._store) > self.max_sessions:
                self._store.popitem(last=False)  # drop the least recently used guest

    def clear(self, guest_id: str | None) -> None:
        with self._lock:
            self._store.pop(guest_id or "", None)


guest_memory = GuestMemory()
