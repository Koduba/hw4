"""Live checks against the real model (costs a few API calls, so opt-in):

    cd hw4/backend && RUN_LIVE_AGENT=1 .venv/bin/pytest -q tests/test_live_agent.py -s

Each question's expected facts are read from campus_customs.db, not hard-coded.
"""

import asyncio
import os
import re
import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
DB = BACKEND.parent / "data" / "campus_customs.db"

pytestmark = pytest.mark.skipif(not os.getenv("RUN_LIVE_AGENT"), reason="set RUN_LIVE_AGENT=1 to call the real model")


def qty(product_id, size):
    with sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True) as c:
        return c.execute("SELECT quantity FROM inventory WHERE product_id=? AND size=?", (product_id, size)).fetchone()[0]


def price(product_id):
    with sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True) as c:
        return c.execute("SELECT price FROM catalogue WHERE product_id=?", (product_id,)).fetchone()[0]


def ask(question, current_product_id=None):
    import agent
    from models import CustomerContext, ShopDeps

    deps = ShopDeps(customer=CustomerContext(is_guest=False, first_name="Test"), current_product_id=current_product_id, user_message=question)
    agent.build_agent.cache_clear()  # each asyncio.run() is a new event loop; don't reuse its HTTP client
    result = asyncio.run(agent.build_agent().run(question, deps=deps, usage_limits=agent.LIMITS))
    print(f"\nQ: {question}\nA: {result.output.reply}\ncards: {result.output.product_ids}")
    return result.output.reply


def test_price_and_size_count():
    reply = ask("How much is the Basic Hoodie Big Yale, and how many do you have in medium?")
    assert f"${price('basic-hoodie-big-yale'):g}" in reply
    assert re.search(rf"\b{qty('basic-hoodie-big-yale', 'M')}\b", reply)


def test_sold_out_size_said_clearly():
    assert qty("football-left-chest-t-shirt", "M") == 0
    reply = ask("Can I get the Football Left Chest T Shirt in a medium?").lower()
    assert "sold out" in reply or "out of stock" in reply


def test_this_one_uses_viewed_product():
    reply = ask("How many XL of this one are left?", current_product_id="basic-hoodie-big-yale")
    assert re.search(rf"\b{qty('basic-hoodie-big-yale', 'XL')}\b", reply)


def test_description_comes_from_database():
    reply = ask("What does the Saybrook College Crewneck look like and what does it cost?").lower()
    assert f"${price('saybrook-college-crewneck'):g}" in reply
    assert "navy" in reply  # from its catalogue description/colours


def test_browse_question_fills_showcase():
    import agent
    from models import CustomerContext, ShopDeps

    question = "what hoodies do you have?"
    deps = ShopDeps(customer=CustomerContext(is_guest=False, first_name="Test"), user_message=question)
    agent.build_agent.cache_clear()
    out = asyncio.run(agent.build_agent().run(question, deps=deps, usage_limits=agent.LIMITS)).output
    assert out.showcase is not None
    showcase = agent.build_showcase(out.showcase, deps)
    print(f"\nQ: {question}\nA: {out.reply}\nshowcase: {showcase.title} ({len(showcase.products)} of {showcase.total_matches})")
    assert len(showcase.products) >= 8
    assert all(p.category == "Hoodies" for p in showcase.products)


# ---------- Problem 8: customer + page context (read-only: uses make_deps, doesn't save) ----------

def ask_as(question, customer, page=None):
    import agent
    from models import PageContext

    agent.build_agent.cache_clear()
    deps = agent.make_deps(customer, question, PageContext(**page) if page else None)
    out = asyncio.run(agent.build_agent().run(question, deps=deps, usage_limits=agent.LIMITS)).output
    print(f"\nQ: {question}\nA: {out.reply}")
    return out.reply


def _test_customer(user_id=1):
    from models import CustomerContext

    return CustomerContext(is_guest=False, first_name="Test", last_name="User",
                           email="test@campuscustoms.yale.edu", member_since="2026-09-19", user_id=user_id)


def test_this_in_pink_on_product_page():
    reply = ask_as("do you have this in pink?", _test_customer(),
                   {"path": "/products/basic-hoodie-big-yale", "product_id": "basic-hoodie-big-yale"}).lower()
    assert "navy" in reply and "white" in reply  # its real colours, from page context


def test_agent_knows_logged_in_email():
    assert "test@campuscustoms.yale.edu" in ask_as("what email is my account under?", _test_customer())


def test_guest_is_not_identified():
    from models import CustomerContext

    reply = ask_as("do you know my name and email?", CustomerContext.guest()).lower()
    assert "test@" not in reply and ("log in" in reply or "guest" in reply or "account" in reply)
