# Campus Customs Database Report

Source: `data/campus_customs.db` (SQLite) plus 102 product photos in `data/products/`.

## 1. Schema at a glance

| Table | Rows | Purpose | Key |
|---|---|---|---|
| `catalogue` | 102 | One row per product: what it is, how it looks, what it costs | `product_id` (text slug, e.g. `basic-hoodie-big-yale`) |
| `inventory` | 612 | Stock count per product per size | `UNIQUE(product_id, size)`, FK → `catalogue` |
| `users` | 3 | Shopper accounts for the chat app | `email` is unique |
| `chat_messages` | 22 | Saved chat history per user, including products shown | FK `user_id` → `users` |

How they connect:

```
users 1 ──< chat_messages        (user_id)
catalogue 1 ──< inventory        (product_id, 6 sizes each)
chat_messages.products_json  →  snapshot of catalogue + inventory rows shown in a reply
```

## 2. Catalogue

**Columns:** `product_id`, `name`, `garment_type`, `description`, `colors` (JSON list), `search_tags` (JSON list), `image_file_path`, `price`.

- **102 products, and every one has a matching photo.** Each `image_file_path` (`products/<product_id>.jpg`) points to a file that exists, and there are no extra photos without a catalogue row.
- The descriptions, colours and tags look AI-generated from the photos, like the HW3 catalogue build. Each one is a single descriptive sentence, with 4–12 search tags per product (about 9 on average).
- **Range:** Yale apparel only, with no shorts, hats or accessories. It covers residential colleges (Branford, Saybrook, Morse, Grace Hopper, etc.), professional schools (SOM, Law, Medicine, Art, Music, Divinity…), varsity sports, "family" items (Yale Mom, Dad, Grandpa, Aunt…), and branded lines (Champion, Under Armour, Brooks Brothers, District, Hype and Vice).
- **Colours:** mostly heather gray (41 primary) and navy / navy blue (44 primary).

### Prices: 7 price points, set by garment family

| Price | Products | Garment family |
|---|---|---|
| $32 | 25 | T-shirts |
| $45 | 5 | Performance long-sleeves, mockneck, two sale hoodies |
| $58 | 28 | Crewneck sweatshirts |
| $68 | 23 | Pullover hoodies |
| $72 | 11 | Quarter-zips |
| $88 | 2 | Full-zip hoodies |
| $98 | 8 | Fleece / bomber jackets |

Average price is $58.48.

### Data-quality issues worth knowing before you build on it

1. **`garment_type` is not standardised.** There are 22 distinct values for about 8 real categories. Examples: `short-sleeve t-shirt` / `short-sleeve T-shirt` / `t-shirt`, `pullover hoodie` / `hoodie` / `hooded sweatshirt`, and `quarter-zip pullover` / `quarter-zip pullover sweatshirt`. Filtering with `garment_type = 'hoodie'` would miss most hoodies.
2. **Three products have an empty `colors` list:** `benjamin-franklin-t-shirt`, `berkeley-sweater-fleece-jacket` and `timothy-dwight-college-crewneck`.
3. **Colour names vary:** `navy` vs `navy blue`, and `gray` vs `heather gray` vs `charcoal gray`.
4. **One price stands out:** `yale-sports-hoodie-tennis` is $45, while its six sibling sports hoodies are $68.
5. **Mascot search gap:** no row mentions "Handsome Dan" (Yale's bulldog mascot), although 10 rows mention "bulldog". A keyword-only search misses that link.

## 3. Inventory

**Columns:** `id`, `product_id`, `size`, `quantity`.

- **Complete grid:** all 102 products have exactly 6 sizes (XS, S, M, L, XL, XXL), giving 612 rows. No inventory row points to a product that doesn't exist.
- **5,920 units on hand**, worth about **$344K at retail**. Quantities run from 0 to 25 per size, averaging 9.7.
- **Stockouts:** 145 of 612 size rows (24%) are at 0. Another 115 (19%) are low, at 1–5 units. Stockouts are spread evenly across sizes, so no single size is short.
- No product is fully out of stock, but **21 products are out in 3 or more sizes**. The thinnest are:

| Product | Units left | Sizes at 0 |
|---|---|---|
| football-left-chest-t-shirt | 9 | 3 |
| tri-blend-sports-hockey-t-shirt | 13 | 4 |
| t-felt-y-heavyweight | 14 | 4 |
| soccer-left-chest-crewneck | 17 | 4 |
| champion-reverse-weave-crewneck | 24 | 4 |

- **Deepest stock:** tri-blend-sports-football-t-shirt (116), 2025-yale-vs-harvard-t-shirt (112), branford-1-4-zip (95).
- By retail value, crewnecks (~$86K) and pullover hoodies (~$71K) are the biggest categories.

## 4. Users

**Columns:** `id`, `name`, `first_name`, `last_name`, `email`, `password_hash`, `created_at`.

| id | Name | Email | Created | Chat messages |
|---|---|---|---|---|
| 1 | Test User | test@campuscustoms.yale.edu | 2026-09-19 11:34 | 6 |
| 2 | Ada Lovelace | ada.1789818990@yale.edu | 2026-09-19 11:56 | 0 |
| 3 | Tauhid Zaman | tauhid.zaman@yale.edu | 2026-09-19 11:57 | 16 |

- **Passwords are hashed, not stored in plain text.** They use PBKDF2 (`pbkdf2_…` prefix, about 95 characters). This report does not show any hash values.
- `first_name` and `last_name` were added after the table was created (via `ALTER TABLE`), alongside the original `name` field. The assistant uses the first name to personalise replies ("Hey Tauhid!").
- Ada's email has a numeric suffix, so it looks like an auto-generated test sign-up.

## 5. Chat messages

**Columns:** `id`, `user_id`, `role` (`user` / `assistant`), `content` (markdown), `products_json`, `created_at`.

- There are 22 messages: 11 user and assistant pairs, all from 2026-09-19.
- When the assistant recommends products, `products_json` holds a **full snapshot of each product**: the catalogue fields plus an `image_url` (`/media/products/...`) and that product's `inventory` list by size. The app evidently renders product cards from it. Replies with no products store `[]`. User messages store `NULL`.
- The history shows how the existing assistant behaves:
  - **Remembers the user:** "do you remember me? What's my name?" → "Hi, Test!"
  - **Refers back to a product:** "you have this in pink?" gets an answer about a specific crewneck, so a selected or previously shown item is passed in as context.
  - **Handles out-of-range requests:** "gym shorts" → no match, and it offers alternatives.
  - **Misses on search:** "Handsome Dan" returns nothing, even though bulldog products exist (see catalogue issue 5).
  - **Inconsistent answer:** for "cheapest fleece", the text names a $72 quarter-zip, but the attached product cards are the $98 fleece jackets.

## 6. Takeaways for HW4

- The data supports a **shopping-assistant chat app**: search the catalogue, check stock by size, log users in and save their chat history.
- Before relying on filters, **normalise `garment_type` and colours**, or search over description and tags rather than exact category matches.
- Answers about availability should read the **live `inventory` table**. The snapshot in `products_json` goes stale.
- Search needs synonyms or semantic matching (Handsome Dan → bulldog, fleece vs. quarter-zip). Those are the misses in the existing chat log.
