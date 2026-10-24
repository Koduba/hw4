"""Pydantic / PydanticAI structured types for the Campus Customs API and agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["Crewnecks", "Hoodies", "T-Shirts", "Quarter-Zips", "Jackets & Fleece", "Long Sleeves"]
Size = Literal["XS", "S", "M", "L", "XL", "XXL"]

MAX_CHAT_MESSAGE = 1000
MAX_PRODUCTS_PER_REPLY = 6  # small cards inside the chat bubble
MAX_SHOWCASE = 24  # product cards the agent can put on the page in one go
MAX_SEARCH_RESULTS = 24


# ---------- catalogue (API responses) ----------

class SizeStock(BaseModel):
    size: str
    quantity: int


class Product(BaseModel):
    """Full product as sent to the website (cards and product pages)."""
    product_id: str
    name: str
    garment_type: str
    category: str
    description: str
    colors: list[str]
    search_tags: list[str]
    image_url: str
    model_image_url: str | None = Field(default=None, description="AI-styled on-model photo, if one exists.")
    price: float
    total_stock: int
    inventory: list[SizeStock]


def short_info(description: str, limit: int = 110) -> str:
    """First sentence of the catalogue description, trimmed for a card."""
    first = description.split(". ")[0].strip().rstrip(".")
    return first if len(first) <= limit else first[: limit - 1].rsplit(" ", 1)[0] + "…"


class ProductCard(BaseModel):
    """One product tile, used in chat bubbles and in the on-page showcase."""
    product_id: str
    name: str
    category: str
    price: float
    image_url: str = Field(description="Served by FastAPI under /media/products/.")
    model_image_url: str | None = Field(default=None, description="AI-styled on-model photo, if one exists.")
    page_url: str = Field(description="Front-end route for the product page.")
    short_info: str = Field(description="First sentence of the catalogue description.")
    colors: list[str]
    sizes_in_stock: list[str]
    in_stock: bool
    stock_label: str = Field(description="'In stock', 'Low stock', 'Sold out', or 'Sold out in M, XL'.")
    note: str | None = Field(default=None, description="Assistant's one-line reason this item matches (showcase only).")

    @classmethod
    def from_product(cls, p: Product, note: str | None = None) -> "ProductCard":
        sizes = [s.size for s in p.inventory if s.quantity > 0]
        sold_out = [s.size for s in p.inventory if s.quantity <= 0]
        if not sizes:
            label = "Sold out"
        elif sold_out:
            label = "Sold out in " + ", ".join(sold_out)
        elif any(s.quantity <= 5 for s in p.inventory):
            label = "Low stock"
        else:
            label = "In stock"
        return cls(
            product_id=p.product_id,
            name=p.name,
            category=p.category,
            price=p.price,
            image_url=p.image_url,
            model_image_url=p.model_image_url,
            page_url=f"/products/{p.product_id}",
            short_info=short_info(p.description),
            colors=p.colors,
            sizes_in_stock=sizes,
            in_stock=bool(sizes),
            stock_label=label,
            note=note,
        )


# ---------- what the agent's tools return ----------
# These are returned to the model as JSON. Each field is something the model needs to
# answer a shopper (see "Tool return types" in output/harness.md for why each exists).
# Numbers are passed as numbers, never pre-formatted text, so the reply fact check can
# compare them with what the database returned.

StockStatus = Literal["in stock", "low stock", "sold out"]
LOW_STOCK = 5  # 1-5 units left counts as "low stock"


class ProductSummary(BaseModel):
    """search_products hit: enough to recommend and compare, small enough to list many."""
    product_id: str = Field(description="Stable key for follow-up calls and product cards.")
    name: str
    category: str = Field(description="One of the 6 clean shop categories, not the raw garment_type.")
    price: float = Field(description="USD price from the catalogue table.")
    colors: list[str]
    in_stock: bool = Field(description="False if every size is sold out.")
    sizes_in_stock: list[Size] = Field(description="Sizes with at least one unit left.")


class SearchResults(BaseModel):
    """search_products: ranked matches for the shopper's words and filters."""
    query: str
    total_matches: int = Field(description="All matches, even if only `limit` are listed.")
    products: list[ProductSummary]
    note: str | None = Field(default=None, description="E.g. 'We don't sell shorts' or 'No matches'.")


class ProductInfo(BaseModel):
    """get_product_info: what the item is and what it costs (catalogue table only, no stock)."""
    product_id: str
    name: str
    category: str
    garment_type: str = Field(description="Original style wording, e.g. 'quarter-zip pullover sweatshirt'.")
    description: str = Field(description="Catalogue description; the only source for looks and details.")
    price: float = Field(description="USD price. Quote exactly this number.")
    colors: list[str] = Field(description="Colours listed in the catalogue; may be empty.")


class SizeAvailability(BaseModel):
    """One row of the inventory table, with a status the model can say out loud."""
    size: Size
    quantity: int = Field(ge=0, description="Units on hand right now.")
    status: StockStatus


class StockReport(BaseModel):
    """check_stock: live inventory for one product, optionally focused on one size."""
    product_id: str
    name: str
    price: float = Field(description="Included so 'price and do you have it in L?' needs one call.")
    in_stock: bool = Field(description="True if any size has at least 1 unit.")
    total_units: int = Field(ge=0)
    sizes: list[SizeAvailability] = Field(description="All six sizes, XS to XXL, in order.")
    sizes_in_stock: list[Size]
    low_stock_sizes: list[Size] = Field(description="Sizes with 1-5 units left.")
    sold_out_sizes: list[Size]
    requested_size: Size | None = Field(default=None, description="The size asked about, normalised (m to M, 2XL to XXL).")
    requested_size_quantity: int | None = None
    requested_size_status: StockStatus | None = Field(default=None, description="Drives the wording: sold out, low or in stock.")
    summary: str = Field(description="Ready-made one-line answer that names sold-out sizes explicitly.")


class SimilarProducts(BaseModel):
    """find_similar_products: alternatives to one product (e.g. it's not in pink, or sold out in M)."""
    base: ProductSummary = Field(description="The product the shopper asked about.")
    filters: str = Field(description="Plain-English filters applied, e.g. 'colour pink · in stock in M'.")
    products: list[ProductSummary] = Field(description="Best alternatives first: same category, shared style tags.")
    note: str | None = None


class ProductNotFound(BaseModel):
    """Returned instead of ProductInfo/StockReport when the product can't be identified."""
    query: str = Field(description="What the model asked for.")
    error: str
    did_you_mean: list[ProductSummary] = Field(default_factory=list, max_length=3)


# ---------- who is chatting, and what is on their screen ----------

class CustomerContext(BaseModel):
    """Who is chatting. Built by the server from the session cookie, never from chat text.

    The agent sees these fields (via its instructions and get_my_account). `user_id`
    is internal: tools use it to scope database reads to this customer, but it is
    excluded from anything sent to the model.
    """
    is_guest: bool
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    member_since: str | None = Field(default=None, description="Account creation date (YYYY-MM-DD).")
    user_id: int | None = Field(default=None, exclude=True)

    @classmethod
    def guest(cls) -> "CustomerContext":
        return cls(is_guest=True)

    @property
    def full_name(self) -> str | None:
        return " ".join(n for n in (self.first_name, self.last_name) if n) or None


class PageContext(BaseModel):
    """What the shopper's browser says is on screen. Sent with every chat message.

    Untrusted input: the server checks product ids against the catalogue and treats
    the text fields as data, never as instructions.
    """
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    path: str = Field(default="/", max_length=200, description="Current route, e.g. /products/basic-hoodie-big-yale.")
    product_id: str | None = Field(default=None, max_length=120, description="Set on a product page.")
    search_query: str | None = Field(default=None, max_length=100, description="?q= on the Products page.")
    category: str | None = Field(default=None, max_length=40, description="?category= on the Products page.")
    showcase_title: str | None = Field(default=None, max_length=60)
    showcase_product_ids: list[str] = Field(default_factory=list, max_length=24, description="Picks visible on the page, in order.")


class ViewedProduct(BaseModel):
    """The product page the shopper is on, resolved from the database (no stock: use check_stock)."""
    product_id: str
    name: str
    category: str
    price: float
    colors: list[str]
    description: str


class AccountInfo(BaseModel):
    """get_my_account: the logged-in shopper's own profile and chat memory."""
    is_guest: bool
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    member_since: str | None = None
    saved_messages: int = 0
    first_chat_at: str | None = None
    recently_shown: list[ProductSummary] = Field(default_factory=list, description="Products shown to them in past chats, newest first.")
    note: str | None = None


# ---------- agent output and dependencies ----------

class ShowcaseItem(BaseModel):
    product_id: str = Field(description="An id returned by search_products this turn.")
    note: str | None = Field(
        default=None,
        max_length=80,
        description="Optional 3-8 word reason it fits, e.g. 'Vintage bulldog graphic'. No prices or stock counts.",
    )


class ShowcasePlan(BaseModel):
    """The agent's request to put a set of matching products on the web page."""
    title: str = Field(max_length=60, description="Heading for the page section, e.g. 'Hoodies' or 'Saybrook gear under $60'.")
    items: list[ShowcaseItem] = Field(min_length=1, max_length=MAX_SHOWCASE, description="Best match first.")


class ShopReply(BaseModel):
    """Structured answer the agent must return for every chat turn."""
    reply: str = Field(
        description="Friendly plain-text answer for the shopper (no markdown). Mention prices and sizes you verified with tools."
    )
    product_ids: list[str] = Field(
        default_factory=list,
        max_length=MAX_PRODUCTS_PER_REPLY,
        description="product_id values to show as cards under the reply, most relevant first. Only ids returned by tools.",
    )
    showcase: ShowcasePlan | None = Field(
        default=None,
        description="Set when the shopper is browsing a type of item (e.g. 'what hoodies do you have?'): "
        "the website shows these products as cards on the page. Leave null for single-product questions.",
    )


@dataclass
class ShopDeps:
    """Per-request context handed to every instruction function and tool.

    customer: who is chatting (from the session cookie; guest if not logged in).
    page / viewed_product: what's on their screen (from the request, checked against the DB).
    """
    customer: CustomerContext = field(default_factory=CustomerContext.guest)
    current_product_id: str | None = None
    user_message: str = ""  # numbers the shopper typed (e.g. "under $60") are fine to repeat
    page: PageContext | None = None
    viewed_product: ViewedProduct | None = None
    prior_messages: int = 0  # how many saved messages this customer already has
    # What the tools actually returned this turn. The output check uses these so the
    # reply can't contain product ids, prices or quantities the database didn't give.
    seen_product_ids: set[str] = field(default_factory=set)
    seen_prices: set[float] = field(default_factory=set)
    seen_quantities: set[int] = field(default_factory=set)
    # (product name, size) pairs the shopper asked about that are sold out; the reply must say so.
    sold_out_requests: list[tuple[str, str]] = field(default_factory=list)
    # Most recent search this turn; gives the showcase its query and total match count.
    last_search: SearchResults | None = None


# ---------- audit trail (output/audit_trail.json) ----------

AuditEvent = Literal["run_start", "model_response", "tool_call", "tool_result", "retry", "run_end"]


class AuditEntry(BaseModel):
    """One step of the agent loop. Appended to output/audit_trail.json, never rewritten.

    Kept short and privacy-safe: who is "guest" or "user:<id>" (no names/emails),
    text fields are truncated and email addresses / card numbers are masked.
    """
    timestamp: str = Field(description="UTC ISO-8601, when the step happened.")
    run_id: str = Field(description="Groups every step of one chat turn.")
    step: int = Field(description="Order within the run (1, 2, 3 …).")
    event: AuditEvent
    who: str = Field(description='"guest" or "user:<id>", never a name or email.')
    message: str | None = Field(default=None, description="run_start: the shopper's message (truncated, masked).")
    page: str | None = Field(default=None, description="run_start: product page the shopper was on, if any.")
    tool_name: str | None = None
    tool_args: str | None = Field(default=None, description="Short JSON of the arguments the model passed.")
    result_summary: str | None = Field(default=None, description="Short summary of what the tool returned.")
    finish_reason: str | None = Field(default=None, description="model_response: why the model stopped (tool_call, stop …).")
    stop_reason: str | None = Field(
        default=None,
        description="run_end: final_result | content_filter | usage_limit | output_retries_exhausted | error",
    )
    tokens_in: int | None = None
    tokens_out: int | None = None
    duration_ms: int | None = None
    detail: str | None = Field(default=None, description="Retry reason, error type, or reply summary.")


# ---------- chat API ----------

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=MAX_CHAT_MESSAGE)
    page: PageContext | None = None
    # Older clients sent only this; it is folded into page.product_id.
    current_product_id: str | None = Field(default=None, max_length=120)


class Showcase(BaseModel):
    """API contract for the on-page product showcase (POST /api/chat → website).

    The agent decides WHICH products (ShowcasePlan); the backend turns that into
    cards from the database, so names, prices, images and stock are always real.
    """
    id: str = Field(description="Unique per showcase, so the front end can animate a fresh set.")
    title: str
    query: str = Field(description="What was searched, for 'See all on the Products page'.")
    category: str | None = Field(default=None, description="Set if every item shares one category.")
    total_matches: int = Field(description="All catalogue matches for the search (may exceed len(products)).")
    products: list[ProductCard]


class ChatMessage(BaseModel):
    """One saved message, as returned by GET /api/chat/history."""
    role: Literal["user", "assistant"]
    content: str
    products: list[ProductCard] = Field(default_factory=list)
    showcase: Showcase | None = None
    viewing_product_id: str | None = Field(default=None, description="Product page the shopper was on when they sent it.")
    created_at: str | None = None


class ChatResponse(BaseModel):
    """What POST /api/chat returns: the agent's text, chat cards, and an optional page showcase."""
    reply: str
    products: list[ProductCard] = Field(default_factory=list)
    showcase: Showcase | None = None
    saved: bool = Field(default=False, description="True if this turn was stored in the database (logged-in users).")
