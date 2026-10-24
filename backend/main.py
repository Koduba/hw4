"""Campus Customs API.

Serves the product catalogue, stock levels, product photos, user accounts and
the shopping-assistant chat (a PydanticAI agent: agent.py, tools.py,
models.py, prompts/prompt.md) from data/campus_customs.db.

Run from hw4/backend (with the venv activated):
    uvicorn main:app --reload --port 8000
"""

import logging
import os
import re
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import agent
import auth
import db
import memory
import tools
from models import ChatMessage, ChatRequest, ChatResponse, CustomerContext, PageContext, Product

log = logging.getLogger("campus_customs")

# Each AI call costs money; cap how fast one account can send chat messages.
chat_by_user = auth.RateLimiter(limit=20, window_seconds=60)

# Browser origins allowed to call the API. Requests that change data must come
# from one of these (blocks cross-site request forgery from other websites).
ALLOWED_ORIGINS = os.getenv(
    "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_schema()
    yield


app = FastAPI(title="Campus Customs API", lifespan=lifespan)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # CSRF guard: data-changing requests must come from our own frontend.
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") not in ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Request origin not allowed."}, status_code=403)

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    return response


# The Vite dev server proxies /api and /media, so CORS is only a fallback for
# calling the API directly from the frontend's origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)

@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    # FastAPI's default 422 echoes the submitted values back, which would
    # include passwords. Return only which field failed and why.
    fields = [
        {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
        for e in exc.errors()
    ]
    return JSONResponse({"detail": "Please check the highlighted fields.", "fields": fields}, status_code=422)


app.mount("/media/products", StaticFiles(directory=db.IMAGES_DIR), name="product-images")
db.MODEL_SHOTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/models", StaticFiles(directory=db.MODEL_SHOTS_DIR), name="model-shots")
app.include_router(auth.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/products", response_model=list[Product])
def list_products() -> list[Product]:
    return tools.load_products()


@app.get("/api/products/{product_id}", response_model=Product)
def get_product(product_id: str) -> Product:
    products = tools.load_products([product_id])
    if not products:
        raise HTTPException(status_code=404, detail="Product not found")
    return products[0]


GUEST_COOKIE = "cc_guest"
GUEST_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")
guest_chat_by_ip = auth.RateLimiter(limit=60, window_seconds=60)  # stops cookie-cycling floods


def guest_id_for(request: Request, response: Response | None = None) -> str | None:
    """Existing guest id from the HttpOnly cc_guest cookie, or (if a response is given) a new one."""
    gid = request.cookies.get(GUEST_COOKIE)
    if gid and GUEST_ID_RE.match(gid):
        return gid
    if response is None:
        return None
    gid = secrets.token_urlsafe(18)
    response.set_cookie(
        GUEST_COOKIE, gid, max_age=memory.GUEST_TTL_SECONDS, httponly=True,
        secure=auth.COOKIE_SECURE, samesite="strict", path="/api",
    )
    return gid


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request, response: Response, user=Depends(auth.current_user)) -> ChatResponse:
    """One chat turn. Logged in: the customer comes from the session cookie and history is saved.
    Guest: allowed, remembered in server memory only (cc_guest cookie)."""
    page = body.page or PageContext()
    if body.current_product_id and not page.product_id:
        page = page.model_copy(update={"product_id": body.current_product_id})

    if user is not None:
        customer, guest_id, key = memory.customer_from_user(user), None, f"user:{user['id']}"
    else:
        ip = auth.client_ip(request)
        if wait := guest_chat_by_ip.blocked(ip):
            raise auth.too_many(wait)
        guest_chat_by_ip.hit(ip)
        guest_id = guest_id_for(request, response)
        customer, key = CustomerContext.guest(), f"guest:{guest_id}"

    if wait := chat_by_user.blocked(key):
        raise auth.too_many(wait)
    chat_by_user.hit(key)
    try:
        return await agent.run_chat(customer, body.message, page, guest_id)
    except Exception:
        # Log the details server-side; never send stack traces or keys to the browser.
        log.exception("chat failed for %s", key)
        raise HTTPException(503, "The assistant is having trouble right now. Please try again in a moment.")


@app.get("/api/chat/history", response_model=list[ChatMessage])
def chat_history(request: Request, user=Depends(auth.current_user)) -> list[ChatMessage]:
    """Logged in: saved history from the database. Guest: this visit's in-memory history (or none)."""
    if user is not None:
        return memory.load_history(user["id"])
    return memory.guest_memory.get(guest_id_for(request))


@app.delete("/api/chat/history", status_code=204)
def clear_chat_history(request: Request, user=Depends(auth.current_user)) -> None:
    if user is not None:
        memory.clear_history(user["id"])
    else:
        memory.guest_memory.clear(guest_id_for(request))
