"""Problem 12: append-only audit trail + safety guards.

    cd hw4/backend && .venv/bin/pytest -q tests/test_audit_safety.py
"""

import json
import shutil
import sqlite3
import sys
import threading
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
REAL_DB = BACKEND.parent / "data" / "campus_customs.db"
ORIGIN = {"Origin": "http://localhost:5173"}
TEST_USER = {"email": "test@campuscustoms.yale.edu", "password": "password"}
VISA_TEST = "4242 4242 4242 4242"  # public test card number (passes Luhn)


@pytest.fixture()
def env(tmp_path, monkeypatch):
    db_copy = tmp_path / "test.db"
    shutil.copy(REAL_DB, db_copy)
    monkeypatch.setenv("CAMPUS_DB_PATH", str(db_copy))
    monkeypatch.setenv("AUDIT_PATH", str(tmp_path / "audit_trail.json"))
    monkeypatch.setenv("PORTKEY_API_KEY", "test-key-not-used")
    sys.path.insert(0, str(BACKEND))
    for name, mod in list(sys.modules.items()):
        if getattr(mod, "__file__", None) and Path(mod.__file__).parent == BACKEND:
            sys.modules.pop(name, None)
    import agent
    import audit
    import main
    from fastapi.testclient import TestClient

    agent.build_agent.cache_clear()
    client = TestClient(main.app, headers=ORIGIN)
    assert client.post("/api/auth/login", json=TEST_USER).status_code == 200
    yield {"client": client, "agent": agent, "audit": audit, "trail": tmp_path / "audit_trail.json", "db": db_copy}
    agent.build_agent.cache_clear()


def run_chat(env, message, script, page=None):
    from pydantic_ai.models.function import FunctionModel

    with env["agent"].build_agent().override(model=FunctionModel(script)):
        return env["client"].post("/api/chat", json={"message": message, "page": page or {"path": "/"}})


def trail(env):
    return json.loads(env["trail"].read_text())


def stock_then_answer(reply):
    """check_stock(football tee, M) → final answer."""
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

    def script(messages, info):
        if not any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[ToolCallPart("check_stock", {"product": "football-left-chest-t-shirt", "size": "M"})])
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"reply": reply, "product_ids": []})])
    return script


# ---------- audit trail ----------

def test_trail_logs_the_agent_loop(env):
    r = run_chat(env, "do you have the football tee in M?", stock_then_answer("Sorry, size M is sold out."))
    assert r.status_code == 200
    entries = trail(env)
    assert [e["event"] for e in entries] == [
        "run_start", "model_response", "tool_call", "tool_result", "model_response", "tool_call", "tool_result", "run_end"]
    assert {e["run_id"] for e in entries} == {entries[0]["run_id"]}
    assert [e["step"] for e in entries] == list(range(1, 9))
    call = entries[2]
    assert call["tool_name"] == "check_stock" and "football-left-chest-t-shirt" in call["tool_args"]
    assert "SOLD OUT" in entries[3]["result_summary"]
    end = entries[-1]
    assert end["stop_reason"] == "final_result" and end["duration_ms"] >= 0 and "sold out" in end["detail"]
    assert all(e["who"] == "user:1" for e in entries)
    assert all(e["timestamp"].endswith("Z") for e in entries)
    text = env["trail"].read_text()
    assert "test@campuscustoms.yale.edu" not in text  # no emails in the trail
    assert all(len(e.get(k) or "") <= 240 for e in entries for k in ("message", "tool_args", "result_summary", "detail"))


def test_trail_is_append_only_across_runs(env):
    run_chat(env, "first", stock_then_answer("Sorry, size M is sold out."))
    first_bytes = env["trail"].read_bytes()
    run_chat(env, "second", stock_then_answer("Sorry, size M is sold out."))
    after = env["trail"].read_bytes()
    # Everything written by run 1 (minus its closing "]") is byte-for-byte unchanged.
    keep = first_bytes[: first_bytes.rfind(b"]")].rstrip()
    assert after.startswith(keep)
    entries = trail(env)
    assert len({e["run_id"] for e in entries}) == 2
    assert [e["message"] for e in entries if e["event"] == "run_start"] == ["first", "second"]


def test_trail_survives_concurrent_writers(env):
    audit = env["audit"]

    def write(i):
        run = audit.RunAudit(f"guest")
        run.add("run_start", message=f"msg {i}")
        run.add("run_end", stop_reason="final_result")
        run.write()

    threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    entries = trail(env)  # still one valid JSON array
    assert len(entries) == 40 and len({e["run_id"] for e in entries}) == 20


def test_validator_retry_is_logged(env):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, ToolReturnPart

    turns = []

    def script(messages, info):
        turns.append(1)
        if len(turns) == 1:
            return ModelResponse(parts=[ToolCallPart("check_stock", {"product": "basic-hoodie-big-yale", "size": "M"})])
        price = "$59" if len(turns) == 2 else "$68"
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"reply": f"It's {price}.", "product_ids": []})])

    assert run_chat(env, "price?", script).status_code == 200
    retries = [e for e in trail(env) if e["event"] == "retry"]
    assert retries and "$59" in retries[0]["result_summary"]
    assert trail(env)[-1]["stop_reason"] == "final_result"


def test_loop_limit_stop_reason_is_logged(env):
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    def endless(messages, info):  # never answers, keeps calling tools
        return ModelResponse(parts=[ToolCallPart("search_products", {"query": "hoodie"})])

    r = run_chat(env, "loop forever", endless)
    assert r.status_code == 503  # the shopper sees a polite error, not a hang
    end = trail(env)[-1]
    assert end["event"] == "run_end" and end["stop_reason"] == "usage_limit"
    assert sum(e["event"] == "model_response" for e in trail(env)) == env["agent"].LIMITS.request_limit


# ---------- safety guards ----------

def test_card_and_password_never_reach_model_db_or_trail(env):
    from pydantic_ai.messages import ModelResponse, ToolCallPart, UserPromptPart

    seen = []

    def script(messages, info):
        seen.extend(str(p.content) for m in messages for p in m.parts if isinstance(p, UserPromptPart))
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {
            "reply": "Please never share card numbers or passwords here; we never need them.", "product_ids": []})])

    msg = f"buy the hoodie, my card is {VISA_TEST} and my password is hunter2-secret"
    assert run_chat(env, msg, script).status_code == 200
    model_text = seen[-1]
    assert VISA_TEST not in model_text and "hunter2" not in model_text
    assert "[card number removed]" in model_text and "Safety note" in model_text
    with sqlite3.connect(env["db"]) as conn:
        saved = conn.execute("SELECT content FROM chat_messages WHERE user_id=1 AND role='user' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert VISA_TEST not in saved and "hunter2" not in saved
    text = env["trail"].read_text()
    assert VISA_TEST not in text and "hunter2" not in text and "card number, password" in text


def test_links_and_other_emails_are_rewritten(env):
    from pydantic_ai.messages import ModelResponse, ToolCallPart

    replies = iter([
        "See https://evil.example/deal for more.",
        "Email tauhid.zaman@yale.edu for help.",
        "Visit us at 57 Broadway, or tap a card for details.",
    ])

    def script(messages, info):
        return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, {"reply": next(replies), "product_ids": []})])

    body = run_chat(env, "help", script).json()
    assert body["reply"] == "Visit us at 57 Broadway, or tap a card for details."
    assert sum(e["event"] == "retry" for e in trail(env)) == 2


def test_redact_input_unit():
    sys.path.insert(0, str(BACKEND))
    import safety

    clean, removed = safety.redact_input(f"card {VISA_TEST}, ssn 123-45-6789, pw: abc123")
    assert removed == ["card number", "social security number", "password"]
    assert VISA_TEST not in clean and "123-45-6789" not in clean and "abc123" not in clean
    # Ordinary numbers (prices, years, sizes) are left alone.
    assert safety.redact_input("under $60 in 2025, size M, 2 shirts")[1] == []
    assert safety.reply_problem("Your account is test@campuscustoms.yale.edu.", "test@campuscustoms.yale.edu") is None
