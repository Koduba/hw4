# Problem 9: Usability Improvements

Four improvements: two on the front end and two on the agent/backend. Each one is live in the running app (http://localhost:5173 with the backend on :8000). Every section below says **what was added**, **how it helps a shopper or the business**, **where to see it**, and **how it was verified**.

| # | Type | Improvement | Where to see it |
|---|---|---|---|
| 1 | Front end | Smart quick-reply chips in the chat | Open the pink chat button on any page |
| 2 | Front end | "In stock in my size" filter and sort on Products | `/products`: size chips and the Sort menu under the categories |
| 3 | Agent | `find_similar_products` tool: never a dead-end "no" | On a product page, ask "do you have this in pink?" or "do you have this in M?" for a sold-out size |
| 4 | Agent / backend | Sharper, cheaper context and a per-turn usage meter | Ask "this" questions on a product page; watch the backend terminal for `chat turn …` lines |

---

## 1. Smart quick-reply chips in the chat (front end)

**What I added:** a row of one-tap suggestion chips above the chat input (`frontend/src/components/QuickReplies.tsx`). Tapping one sends it straight away. The chips change with the page:

| Where the shopper is | Chips shown |
|---|---|
| Home, About, any other page | "What hoodies do you have?" · "Gift ideas under $60" · "Anything with Handsome Dan?" |
| Products page filtered to a category (e.g. Hoodies) | "Which hoodies are in stock in L?" first, then the general ones |
| A product page | "Do you have this in M?" · "What colours does it come in?" · "Show me similar items under $60" |
| Picks from the assistant are on the page | "Is the first one in stock in M?" |
| Logged in with saved history | "What did you show me last time?" |

**How it helps:**
- **Shoppers:** an empty chat box gives no hint of what the assistant can do. The chips show its best tricks (size and stock checks, budget gift ideas, finding the bulldog mascot gear, memory) and save typing, especially on phones.
- **Business:** more shoppers start a conversation, and the chips steer them toward questions that end in a product card (a step closer to a sale). The product-page chips use the page context from Problem 8, so "this" always resolves to the item on screen.

**Verified in the browser:**
- Home showed the three general chips; `/products?category=Hoodies` added "Which hoodies are in stock in L?"; the Basic Hoodie page showed the three product chips.
- Tapping "What colours does it come in?" on the Basic Hoodie page got "This hoodie comes in navy blue and white."
- Tapping "Do you have this in M?" on the Football tee (M is sold out) got "Sorry, size M is sold out…" with in-stock alternatives (see #3).
- Chips are disabled while the assistant is answering, so a shopper can't double-send.

Screenshot: `screenshots/2-chat-quick-replies.png`

---

## 2. "In stock in my size" filter and sort on Products (front end)

**What I added** (on `frontend/src/pages/Products.tsx`, alongside the existing search and category chips):
- **In stock in:** Any size / XS / S / M / L / XL / XXL. Picking a size hides every product that's sold out in it, and each card's stock badge switches to that size: "20 in stock in M", "Only 5 left in M".
- **Sort:** Featured, Price: low to high, Price: high to low, Most in stock (in the chosen size), Name A–Z.
- **Clear all**, which resets search, category, size and sort in one click. The "no results" message also offers it.
- Everything is stored in the URL (`/products?size=M&sort=price-asc`), so it survives refresh, the back button and sharing a link.

**How it helps:**
- **Shoppers:** a quarter of all size slots are sold out (145 of 612, from the Problem 2 analysis). Without this, a shopper could fall for a hoodie and only discover on the product page that their size is gone. Now they only see what they can actually buy, and budget shoppers can sort by price.
- **Business:** fewer dead-end clicks and less frustration means more completed purchases. "Most in stock" also helps move deep inventory, such as the 116-unit football tri-blend tee.

**Verified in the browser:**
- Picking **M** showed "80 products in stock in M", which exactly matches the database (`SELECT count(DISTINCT product_id) FROM inventory WHERE size='M' AND quantity>0` → 80). Every card's badge mentioned M.
- **Price: low to high** started at $32.00 and ended at $98.00; **high to low** started with the $98 Benjamin Franklin Fleece Jacket. The URL became `?size=M&sort=price-asc`.
- **Clear all** brought back all 102 products, with an empty query string.

Screenshot: `screenshots/1-products-size-sort.png`

---

## 3. `find_similar_products` tool: never a dead-end "no" (agent)

**What I added:** a new agent tool in `backend/tools.py`, registered in `agent.py`, with a return type `SimilarProducts` in `models.py`:

```
find_similar_products(product, color=None, size=None, max_price=None, limit=6)
  → SimilarProducts { base, filters, products: ProductSummary[], note }
```

- **Ranking:** same category first (+10), shared style tags and name words, in-stock items before sold-out ones, and a similar price point.
- **Hard filters:** colour (with colour families, so "pink" also matches "coral"/"rose"), **size in stock**, and max price.
- **Honest notes:** if nothing is literally that colour, the `note` says so ("Nothing is listed as exactly 'pink'. These are the closest colours (dusty coral). Say so honestly.").
- Results are recorded in `ShopDeps`, so the database fact check still applies to every price the agent quotes, and the alternatives can be shown as cards.
- **Prompt (`prompts/prompt.md` → "Don't stop at 'no'"):** give the honest answer first, then call the tool and suggest the top 1–3 with prices as cards. Never call a colour something it isn't.

**How it helps:**
- **Shoppers:** questions like "do you have this in pink?" or "M is sold out?" used to end with "no". Now they end with a real, in-stock suggestion they can tap.
- **Business:** it turns lost sales into alternative sales, which matters because 21 products are sold out in 3 or more sizes. Accuracy is protected: alternatives come from the database and are fact-checked, and colours are never misnamed.

**Verified:**

| Where / question | Tools the agent called | Reply |
|---|---|---|
| Basic Hoodie page: "do you have this in pink?" | `find_similar_products(basic-hoodie-big-yale, color=pink)` | "This hoodie only comes in navy blue and white, not pink. The closest colour we carry is dusty coral in the Big Yale Tri Blend T-Shirt for $32…" plus 1 card |
| Football tee page: "Do you have this in M?" (chip) | `check_stock(…, M)` → `find_similar_products(…, size=M)` | "Sorry, size M is sold out… the Track Field Left Chest T Shirt is $32 and comes in M, or the Boola Boola T Shirt…" plus 2 cards |

- Unit tests (`tests/test_tools.py`):
  - pink returns only the dusty-coral tee, with the honest note;
  - for the football tee's sold-out M, every alternative has M in stock, the top one is a T-shirt, and the original is excluded;
  - a `max_price=60` budget is respected.

Screenshots: `screenshots/3-similar-pink.png`, `screenshots/4-similar-sold-out-size.png`

---

## 4. Sharper, cheaper context and a per-turn usage meter (agent / backend)

**Why this one:** I first planned a catalogue cache to make tools faster. I measured before building it: database lookups take only **0.1–1.2 ms**, while one model call takes about **4–5 s**. Caching would have saved nothing a shopper could notice. The real cost and speed driver is **tokens sent to the model**. The same measurement also turned up an **accuracy bug**.

**The bug (found by measuring):** the Test User's last chat was about the Football tee. On the **Basic Hoodie** page they asked "do you have this in M?", and the agent answered about the **Football tee** ("Sorry, size M is sold out in the Football Left Chest T-Shirt…"). The page context lived far away in the instructions, so the model followed the recent chat topic instead. The AI gateway (Portkey) also cached that wrong answer and replayed it in 0.2–0.4 s on every retry.

**What I added (`backend/agent.py`):**
1. **The product on screen is tagged on the live question.** The text sent to the model becomes `do you have this in M?\n[Shopper is viewing product now: basic-hoodie-big-yale (Basic Hoodie Big Yale)]`. The saved and visible message stays exactly what the shopper typed.
2. **Compact history replay:**
   - shopper messages are replayed word for word;
   - older assistant replies are trimmed to 320 characters (prices and stock are re-checked by tools anyway, so nothing factual is lost);
   - only the **most recent** showcase keeps its full numbered list, because that's the one "the third one on the page" refers to. Older ones collapse to `[Showcase on page 'Hoodies' (24 items, since replaced)]`.
3. **Usage meter:** one line per chat turn in the backend (uvicorn) terminal, for example:
   ```
   INFO:     chat turn guest | 4.3s | 2 model calls | tools: find_similar_products | tokens in 9,277 / out 207
   INFO:     chat turn guest | 3.9s | 2 model calls | tools: get_product_info | tokens in 9,057 / out 93
   ```

**How it helps:**
- **Shoppers:** "this" now means the item they're looking at, even right after a conversation about something else.
- **Business:** about 19% fewer input tokens per turn on a returning customer's chat, which means a lower AI bill. The meter makes cost and latency visible per turn, so slow or expensive turns can be spotted. In testing it caught one 25.5-second, 3-call turn and 9–15k tokens per message, which is why the system prompt is the next thing to slim down.

**Measured** (same 3 questions with the Test User's real saved history; `measure_tokens.py`, before → after):

| | Before | After |
|---|---|---|
| Replayed history (20 messages) | 6,955 characters | **2,937** (−58%) |
| Input tokens for 3 questions | 40,964 | **33,198** (−19%) |
| "do you have this in M?" on the Basic Hoodie page | ❌ answered about the Football tee | ✅ "Yes, size M is in stock, with 5 left…" (DB: M = 5) |
| "what did I ask you about on the t-shirt page?" | ✅ recalled | ✅ still recalled (memory not hurt by trimming) |

**Tests:** `tests/test_memory.py` checks that the live question carries the viewed-product tag while the saved message stays unchanged, and that the replayed history is compacted (user text intact, long assistant text trimmed).

---

## Summary of checks

- Backend: `cd hw4/backend && .venv/bin/pytest -q` → **51 passed** offline (8 live-model checks are opt-in with `RUN_LIVE_AGENT=1`).
- Frontend: `npm run build` and `npm run lint` are clean.
- Browser (headless Chrome against the running app): all four features were exercised as described above, with no console errors. Screenshots are in `output/screenshots/`.
