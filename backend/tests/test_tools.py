"""Problem 6: product-info and stock tools must report exactly what's in campus_customs.db,
and the agent must not be able to send prices/quantities the tools didn't return.

    cd hw4/backend && .venv/bin/pytest -q tests/test_tools.py
"""

import sqlite3
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

import tools  # noqa: E402
from models import CustomerContext, ProductInfo, ProductNotFound, ShopDeps, StockReport  # noqa: E402

DB = BACKEND.parent / "data" / "campus_customs.db"


def db_rows(sql, *args):
    with sqlite3.connect(f"{DB.as_uri()}?mode=ro", uri=True) as conn:
        return conn.execute(sql, args).fetchall()


@pytest.fixture()
def deps():
    return ShopDeps(customer=CustomerContext(is_guest=False, first_name="Test"))


# ---------- tools return database values ----------

def test_product_info_matches_database_for_every_product(deps):
    for product_id, description, price in db_rows("SELECT product_id, description, price FROM catalogue"):
        info = tools.get_product_info(deps, product_id)
        assert isinstance(info, ProductInfo)
        assert info.description == description and info.price == price


def test_stock_matches_database_for_every_size(deps):
    for product_id, size, qty in db_rows("SELECT product_id, size, quantity FROM inventory"):
        report = tools.check_stock(deps, product_id, size)
        assert isinstance(report, StockReport)
        assert report.requested_size_quantity == qty
        assert report.requested_size_status == ("sold out" if qty == 0 else "low stock" if qty <= 5 else "in stock")


def test_sold_out_size_is_stated_clearly(deps):
    # Football Left Chest T Shirt: M = 0 in the seed data.
    report = tools.check_stock(deps, "football-left-chest-t-shirt", "m")
    assert report.requested_size == "M" and report.requested_size_quantity == 0
    assert "SOLD OUT" in report.summary
    assert "M" in report.sold_out_sizes and "M" not in report.sizes_in_stock
    assert deps.sold_out_requests == [("Football Left Chest T Shirt", "M")]
    # DB: XS 0, S 2, M 0, L 2, XL 0, XXL 5
    assert report.in_stock is True and report.total_units == 9
    assert report.sold_out_sizes == ["XS", "M", "XL"]
    assert report.low_stock_sizes == ["S", "L", "XXL"]
    assert [s.size for s in report.sizes] == ["XS", "S", "M", "L", "XL", "XXL"]


def test_in_stock_size(deps):
    report = tools.check_stock(deps, "basic-hoodie-big-yale", "XL")
    assert report.requested_size_quantity == 2 and report.requested_size_status == "low stock"
    assert report.total_units == sum(q for (q,) in db_rows(
        "SELECT quantity FROM inventory WHERE product_id = 'basic-hoodie-big-yale'"))


def test_lookup_by_name_and_unknown(deps):
    assert tools.get_product_info(deps, "Basic Hoodie Big Yale").product_id == "basic-hoodie-big-yale"
    missing = tools.check_stock(deps, "gym shorts")
    assert isinstance(missing, ProductNotFound)


def test_unknown_size(deps):
    report = tools.check_stock(deps, "basic-hoodie-big-yale", "XXXL")
    assert report.requested_size is None and "doesn't come in size" in report.summary


# ---------- fact check on replies ----------

def test_fact_check_accepts_database_numbers(deps):
    tools.check_stock(deps, "basic-hoodie-big-yale", "M")
    assert tools.check_reply_facts("The Basic Hoodie is $68 and we have 5 left in M.", deps) is None


def test_fact_check_rejects_invented_price_and_quantity(deps):
    tools.check_stock(deps, "basic-hoodie-big-yale", "M")
    problem = tools.check_reply_facts("It's $65 and we have 12 left in M.", deps)
    assert "$65" in problem and "12" in problem


def test_fact_check_requires_sold_out_wording(deps):
    tools.check_stock(deps, "football-left-chest-t-shirt", "M")
    assert "sold out" in tools.check_reply_facts("Size M is a great choice!", deps)
    assert tools.check_reply_facts("Sorry, size M is sold out. We have 2 left in S.", deps) is None


def test_fact_check_allows_numbers_the_shopper_typed(deps):
    tools.search_products(deps, "hoodie", max_price=70)
    assert tools.check_reply_facts("Here are hoodies under $70.", deps, user_message="hoodies under $70?") is None


# ---------- the agent cannot ship an invented price ----------

def test_agent_retries_until_reply_uses_database_price(monkeypatch):
    """A scripted model first answers $59 without looking anything up. The output
    validator rejects it, the model calls check_stock, then answers with the DB price."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart
    from pydantic_ai.models.function import AgentInfo, FunctionModel

    import agent

    seen_by_model = []

    def scripted(messages, info: AgentInfo) -> ModelResponse:
        seen_by_model.append(" ".join(str(getattr(p, "content", "")) for p in messages[-1].parts))
        final = info.output_tools[0].name
        if len(seen_by_model) == 1:  # answers from "memory", no tool call
            return ModelResponse(parts=[ToolCallPart(final, {"reply": "It's $59 with 9 left in M.", "product_ids": []})])
        if len(seen_by_model) == 2:  # after the rejection, looks it up
            return ModelResponse(parts=[ToolCallPart("check_stock", {"product": "basic-hoodie-big-yale", "size": "M"})])
        return ModelResponse(parts=[ToolCallPart(final, {
            "reply": "The Basic Hoodie Big Yale is $68 and we have 5 left in M.",
            "product_ids": ["basic-hoodie-big-yale"],
        })])

    agent.build_agent.cache_clear()
    monkeypatch.setenv("PORTKEY_API_KEY", "test-key-not-used")
    shop_agent = agent.build_agent()
    deps = ShopDeps(customer=CustomerContext(is_guest=False, first_name="Test"), user_message="price and mediums for the basic hoodie?")
    with shop_agent.override(model=FunctionModel(scripted)):
        result = shop_agent.run_sync(deps.user_message, deps=deps)
    agent.build_agent.cache_clear()

    assert result.output.reply == "The Basic Hoodie Big Yale is $68 and we have 5 left in M."
    assert result.output.product_ids == ["basic-hoodie-big-yale"]
    assert len(seen_by_model) == 3  # bad answer -> rejected -> check_stock -> good answer
    assert "$59" in seen_by_model[1] and "no tool returned" in seen_by_model[1]  # the correction it was sent
    assert "price=68.0" in seen_by_model[2]  # the database row it then saw


def test_not_found_echoes_query_and_suggests(deps):
    missing = tools.get_product_info(deps, "saybrook crewneck")
    assert isinstance(missing, ProductNotFound) and missing.query == "saybrook crewneck"
    assert missing.did_you_mean[0].product_id == "saybrook-college-crewneck"


# ---------- Problem 9: find_similar_products ----------

def test_similar_in_a_colour_we_only_have_close_to(deps):
    r = tools.find_similar_products(deps, "basic-hoodie-big-yale", color="pink")
    assert [p.product_id for p in r.products] == ["big-yale-tri-blend-t-shirt"]  # only "dusty coral" item
    assert "Nothing is listed as exactly 'pink'" in r.note and "dusty coral" in r.note


def test_similar_when_size_is_sold_out(deps):
    # Football Left Chest T Shirt is sold out in M; alternatives must have M in stock.
    r = tools.find_similar_products(deps, "football-left-chest-t-shirt", size="M")
    assert r.products and all("M" in p.sizes_in_stock for p in r.products)
    assert r.products[0].category == "T-Shirts"  # same category ranks first
    assert "football-left-chest-t-shirt" not in [p.product_id for p in r.products]
    assert {p.product_id for p in r.products} <= deps.seen_product_ids  # allowed as cards


def test_similar_respects_budget(deps):
    r = tools.find_similar_products(deps, "benjamin-franklin-fleece-jacket", max_price=60)
    assert r.products and all(p.price <= 60 for p in r.products)
