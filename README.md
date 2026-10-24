# Campus Customs: Yale apparel shop with an AI shopping assistant

HW4, AI in Management (Yale SOM). A full-stack storefront for **Campus Customs** (Yale gear, 57 Broadway, New Haven) with **"Ask the Bulldog"**, a PydanticAI agent that checks live stock and prices from the database, lays out matching products on the page, remembers logged-in customers, and follows code-enforced safety rules.

- **Frontend:** React + Vite + TypeScript (`frontend/`), in Yale Blue
- **Backend:** FastAPI + PydanticAI (`backend/`), model `gpt-5.6-luna` via Portkey
- **Data:** SQLite `campus_customs.db` (catalogue, inventory, users, chat history). **Not in this repo** (see Setup).

## Project layout

```
hw4/
├── AI_prompts.md            # my prompts for each problem
├── requirements.txt         # backend Python dependencies
├── .env.example             # variable names with placeholders only
├── .gitignore
├── README.md
├── frontend/                # Vite React TypeScript app
├── backend/
│   ├── main.py              # FastAPI app — run with: uvicorn main:app --reload --port 8000
│   ├── agent.py             # PydanticAI agent wiring, run_chat()
│   ├── models.py            # Pydantic / PydanticAI types
│   ├── tools.py             # tools the agent can call
│   ├── prompts/
│   │   └── prompt.md        # system prompt (voice, tools, safety rules)
│   ├── auth.py · db.py · memory.py · safety.py · audit.py
│   └── tests/               # pytest suite
└── output/
    ├── harness.md           # how the system works (models, tools, safety, specs)
    ├── design.md            # visual design write-up
    ├── usability.md         # Problem 9 improvements
    ├── app_check.html       # live-site test page (double-click to open)
    ├── app_check_images/    # screenshots linked from app_check.html
    └── audit_trail.json     # append-only agent loop log
```

The agent itself is four files under `backend/`: `prompts/prompt.md`, `agent.py`, `tools.py` and `models.py`. The other backend modules support the app (accounts, database access, chat memory, safety guards, audit trail).

## Setup

1. **Local-only data pack (not in git):** create `hw4/data/` with the course materials laid out like this:

   ```
   data/
   ├── campus_customs.db
   └── products/              # images referenced by the catalogue
   ```

   Then follow the steps below to run the backend and frontend.
2. **Secrets:** `cp .env.example .env`, then set `PORTKEY_API_KEY` in `.env`. `.env` is git-ignored; never commit real keys.
3. **Install:**
   ```bash
   python3.12 -m venv backend/.venv
   backend/.venv/bin/pip install -r requirements.txt
   cd frontend && npm install
   ```

## Run

```bash
# Terminal 1: backend
cd backend && source .venv/bin/activate && uvicorn main:app --reload --port 8000

# Terminal 2: frontend
cd frontend && npm run dev        # open http://localhost:5173
```

Test log-in (seed database): `test@campuscustoms.yale.edu` / `password`. Guests can chat too.

## Tests

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest -q                                        # 59 offline tests (scripted model, temp DB copy)
RUN_LIVE_AGENT=1 .venv/bin/pytest -q tests/test_live_agent.py   # optional: real model
```

## Where to look

- **How it works:** [`output/harness.md`](output/harness.md). Part A covers models, tools, safety rules, specs and the audit trail.
- **Live-site checks:** [`output/app_check.html`](output/app_check.html)
- **Design / usability:** [`output/design.md`](output/design.md), [`output/usability.md`](output/usability.md)
- **Database analysis (Problem 2):** [`output/database_report.md`](output/database_report.md)
