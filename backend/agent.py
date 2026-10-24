"""Campus Customs shopping agent: PydanticAI wiring and the entry point main.py calls.

    reply = await run_chat(customer, "do you have this in pink?", page=PageContext(...), guest_id=None)

The system prompt lives in prompts/prompt.md, tools in tools.py, types in models.py,
chat history (DB for logged-in users, server memory for guests) in memory.py.

Each run gets ShopDeps with:
  - customer: who is chatting (name, email, member since) from the session cookie
  - page / viewed_product: what is on their screen, checked against the catalogue
Two @agent.instructions functions turn those into text the model reads every turn.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from functools import lru_cache
from pathlib import Path

from pydantic_ai import Agent, AgentRetries, ModelRetry, RunContext, capture_run_messages
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.usage import UsageLimits

import memory
import safety
import tools
from audit import RunAudit
from models import (
    MAX_SHOWCASE,
    AccountInfo,
    ChatMessage,
    ChatResponse,
    CustomerContext,
    PageContext,
    ProductCard,
    Showcase,
    ProductInfo,
    ProductNotFound,
    SearchResults,
    ShopDeps,
    SimilarProducts,
    ShopReply,
    StockReport,
)

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "prompts" / "prompt.md"

HISTORY_MESSAGES = 20  # how many past messages the model sees
REPLAY_REPLY_CHARS = 320  # older assistant replies are trimmed to this in the replayed history
usage_log = logging.getLogger("uvicorn.error")  # shows up in the uvicorn terminal
LIMITS = UsageLimits(request_limit=8)  # stops runaway tool loops (incl. fact-check retries)
# Shown when the model provider's safety filter blocks a message (e.g. jailbreak attempts).
FILTERED_REPLY = (
    "Sorry, I can't help with that. I can only help with Campus Customs products: "
    "finding gear, checking sizes, colours, prices and stock."
)


@lru_cache(maxsize=1)
def build_agent() -> Agent[ShopDeps, ShopReply]:
    agent: Agent[ShopDeps, ShopReply] = Agent(
        tools.get_model(),
        deps_type=ShopDeps,
        output_type=ShopReply,
        # Extra output retries give room to fix a reply the database fact check rejects.
        retries=AgentRetries(tools=2, output=3),
        name="campus_customs_assistant",
    )

    @agent.instructions
    def load_prompt() -> str:
        # Read on every run so edits to prompt.md apply without a restart.
        return PROMPT_PATH.read_text(encoding="utf-8")

    @agent.instructions
    def who_is_chatting(ctx: RunContext[ShopDeps]) -> str:
        return customer_instructions(ctx.deps)

    @agent.instructions
    def whats_on_screen(ctx: RunContext[ShopDeps]) -> str:
        return page_instructions(ctx.deps)

    @agent.tool
    def search_products(
        ctx: RunContext[ShopDeps],
        query: str = "",
        category: str | None = None,
        color: str | None = None,
        max_price: float | None = None,
        size: str | None = None,
        limit: int = 8,
    ) -> SearchResults:
        """Search the Campus Customs catalogue. Results are sorted best match first.

        Args:
            query: Free-text words, e.g. "Saybrook", "bulldog", "football", "mom". Empty lists everything.
            category: One of Crewnecks, Hoodies, T-Shirts, Quarter-Zips, Jackets & Fleece, Long Sleeves.
            color: Colour the item must include, e.g. "navy", "gray", "white".
            max_price: Highest price in USD.
            size: Only items with this size in stock (XS, S, M, L, XL, XXL).
            limit: Max results (1-24). Use 12-24 when the shopper is browsing a type of item.
        """
        return tools.search_products(ctx.deps, query, category, color, max_price, size, limit)

    @agent.tool
    def get_product_info(ctx: RunContext[ShopDeps], product: str) -> ProductInfo | ProductNotFound:
        """Description, price, colours and category for one product, from the database.
        Use for "what is it / what does it look like / how much is it".

        Args:
            product: The product_id (preferred) or the product's name.
        """
        return tools.get_product_info(ctx.deps, product)

    @agent.tool
    def check_stock(ctx: RunContext[ShopDeps], product: str, size: str | None = None) -> StockReport | ProductNotFound:
        """Live units on hand for one product, per size, from the inventory table.
        Use whenever you mention availability or how many are left. Pass `size` when the shopper asks about one.

        Args:
            product: The product_id (preferred) or the product's name.
            size: Optional size the shopper asked about: XS, S, M, L, XL or XXL.
        """
        return tools.check_stock(ctx.deps, product, size)

    @agent.tool
    def find_similar_products(
        ctx: RunContext[ShopDeps],
        product: str,
        color: str | None = None,
        size: str | None = None,
        max_price: float | None = None,
        limit: int = 6,
    ) -> SimilarProducts | ProductNotFound:
        """Alternatives to one product: same category and style first, in-stock first.
        Use when the item doesn't come in the colour they want, is sold out in their size,
        or costs more than their budget, and for "anything like this?".

        Args:
            product: product_id (preferred) or name of the item they're asking about.
            color: Colour the alternatives must come in, e.g. "pink", "white".
            size: Only alternatives with this size in stock (XS-XXL).
            max_price: Highest price in USD.
            limit: How many alternatives (1-12).
        """
        return tools.find_similar_products(ctx.deps, product, color, size, max_price, limit)

    @agent.tool
    def get_my_account(ctx: RunContext[ShopDeps]) -> AccountInfo:
        """The shopper's own account: name, email, customer since, how many chat messages are saved,
        and products shown to them in past chats (newest first). Guests get is_guest=true.
        Use for "what's my email?", "what did you show me last time?", "do you remember me?"."""
        return tools.get_my_account(ctx.deps)

    @agent.output_validator
    def grounded_in_database(ctx: RunContext[ShopDeps], output: ShopReply) -> ShopReply:
        # 1. Prices and stock counts in the text must be ones the tools returned this turn,
        #    and a requested sold-out size must be called sold out. Otherwise the model retries.
        notes = " ".join(i.note or "" for i in output.showcase.items) if output.showcase else ""
        if problem := tools.check_reply_facts(f"{output.reply} {notes}", ctx.deps, ctx.deps.user_message):
            raise ModelRetry(problem)
        # Safety (Problem 12): no links, no one else's email address.
        if problem := safety.reply_problem(f"{output.reply} {notes}", ctx.deps.customer.email):
            raise ModelRetry(problem)
        # 2. Cards and showcase items only for products a tool returned this turn
        #    (or the one being viewed): never invented or injected ids.
        allowed = ctx.deps.seen_product_ids | on_screen_ids(ctx.deps)
        output.product_ids = [pid for pid in dict.fromkeys(output.product_ids) if pid in allowed]
        if output.showcase:
            seen: set[str] = set()
            output.showcase.items = [
                i for i in output.showcase.items if i.product_id in allowed and not (i.product_id in seen or seen.add(i.product_id))
            ]
            if not output.showcase.items:
                output.showcase = None
        return output

    return agent


# ---------- agent context: customer + page (dynamic instructions) ----------

def _q(text: str | None) -> str:
    """Quote browser-supplied text so it reads as data, not instructions."""
    return json.dumps(text or "")


def customer_instructions(deps: ShopDeps) -> str:
    c = deps.customer
    if c.is_guest:
        return (
            "## Who you're chatting with\n"
            "- A **guest** (not logged in). You don't know their name or email, and you shouldn't ask for them.\n"
            "- This conversation is not saved after they leave. If they want you to remember it, "
            "or they ask about past chats, suggest logging in or creating an account."
        )
    lines = [
        "## Who you're chatting with",
        f"- Logged-in customer: {c.full_name or c.first_name or 'unknown name'}",
        f"- First name: {c.first_name or 'unknown'}",
        f"- Email: {c.email}",
        f"- Customer since: {c.member_since or 'unknown'}",
    ]
    if deps.prior_messages:
        lines.append(
            f"- Returning customer: {deps.prior_messages} earlier chat messages are saved. The most recent are in "
            "this conversation's history; call get_my_account for products shown in past chats."
        )
    else:
        lines.append("- First conversation with you.")
    return "\n".join(lines)


def page_instructions(deps: ShopDeps) -> str:
    page, viewed = deps.page, deps.viewed_product
    lines = ["## What's on their screen (sent by the website, checked against the catalogue)"]
    if page is None:
        lines.append("- Unknown (no page context sent).")
        return "\n".join(lines)
    if viewed:
        colours = ", ".join(viewed.colors) if viewed.colors else "not listed in the catalogue"
        lines += [
            f"- **Product page:** {viewed.name} (product_id `{viewed.product_id}`), {viewed.category}, ${viewed.price:g}.",
            f"- Colours it comes in: {colours}.",
            f"- Description: {viewed.description}",
            '- "This", "this one", "it", "this hoodie" mean this product. Answer colour questions from the colours above. '
            "For sizes or stock, call check_stock with this product_id.",
        ]
    elif page.path.startswith("/products"):
        filters = []
        if page.category:
            filters.append(f"category {page.category}")
        if page.search_query:
            filters.append(f"search {_q(page.search_query)}")
        lines.append("- Browsing the Products page" + (f" filtered by {' and '.join(filters)}." if filters else " (all products)."))
    else:
        lines.append(f"- Page: {_q(page.path)} (not a product page).")
    if page.showcase_product_ids:
        lines.append(
            f"- Your picks are on screen as {_q(page.showcase_title)}: "
            + ", ".join(f"{i}. {pid}" for i, pid in enumerate(page.showcase_product_ids, 1))
        )
    return "\n".join(lines)


def on_screen_ids(deps: ShopDeps) -> set[str]:
    ids = set(deps.page.showcase_product_ids) if deps.page else set()
    if deps.current_product_id:
        ids.add(deps.current_product_id)
    return ids


def build_showcase(plan, deps: ShopDeps, showcase_id: str | None = None) -> Showcase:
    """Turn the agent's ShowcasePlan (ids + notes) into real cards from the database."""
    notes = {i.product_id: i.note for i in plan.items}
    products = tools.load_products(list(notes)[:MAX_SHOWCASE])
    cards = [ProductCard.from_product(p, note=notes.get(p.product_id)) for p in products]
    categories = {c.category for c in cards}
    search = deps.last_search
    return Showcase(
        id=showcase_id or uuid.uuid4().hex,
        title=plan.title,
        query=search.query if search else "",
        category=categories.pop() if len(categories) == 1 else None,
        total_matches=max(search.total_matches if search else 0, len(cards)),
        products=cards,
    )


def _to_model_messages(history: list[ChatMessage]) -> list[ModelMessage]:
    """Replay saved chat as model history, compacted to save tokens (Problem 9):
    shopper messages stay word-for-word; older assistant replies are trimmed; only the
    most recent showcase keeps its full numbered list (that's the one "the third one"
    refers to). Facts never come from here anyway: prices and stock are re-checked by tools."""
    messages: list[ModelMessage] = []
    last_showcase = max((i for i, m in enumerate(history) if m.showcase), default=-1)
    for i, m in enumerate(history):
        if m.role == "user":
            text = m.content
            if m.viewing_product_id:  # so an old "do you have this in pink?" still says which item
                text += f"\n[Shopper was viewing product: {m.viewing_product_id}]"
            messages.append(ModelRequest(parts=[UserPromptPart(content=text)]))
        else:
            text = m.content
            if len(text) > REPLAY_REPLY_CHARS:
                text = text[:REPLAY_REPLY_CHARS].rsplit(" ", 1)[0] + " …"
            # Numbered, so "the second one" / "the third one on the page" can be counted, not guessed.
            if m.products:
                text += "\n[Product cards shown: " + _numbered(p.product_id for p in m.products) + "]"
            if m.showcase and i == last_showcase:
                text += f"\n[Showcase on page '{m.showcase.title}': " + _numbered(p.product_id for p in m.showcase.products) + "]"
            elif m.showcase:
                text += f"\n[Showcase on page '{m.showcase.title}' ({len(m.showcase.products)} items, since replaced)]"
            messages.append(ModelResponse(parts=[TextPart(content=text)]))
    # The model expects history to start with a user turn.
    while messages and isinstance(messages[0], ModelResponse):
        messages.pop(0)
    return messages


def _numbered(ids) -> str:
    return ", ".join(f"{i}. {pid}" for i, pid in enumerate(ids, 1))


# ---------- entry point ----------

def log_usage(customer: CustomerContext, result, seconds: float, showcase: Showcase | None) -> None:
    """One line per chat turn in the uvicorn terminal: speed, model calls, tools, tokens."""
    who = "guest" if customer.is_guest else f"user:{customer.user_id}"
    if result is None:
        usage_log.info("chat turn %s | %.1fs | blocked by provider content filter", who, seconds)
        return
    usage = result.usage() if callable(result.usage) else result.usage
    tools_used = [p.tool_name for m in result.new_messages() for p in getattr(m, "parts", [])
                  if getattr(p, "part_kind", "") == "tool-call" and not p.tool_name.startswith("final_result")]
    usage_log.info(
        "chat turn %s | %.1fs | %d model calls | tools: %s | tokens in %s / out %s%s",
        who, seconds, usage.requests, ", ".join(tools_used) or "none",
        f"{usage.input_tokens:,}", f"{usage.output_tokens:,}",
        f" | showcase: {len(showcase.products)} cards" if showcase else "",
    )


def make_deps(customer: CustomerContext, message: str, page: PageContext | None, prior_messages: int = 0) -> ShopDeps:
    page, viewed = tools.resolve_page(page)
    deps = ShopDeps(
        customer=customer,
        current_product_id=viewed.product_id if viewed else None,
        user_message=message,
        page=page,
        viewed_product=viewed,
        prior_messages=prior_messages,
    )
    if viewed:  # its price came from the DB, so the fact check may let the reply quote it
        deps.seen_product_ids.add(viewed.product_id)
        deps.seen_prices.add(viewed.price)
    return deps


async def run_chat(
    customer: CustomerContext,
    message: str,
    page: PageContext | None = None,
    guest_id: str | None = None,
) -> ChatResponse:
    """One chat turn. Logged-in: history from/to the chat_messages table. Guest: server memory only.
    Every step of the agent loop is appended to output/audit_trail.json."""
    logged_in = not customer.is_guest and customer.user_id is not None
    # Safety: strip card numbers / passwords / SSNs before the model, the DB or the audit see them.
    message, removed = safety.redact_input(message)
    if logged_in:
        past = memory.load_history(customer.user_id, HISTORY_MESSAGES)
        prior = memory.count_messages(customer.user_id)
    else:
        past = memory.guest_memory.get(guest_id)
        prior = 0
    deps = make_deps(customer, message, page, prior)

    # Put the product on screen right next to the question. In instructions alone, the model
    # sometimes followed the chat's previous topic instead (Problem 9 finding).
    prompt = message
    if deps.viewed_product:
        prompt += f"\n[Shopper is viewing product now: {deps.viewed_product.product_id} ({deps.viewed_product.name})]"
    if removed:
        prompt += (f"\n[Safety note: the shopper's message contained a {', '.join(removed)}, which was removed. "
                   "Kindly remind them never to share it in chat; we never need it.]")

    audit = RunAudit("guest" if customer.is_guest else f"user:{customer.user_id}")
    audit.add("run_start", message=message, page=deps.current_product_id,
              detail=f"removed: {', '.join(removed)}" if removed else None)
    history = _to_model_messages(past)
    started = time.perf_counter()
    result, stop, error = None, "error", None
    with capture_run_messages() as run_messages:
        try:
            result = await build_agent().run(prompt, deps=deps, message_history=history, usage_limits=LIMITS)
            out = result.output
            reply = out.reply
            products = memory.cards(out.product_ids)  # fresh price/stock from the DB, not the model's words
            showcase = build_showcase(out.showcase, deps) if out.showcase else None
            stop = "final_result"
        except ModelHTTPError as e:
            if "content_filter" not in str(e.body):
                error = f"ModelHTTPError {e.status_code}"
                raise
            reply, products, showcase, stop = FILTERED_REPLY, [], None, "content_filter"
        except UsageLimitExceeded as e:
            stop, error = "usage_limit", str(e)
            raise
        except UnexpectedModelBehavior as e:
            stop, error = "output_retries_exhausted", str(e)
            raise
        except Exception as e:
            error = type(e).__name__
            raise
        finally:
            audit.from_messages(run_messages[len(history):])
            usage = (result.usage() if callable(result.usage) else result.usage) if result else None
            if error:
                detail = error
            elif stop in ("final_result", "content_filter"):
                detail = f"reply: {reply}"
                if stop == "final_result":
                    detail = (f"cards: {len(products)} | " if products else "") + (
                        f"showcase: {len(showcase.products)} | " if showcase else "") + detail
            else:
                detail = None
            audit.add(
                "run_end", stop_reason=stop, duration_ms=round((time.perf_counter() - started) * 1000),
                tokens_in=usage.input_tokens if usage else None, tokens_out=usage.output_tokens if usage else None,
                detail=detail,
            )
            audit.write()

    log_usage(customer, result, time.perf_counter() - started, showcase)
    viewing = deps.current_product_id
    if logged_in:
        memory.save_turn(customer.user_id, message, reply, products, showcase, viewing, deps.page.path if deps.page else None)
    elif guest_id:
        memory.guest_memory.append(
            guest_id,
            ChatMessage(role="user", content=message, viewing_product_id=viewing),
            ChatMessage(role="assistant", content=reply, products=products, showcase=showcase),
        )
    return ChatResponse(reply=reply, products=products, showcase=showcase, saved=logged_in)


if __name__ == "__main__":  # quick manual test: python agent.py "any navy hoodies under $70?"
    import asyncio
    import sys

    async def _demo() -> None:
        question = " ".join(sys.argv[1:]) or "What hoodies do you have?"
        deps = ShopDeps(customer=CustomerContext(is_guest=False, first_name="Test", last_name="User"), user_message=question)
        result = await build_agent().run(question, deps=deps, usage_limits=LIMITS)
        print(result.output.model_dump_json(indent=2))

    asyncio.run(_demo())
