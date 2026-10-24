"""Tools the shop agent can call, plus the catalogue helpers they share with the API.

Every tool is READ-ONLY and only touches the catalogue and inventory tables.
No tool can see users, password hashes, sessions or other shoppers' chats,
so even a prompt-injected agent has nothing sensitive to leak.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import db
from models import (
    LOW_STOCK,
    MAX_SEARCH_RESULTS,
    AccountInfo,
    PageContext,
    ViewedProduct,
    Product,
    ProductInfo,
    ProductNotFound,
    ProductSummary,
    SearchResults,
    ShopDeps,
    SimilarProducts,
    SizeAvailability,
    SizeStock,
    StockReport,
)

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
load_dotenv(HERE.parent / ".env")  # hw4/.env (see .env.example)
load_dotenv(HERE.parent.parent / ".env")  # PORTKEY_API_KEY lives in the class-folder root

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

SIZE_ORDER = ["XS", "S", "M", "L", "XL", "XXL"]

# garment_type has ~22 free-text variants; collapse them into shop categories.
# Checked in order, so more specific keywords come first.
CATEGORY_RULES = [
    ("jacket", "Jackets & Fleece"),
    ("quarter-zip", "Quarter-Zips"),
    ("hood", "Hoodies"),
    ("t-shirt", "T-Shirts"),
    ("long-sleeve", "Long Sleeves"),
    ("crewneck", "Crewnecks"),
    ("mockneck", "Crewnecks"),
]

# Shopper words -> words the catalogue actually uses (fixes misses like
# "Handsome Dan" returning nothing even though bulldog items exist).
SYNONYMS = {
    "handsome dan": ["bulldog"],
    "dan": ["bulldog"],
    "mascot": ["bulldog"],
    "dog": ["bulldog"],
    "tee": ["t-shirt"],
    "tshirt": ["t-shirt"],
    "shirt": ["t-shirt", "long sleeve"],
    "sweatshirt": ["crewneck", "hoodie", "sweatshirt"],
    "sweater": ["crewneck", "fleece", "sweater"],
    "hoody": ["hoodie"],
    "hooded": ["hoodie"],
    "zip": ["zip"],
    "pullover": ["quarter-zip", "hoodie", "pullover"],
    "coat": ["jacket"],
    "grey": ["gray"],
    "blue": ["navy", "blue"],
    # colour families, so "pink" can surface the closest real colour (e.g. "dusty coral")
    "pink": ["pink", "coral", "rose"],
    "maroon": ["maroon", "red"],
    "gold": ["gold", "yellow"],
    "mom": ["mom"],
    "mother": ["mom"],
    "father": ["dad"],
    "grandmother": ["grandma"],
    "grandfather": ["grandpa"],
    "som": ["school of management"],
    "law": ["law school"],
    "harvard": ["harvard", "the game"],
}
# Things shoppers ask for that the shop doesn't carry. Dropped from the search
# (so "gym shorts" doesn't match "short-sleeve") and reported back in a note.
NOT_SOLD = {"shorts", "pants", "sweatpants", "joggers", "leggings", "hat", "hats", "cap", "caps", "beanie",
            "socks", "mug", "mugs", "bag", "bags", "scarf", "scarves", "shoes", "sneakers", "jewelry", "pennant"}
STOPWORDS = {"a", "an", "the", "and", "or", "for", "with", "in", "on", "of", "any", "some", "yale", "item", "items", "something", "gear", "anything"}


def get_model() -> OpenAIResponsesModel:
    """One shared model client, routed through Portkey (same setup as HW3)."""
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise RuntimeError("PORTKEY_API_KEY is missing. Add it to backend/.env or the class-folder .env.")
    client = AsyncOpenAI(api_key=api_key, base_url=PORTKEY_BASE_URL)
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))


# ---------- catalogue helpers (shared with main.py) ----------

def categorize(garment_type: str) -> str:
    g = garment_type.lower()
    for keyword, category in CATEGORY_RULES:
        if keyword in g:
            return category
    return "Other"


def load_products(product_ids: list[str] | None = None) -> list[Product]:
    """Products with live stock. None = whole catalogue; a list keeps that order."""
    if product_ids is not None and not product_ids:
        return []
    where, params = "", ()
    if product_ids is not None:
        where = f"WHERE product_id IN ({','.join('?' * len(product_ids))})"
        params = tuple(product_ids)
    with db.read_only() as conn:
        rows = conn.execute(f"SELECT * FROM catalogue {where} ORDER BY name", params).fetchall()
        stock_rows = conn.execute(f"SELECT product_id, size, quantity FROM inventory {where}", params).fetchall()

    stock: dict[str, list[SizeStock]] = {}
    for s in stock_rows:
        stock.setdefault(s["product_id"], []).append(SizeStock(size=s["size"], quantity=s["quantity"]))

    shots = {f.stem for f in db.MODEL_SHOTS_DIR.glob("*.jpg")} if db.MODEL_SHOTS_DIR.exists() else set()
    products = []
    for r in rows:
        inventory = sorted(
            stock.get(r["product_id"], []),
            key=lambda s: SIZE_ORDER.index(s.size) if s.size in SIZE_ORDER else 99,
        )
        products.append(
            Product(
                product_id=r["product_id"],
                name=r["name"],
                garment_type=r["garment_type"],
                category=categorize(r["garment_type"]),
                description=r["description"],
                colors=json.loads(r["colors"]),
                search_tags=json.loads(r["search_tags"]),
                image_url=f"/media/{r['image_file_path']}",
                model_image_url=f"/media/models/{r['product_id']}.jpg" if r["product_id"] in shots else None,
                price=r["price"],
                total_stock=sum(s.quantity for s in inventory),
                inventory=inventory,
            )
        )
    if product_ids is not None:
        order = {pid: i for i, pid in enumerate(product_ids)}
        products.sort(key=lambda p: order[p.product_id])
    return products


def _summary(p: Product) -> ProductSummary:
    return ProductSummary(
        product_id=p.product_id,
        name=p.name,
        category=p.category,
        price=p.price,
        colors=p.colors,
        in_stock=p.total_stock > 0,
        sizes_in_stock=[s.size for s in p.inventory if s.quantity > 0],
    )


def _search_text(p: Product) -> str:
    return " ".join([p.name, p.garment_type, p.category, p.description, *p.colors, *p.search_tags]).lower()


def _terms(query: str) -> list[list[str]]:
    """Split a query into terms; each term is a list of acceptable alternatives."""
    q = query.lower()
    groups: list[list[str]] = []
    for phrase, alts in SYNONYMS.items():
        if " " in phrase and phrase in q:
            groups.append([phrase, *alts])
            q = q.replace(phrase, " ")
    for word in re.findall(r"[a-z0-9&'-]+", q):
        if word in STOPWORDS or word in NOT_SOLD or len(word) < 2:
            continue
        stem = word[:-1] if word.endswith("s") and len(word) > 3 else word
        groups.append([word, stem, *SYNONYMS.get(word, []), *SYNONYMS.get(stem, [])])
    return groups


# ---------- agent tools ----------

def search_products(
    deps: ShopDeps,
    query: str = "",
    category: str | None = None,
    color: str | None = None,
    max_price: float | None = None,
    size: str | None = None,
    limit: int = 8,
) -> SearchResults:
    limit = max(1, min(limit, MAX_SEARCH_RESULTS))
    terms = _terms(query)
    scored: list[tuple[int, Product]] = []
    for p in load_products():
        if category and p.category.lower() != category.lower():
            continue
        if max_price is not None and p.price > max_price:
            continue
        if color and not any(any(c in pc.lower() for c in [color.lower(), *SYNONYMS.get(color.lower(), [])]) for pc in p.colors):
            continue
        if size and not any(s.size == size.upper() and s.quantity > 0 for s in p.inventory):
            continue
        text = _search_text(p)
        hits = sum(any(alt in text for alt in group) for group in terms)
        if terms and hits == 0:
            continue
        name_hits = sum(any(alt in p.name.lower() for alt in group) for group in terms)
        scored.append((hits * 10 + name_hits * 3 + (p.total_stock > 0), p))

    scored.sort(key=lambda t: (-t[0], t[1].price))  # best match first, then cheapest
    top = [p for _, p in scored[:limit]]
    deps.seen_product_ids.update(p.product_id for p in top)
    deps.seen_prices.update(p.price for p in top)

    note = None
    unsold = sorted(set(re.findall(r"[a-z]+", query.lower())) & NOT_SOLD)
    if unsold:
        note = f"We don't sell {', '.join(unsold)}. Results (if any) are the closest tops we carry."
    elif not top:
        note = "No matches. The shop only sells tops and jackets (no shorts, pants, hats or accessories). Try broader words or drop a filter."
    results = SearchResults(query=query, total_matches=len(scored), products=[_summary(p) for p in top], note=note)
    deps.last_search = results
    return results


def _resolve(deps: ShopDeps, product: str) -> Product | ProductNotFound:
    """Accept a product_id or a product name (as shoppers type it)."""
    ref = product.strip()
    if found := load_products([ref]):
        return found[0]
    slug = re.sub(r"[^a-z0-9]+", "-", ref.lower()).strip("-")
    everything = load_products()
    for p in everything:
        if slug in (p.product_id, re.sub(r"[^a-z0-9]+", "-", p.name.lower()).strip("-")):
            return p
    hits = search_products(deps, ref, limit=3).products
    return ProductNotFound(
        query=ref,
        error=f"No product matches '{ref}' exactly. Ask the shopper which one they mean, or pick from did_you_mean.",
        did_you_mean=hits,
    )


def get_product_info(deps: ShopDeps, product: str) -> ProductInfo | ProductNotFound:
    p = _resolve(deps, product)
    if isinstance(p, ProductNotFound):
        return p
    deps.seen_product_ids.add(p.product_id)
    deps.seen_prices.add(p.price)
    return ProductInfo(
        product_id=p.product_id,
        name=p.name,
        category=p.category,
        garment_type=p.garment_type,
        description=p.description,
        price=p.price,
        colors=p.colors,
    )


def _status(qty: int) -> str:
    return "sold out" if qty <= 0 else "low stock" if qty <= LOW_STOCK else "in stock"


def check_stock(deps: ShopDeps, product: str, size: str | None = None) -> StockReport | ProductNotFound:
    p = _resolve(deps, product)
    if isinstance(p, ProductNotFound):
        return p
    sizes = [SizeAvailability(size=s.size, quantity=s.quantity, status=_status(s.quantity)) for s in p.inventory]
    in_stock = [s.size for s in sizes if s.quantity > 0]
    low = [s.size for s in sizes if s.status == "low stock"]
    sold_out = [s.size for s in sizes if s.quantity <= 0]
    available = ", ".join(f"{s.size} ({s.quantity})" for s in sizes if s.quantity > 0) or "none"

    deps.seen_product_ids.add(p.product_id)
    deps.seen_prices.add(p.price)
    deps.seen_quantities.update(s.quantity for s in sizes)
    deps.seen_quantities.add(p.total_stock)

    report = StockReport(
        product_id=p.product_id,
        name=p.name,
        price=p.price,
        in_stock=bool(in_stock),
        total_units=p.total_stock,
        sizes=sizes,
        sizes_in_stock=in_stock,
        low_stock_sizes=low,
        sold_out_sizes=sold_out,
        summary=f"{p.name}: {p.total_stock} units in total. In stock: {available}."
        + (f" Sold out: {', '.join(sold_out)}." if sold_out else ""),
    )
    if size:
        wanted = size.strip().upper().replace("2XL", "XXL")
        match = next((s for s in sizes if s.size == wanted), None)
        if match is None:
            report.summary = f"{p.name} doesn't come in size '{size}'. Sizes are XS, S, M, L, XL, XXL. " + report.summary
        else:
            report.requested_size = match.size
            report.requested_size_quantity = match.quantity
            report.requested_size_status = match.status
            if match.quantity <= 0:
                deps.sold_out_requests.append((p.name, match.size))
                report.summary = f"Size {match.size} is SOLD OUT (0 left). In stock instead: {available}."
            else:
                report.summary = f"Size {match.size}: {match.quantity} in stock ({match.status})."
    return report


def find_similar_products(
    deps: ShopDeps,
    product: str,
    color: str | None = None,
    size: str | None = None,
    max_price: float | None = None,
    limit: int = 6,
) -> SimilarProducts | ProductNotFound:
    """Alternatives to one product, ranked by how alike they are. Used when the item
    doesn't come in the colour asked for, is sold out in their size, or is over budget."""
    base = _resolve(deps, product)
    if isinstance(base, ProductNotFound):
        return base
    want_size = size.strip().upper().replace("2XL", "XXL") if size else None
    colour_words = [color.lower(), *SYNONYMS.get(color.lower(), [])] if color else []
    base_tags = {t.lower() for t in base.search_tags} | set(re.findall(r"[a-z]{4,}", base.name.lower()))

    scored: list[tuple[float, Product]] = []
    for p in load_products():
        if p.product_id == base.product_id:
            continue
        if colour_words and not any(w in c.lower() for c in p.colors for w in colour_words):
            continue
        if want_size and not any(s.size == want_size and s.quantity > 0 for s in p.inventory):
            continue
        if max_price is not None and p.price > max_price:
            continue
        tags = {t.lower() for t in p.search_tags} | set(re.findall(r"[a-z]{4,}", p.name.lower()))
        score = (10 if p.category == base.category else 0) + len(base_tags & tags) * 2
        score += 3 if p.total_stock > 0 else -20
        score -= abs(p.price - base.price) / 20  # similar price point
        scored.append((score, p))
    scored.sort(key=lambda t: -t[0])
    top = [p for _, p in scored[: max(1, min(limit, 12))]]

    deps.seen_product_ids.update([base.product_id, *(p.product_id for p in top)])
    deps.seen_prices.update([base.price, *(p.price for p in top)])
    filters = " · ".join(f for f in (
        f"colour {color}" if color else "",
        f"in stock in {want_size}" if want_size else "",
        f"under ${max_price:g}" if max_price is not None else "",
    ) if f) or "none"
    note = None
    if not top:
        note = "Nothing in the catalogue matches those filters. Say so honestly, and offer to drop a filter."
    elif colour_words and not any(color.lower() in c.lower() for p in top for c in p.colors):
        note = (f"Nothing is listed as exactly '{color}'. These are the closest colours "
                f"({', '.join(sorted({c for p in top for c in p.colors if any(w in c.lower() for w in colour_words)}))}). Say so honestly.")
    elif colour_words and not any(base.category == p.category for p in top):
        note = f"No {base.category.lower()} in {color}; these are the closest items in other categories."
    return SimilarProducts(base=_summary(base), filters=filters, products=[_summary(p) for p in top], note=note)


# ---------- page context and the customer's own account ----------

CATEGORIES = {"Crewnecks", "Hoodies", "T-Shirts", "Quarter-Zips", "Jackets & Fleece", "Long Sleeves"}


def resolve_page(page: PageContext | None) -> tuple[PageContext | None, ViewedProduct | None]:
    """Check what the browser says is on screen against the catalogue.

    Unknown product ids / categories are dropped, so a tampered request can't make
    the agent talk about products that don't exist. Returns the cleaned page and
    the product being viewed (from the DB, without stock)."""
    if page is None:
        return None, None
    page = page.model_copy()
    viewed = None
    if page.product_id:
        found = load_products([page.product_id])
        if found:
            p = found[0]
            viewed = ViewedProduct(
                product_id=p.product_id, name=p.name, category=p.category,
                price=p.price, colors=p.colors, description=p.description,
            )
        else:
            page.product_id = None
    if page.category and page.category not in CATEGORIES:
        page.category = None
    if page.showcase_product_ids:
        real = {p.product_id for p in load_products(page.showcase_product_ids)}
        page.showcase_product_ids = [pid for pid in dict.fromkeys(page.showcase_product_ids) if pid in real]
    return page, viewed


def get_my_account(deps: ShopDeps, recent_limit: int = 8) -> AccountInfo:
    """The logged-in customer's own profile and chat memory. Scoped by the session's
    user_id (deps.customer), so it can never return another customer's data."""
    c = deps.customer
    if c.is_guest or c.user_id is None:
        return AccountInfo(
            is_guest=True,
            note="The shopper is a guest (not logged in). No name, email or saved history. "
            "Suggest logging in or creating an account if they want their chat remembered.",
        )
    with db.read_only() as conn:
        count, first_at = conn.execute(
            "SELECT count(*), min(created_at) FROM chat_messages WHERE user_id = ?", (c.user_id,)
        ).fetchone()
        rows = conn.execute(
            "SELECT products_json FROM chat_messages WHERE user_id = ? AND role = 'assistant' "
            "AND products_json IS NOT NULL ORDER BY id DESC LIMIT 40",
            (c.user_id,),
        ).fetchall()
    ids: list[str] = []
    for (raw,) in rows:
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            continue
        snapshots = data.get("cards", []) if isinstance(data, dict) else data
        if isinstance(data, dict) and isinstance(data.get("showcase"), dict):
            snapshots = snapshots + data["showcase"].get("items", [])
        ids += [p["product_id"] for p in snapshots if isinstance(p, dict) and "product_id" in p]
    recent = [_summary(p) for p in load_products(list(dict.fromkeys(ids))[:recent_limit])]
    deps.seen_product_ids.update(p.product_id for p in recent)
    deps.seen_prices.update(p.price for p in recent)
    return AccountInfo(
        is_guest=False,
        first_name=c.first_name,
        last_name=c.last_name,
        email=c.email,
        member_since=c.member_since,
        saved_messages=count,
        first_chat_at=first_at,
        recently_shown=recent,
    )


# ---------- fact check on the agent's reply ----------

PRICE_RE = re.compile(r"\$\s?(\d{1,4}(?:,\d{3})*(?:\.\d{1,2})?)")
QTY_RE = re.compile(
    r"\b(\d{1,4})\s+(?:units?\s+|pieces?\s+|of them\s+)?(?:left|in stock|available|remaining|on hand)\b"
    r"|\b(?:only|just)\s+(\d{1,4})\b",
    re.IGNORECASE,
)


def check_reply_facts(reply: str, deps: ShopDeps, user_message: str = "") -> str | None:
    """Return a correction for the model if the reply states a price or stock count the
    tools didn't return this turn, or skips saying a requested size is sold out."""
    user_numbers = {float(n) for n in re.findall(r"\d+(?:\.\d+)?", user_message)}
    problems = []

    prices = {float(m.replace(",", "")) for m in PRICE_RE.findall(reply)}
    bad_prices = sorted(p for p in prices if p not in deps.seen_prices and p not in user_numbers)
    if bad_prices:
        problems.append(
            "Your reply mentions price(s) " + ", ".join(f"${p:g}" for p in bad_prices)
            + " that no tool returned this turn. Look prices up with get_product_info or search_products and quote them exactly."
        )

    quantities = {int(a or b) for a, b in QTY_RE.findall(reply)}
    bad_qty = sorted(q for q in quantities if q not in deps.seen_quantities and float(q) not in user_numbers)
    if bad_qty:
        problems.append(
            "Your reply mentions stock count(s) " + ", ".join(map(str, bad_qty))
            + " that check_stock didn't return this turn. Call check_stock and use its exact numbers."
        )

    lowered = reply.lower()
    if deps.sold_out_requests and not any(w in lowered for w in ("sold out", "out of stock")):
        items = "; ".join(f"{name} size {size}" for name, size in deps.sold_out_requests)
        problems.append(f"The shopper asked about {items}, which is sold out. Say clearly that it is sold out.")

    return " ".join(problems) or None
