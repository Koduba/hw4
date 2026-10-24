"""Problem 7: the chat → page showcase API contract.

A scripted model (no API calls) searches for hoodies and returns a ShowcasePlan.
We check that POST /api/chat returns a Showcase whose cards come from the
database, that invented ids are dropped, and that it survives in chat history.

    cd hw4/backend && .venv/bin/pytest -q tests/test_showcase.py
"""

import os
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REAL_DB = BACKEND.parent / "data" / "campus_customs.db"
ORIGIN = {"Origin": "http://localhost:5173"}


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    db_copy = tmp_path / "test.db"
    shutil.copy(REAL_DB, db_copy)
    monkeypatch.setenv("CAMPUS_DB_PATH", str(db_copy))
    monkeypatch.setenv("PORTKEY_API_KEY", "test-key-not-used")
    sys.path.insert(0, str(BACKEND))
    # Re-import every backend module so all of them see this test's CAMPUS_DB_PATH copy.
    for name, mod in list(sys.modules.items()):
        if getattr(mod, "__file__", None) and Path(mod.__file__).parent == BACKEND:  # main, agent, tools, memory, …
            sys.modules.pop(name, None)
    import agent
    import main
    from fastapi.testclient import TestClient

    agent.build_agent.cache_clear()
    with TestClient(main.app, headers=ORIGIN) as c:
        r = c.post("/api/auth/login", json={"email": "test@campuscustoms.yale.edu", "password": "password"})
        assert r.status_code == 200
        c.db_path = db_copy
        yield c, agent
    agent.build_agent.cache_clear()


def tool_returned(messages) -> bool:
    """True once a tool result has come back this turn (history from earlier turns doesn't count)."""
    from pydantic_ai.messages import ToolReturnPart

    return any(isinstance(p, ToolReturnPart) for p in messages[-1].parts)


def scripted_browse(messages, info):
    """search_products(Hoodies) → final answer with a showcase (plus one invented id)."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    final = info.output_tools[0].name
    if not tool_returned(messages):
        return ModelResponse(parts=[ToolCallPart("search_products", {"category": "Hoodies", "limit": 24})])
    return ModelResponse(parts=[ToolCallPart(final, {
        "reply": "I've put our hoodies on the page for you.",
        "product_ids": [],
        "showcase": {
            "title": "Hoodies",
            "items": [
                {"product_id": "basic-hoodie-big-yale", "note": "Classic Big Yale graphic"},
                {"product_id": "district-vit-hoodie-vintage-bulldog", "note": "Vintage bulldog graphic"},
                {"product_id": "made-up-hoodie", "note": "Does not exist"},
                {"product_id": "basic-hoodie-big-yale", "note": "duplicate"},
            ],
        },
    })])


def test_browse_question_returns_showcase_from_database(app_client):
    from pydantic_ai.models.function import FunctionModel

    client, agent = app_client
    with agent.build_agent().override(model=FunctionModel(scripted_browse)):
        r = client.post("/api/chat", json={"message": "what hoodies do you have?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"] == "I've put our hoodies on the page for you."
    sc = body["showcase"]

    # Contract shape
    assert set(sc) == {"id", "title", "query", "category", "total_matches", "products"}
    assert sc["title"] == "Hoodies" and sc["category"] == "Hoodies"
    assert sc["total_matches"] == 27  # every hoodie in the catalogue, from the search
    # Invented and duplicate ids dropped; order and notes kept
    assert [p["product_id"] for p in sc["products"]] == ["basic-hoodie-big-yale", "district-vit-hoodie-vintage-bulldog"]
    assert sc["products"][0]["note"] == "Classic Big Yale graphic"

    # Card fields come from the database, not the model
    card = sc["products"][0]
    with sqlite3.connect(client.db_path) as conn:
        name, price, desc = conn.execute(
            "SELECT name, price, description FROM catalogue WHERE product_id = 'basic-hoodie-big-yale'"
        ).fetchone()
    assert card["name"] == name and card["price"] == price
    assert desc.startswith(card["short_info"].rstrip("…"))
    assert card["image_url"] == "/media/products/basic-hoodie-big-yale.jpg"
    assert card["page_url"] == "/products/basic-hoodie-big-yale"
    assert card["stock_label"] == "Low stock" and card["in_stock"] is True
    assert {"product_id", "name", "price", "image_url", "short_info", "stock_label", "sizes_in_stock"} <= set(card)

    # Saved with the chat and restored by /api/chat/history
    history = client.get("/api/chat/history").json()
    restored = history[-1]["showcase"]
    assert restored["id"] == sc["id"] and restored["title"] == "Hoodies"
    assert [p["product_id"] for p in restored["products"]] == [p["product_id"] for p in sc["products"]]
    assert restored["products"][1]["note"] == "Vintage bulldog graphic"


def test_single_product_question_has_no_showcase(app_client):
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    def scripted(messages, info):
        final = info.output_tools[0].name
        if not tool_returned(messages):
            return ModelResponse(parts=[ToolCallPart("get_product_info", {"product": "basic-hoodie-big-yale"})])
        return ModelResponse(parts=[ToolCallPart(final, {
            "reply": "The Basic Hoodie Big Yale is $68.", "product_ids": ["basic-hoodie-big-yale"], "showcase": None,
        })])

    client, agent = app_client
    with agent.build_agent().override(model=FunctionModel(scripted)):
        body = client.post("/api/chat", json={"message": "how much is the basic hoodie?"}).json()
    assert body["showcase"] is None
    assert [p["product_id"] for p in body["products"]] == ["basic-hoodie-big-yale"]


def test_showcase_notes_are_fact_checked(app_client):
    """A note with an invented price is rejected, and the model must rewrite it."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import FunctionModel

    turns = []

    def scripted(messages, info):
        turns.append(messages[-1])
        final = info.output_tools[0].name
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("search_products", {"category": "Hoodies"})])
        note = "Only $40 this week" if len(turns) == 2 else "Classic Big Yale graphic"
        return ModelResponse(parts=[ToolCallPart(final, {
            "reply": "Here are some hoodies.", "product_ids": [],
            "showcase": {"title": "Hoodies", "items": [{"product_id": "basic-hoodie-big-yale", "note": note}]},
        })])

    client, agent = app_client
    with agent.build_agent().override(model=FunctionModel(scripted)):
        body = client.post("/api/chat", json={"message": "hoodies?"}).json()
    assert len(turns) == 3  # search, rejected note, fixed note
    assert body["showcase"]["products"][0]["note"] == "Classic Big Yale graphic"
