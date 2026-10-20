"""Personal web chat: same-origin UI, password login and persistent LangGraph threads."""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from chatbot import build_graph
from personalization import MAX_PREFERENCES_BYTES, get_preferences, initialize_preferences, update_preferences

ROOT = Path(__file__).resolve().parent
COOKIE = "chatbot_session"
SESSION_SECONDS = 7 * 24 * 60 * 60
logger = logging.getLogger(__name__)


def text_content(content) -> str:
    if isinstance(content, str):
        return content
    return "".join(
        block if isinstance(block, str) else block.get("text", "")
        for block in content
        if isinstance(block, (str, dict))
    )


def signed_session(secret: bytes) -> str:
    payload = f"{int(time.time()) + SESSION_SECONDS}.{secrets.token_hex(16)}"
    signature = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{signature}"


def authenticated(request: Request) -> bool:
    token = request.cookies.get(COOKIE, "")
    try:
        expires, nonce, signature = token.split(".")
        payload = f"{expires}.{nonce}"
        expected = hmac.new(request.app.state.session_secret, payload.encode(), hashlib.sha256).hexdigest()
        return int(expires) > time.time() and hmac.compare_digest(signature, expected)
    except (ValueError, AttributeError):
        return False


def require_login(request: Request):
    if not authenticated(request):
        raise HTTPException(401, "请先输入访问密码。")


async def read_json(request: Request, *, max_bytes=65536) -> dict:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > max_bytes:
            raise HTTPException(413, "内容太大了，请缩小图片或分次发送消息。")
    try:
        value = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(400, "无法读取这条请求，请重试。")
    if not isinstance(value, dict):
        raise HTTPException(400, "无法读取这条请求，请重试。")
    return value


class WebHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD", "OPTIONS") and origin:
            if urlsplit(origin).netloc != request.headers.get("host"):
                return JSONResponse({"detail": "请从聊天页面重新发送。"}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data: blob:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response


async def index(request):
    def render_page():
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        # Match HTML to its current assets even when a browser cached older files.
        for filename in ("style.css", "app.js"):
            version = hashlib.sha256((ROOT / "web" / filename).read_bytes()).hexdigest()[:12]
            page = page.replace(f"/static/{filename}", f"/static/{filename}?v={version}")
        return page
    return HTMLResponse(await asyncio.to_thread(render_page), headers={"Cache-Control": "no-cache"})


async def session(request):
    return JSONResponse({"authenticated": authenticated(request)})


async def login(request):
    data = await read_json(request)
    password = data.get("password", "")
    ip = request.client.host if request.client else "local"
    failures = request.app.state.login_failures
    now = time.monotonic()
    # Expire old entries, so unused client addresses do not accumulate forever.
    for address in list(failures):
        while failures[address] and now - failures[address][0] > 300:
            failures[address].popleft()
        if not failures[address]:
            del failures[address]
    if len(failures.get(ip, ())) >= 8:
        raise HTTPException(429, "尝试次数有点多，请五分钟后再试。")
    if not isinstance(password, str) or not hmac.compare_digest(
        password.encode(), request.app.state.password.encode()
    ):
        failures[ip].append(now)
        raise HTTPException(401, "密码不太对，再试一次吧。")
    failures.pop(ip, None)
    response = JSONResponse({"ok": True})
    response.set_cookie(
        COOKIE,
        signed_session(request.app.state.session_secret),
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=request.app.state.cookie_secure,
        samesite="strict",
        path="/",
    )
    return response


async def logout(request):
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, path="/")
    return response


async def preferences(request):
    require_login(request)
    if request.method == "GET":
        return JSONResponse(await get_preferences(request.app.state.db))
    data = await read_json(request, max_bytes=MAX_PREFERENCES_BYTES)
    async with request.app.state.preferences_lock:
        values = await update_preferences(request.app.state.db, data)
    return JSONResponse(values)


async def background_image(request):
    require_login(request)
    async with request.app.state.db.execute("SELECT background, mime FROM preferences WHERE id = 1") as cursor:
        row = await cursor.fetchone()
    if not row or row[0] is None:
        raise HTTPException(404, "还没有设置背景图片。")
    return Response(row[0], media_type=row[1])


async def conversation_row(request):
    async with request.app.state.db.execute(
        "SELECT id, title, updated_at FROM conversations WHERE id = ?",
        (request.path_params["conversation_id"],),
    ) as cursor:
        row = await cursor.fetchone()
    if row is None:
        raise HTTPException(404, "这段对话已经不在了。")
    return dict(row)


async def conversations(request):
    require_login(request)
    db = request.app.state.db
    if request.method == "POST":
        row = {"id": str(uuid4()), "title": "新的对话", "updated_at": time.time()}
        await db.execute(
            "INSERT INTO conversations (id, title, updated_at) VALUES (?, ?, ?)",
            (row["id"], row["title"], row["updated_at"]),
        )
        await db.commit()
        return JSONResponse(row, status_code=201)
    async with db.execute("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC") as cursor:
        rows = [dict(row) for row in await cursor.fetchall()]
    return JSONResponse(rows)


async def conversation(request):
    require_login(request)
    row = await conversation_row(request)
    lock = request.app.state.locks[row["id"]]
    if request.method == "DELETE":
        if lock.locked():
            raise HTTPException(409, "请先等这条回复结束，再删除对话。")
        async with lock:
            await request.app.state.saver.adelete_thread(row["id"])
            await request.app.state.db.execute("DELETE FROM conversations WHERE id = ?", (row["id"],))
            await request.app.state.db.commit()
        return JSONResponse({"ok": True})
    snapshot = await request.app.state.graph.aget_state({"configurable": {"thread_id": row["id"]}})
    messages = [
        {"role": "user" if message.type == "human" else "assistant", "content": text_content(message.content)}
        for message in snapshot.values.get("messages", [])
        if message.type in ("human", "ai")
    ]
    return JSONResponse({**row, "messages": messages})


def event(name: str, data: dict) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def send_message(request):
    require_login(request)
    row = await conversation_row(request)
    data = await read_json(request)
    content = data.get("content")
    if not isinstance(content, str) or not content.strip():
        raise HTTPException(400, "先写点什么，再发给我吧。")
    content = content.strip()
    if len(content) > 12000:
        raise HTTPException(400, "这条消息太长了，请分几次发送。")
    lock = request.app.state.locks[row["id"]]
    if lock.locked():
        raise HTTPException(409, "上一条回复还没结束，请稍等一下。")
    # Acquire before returning the response; concurrent sends cannot start two runs.
    await lock.acquire()
    try:
        # Another device may have deleted the conversation while its body was read.
        await conversation_row(request)
    except BaseException:
        lock.release()
        raise

    async def stream():
        try:
            graph = request.app.state.graph
            appearance = await get_preferences(request.app.state.db)
            config = {"configurable": {
                "thread_id": row["id"],
                "companion_name": appearance["companion_name"],
            }}
            title = row["title"]
            if title == "新的对话":
                title = content.replace("\n", " ")[:26]
            await request.app.state.db.execute(
                "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
                (title, time.time(), row["id"]),
            )
            await request.app.state.db.commit()
            yield event("meta", {"id": row["id"], "title": title})
            async for chunk, metadata in graph.astream(
                {"messages": [{"role": "user", "content": content}]},
                config=config,
                stream_mode="messages",
            ):
                if metadata.get("langgraph_node") == "chatbot":
                    text = text_content(chunk.content)
                    if text:
                        yield event("delta", {"text": text})
            # The authoritative reply comes from the completed checkpoint.
            snapshot = await graph.aget_state(config)
            messages = snapshot.values.get("messages", [])
            reply = text_content(messages[-1].content) if messages and messages[-1].type == "ai" else ""
            yield event("done", {"content": reply})
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Chat run failed for thread %s", row["id"])
            yield event("error", {"detail": "这次回复暂时中断了，请稍后再试。"})
        finally:
            lock.release()

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def http_error(request, exc):
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


def create_app(*, data_dir: Path | None = None, password: str | None = None):
    password = password if password is not None else os.getenv("CHAT_PASSWORD", "")
    if len(password) < 8:
        raise ValueError("Set CHAT_PASSWORD in .env to a password with at least 8 characters before starting the web app.")
    configured_dir = Path(os.getenv("CHAT_DATA_DIR", "data/web"))
    storage = Path(data_dir) if data_dir is not None else configured_dir
    if not storage.is_absolute():
        storage = ROOT / storage

    @asynccontextmanager
    async def lifespan(app):
        storage.mkdir(parents=True, exist_ok=True)
        key_file = storage / "session.key"
        try:
            descriptor = os.open(key_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(descriptor, "wb") as file:
                file.write(secrets.token_bytes(32))
        app.state.session_secret = hmac.new(key_file.read_bytes(), password.encode(), hashlib.sha256).digest()
        app.state.password = password
        app.state.cookie_secure = os.getenv("CHAT_COOKIE_SECURE", "false").lower() == "true"
        app.state.locks = defaultdict(asyncio.Lock)
        app.state.login_failures = defaultdict(deque)
        app.state.preferences_lock = asyncio.Lock()
        async with aiosqlite.connect(storage / "conversations.sqlite") as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA journal_mode=WAL")
            await db.execute("CREATE TABLE IF NOT EXISTS conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at REAL NOT NULL)")
            await initialize_preferences(db)
            await db.commit()
            async with AsyncSqliteSaver.from_conn_string(str(storage / "checkpoints.sqlite")) as saver:
                app.state.db = db
                app.state.saver = saver
                app.state.graph = build_graph(async_model=True).compile(checkpointer=saver)
                yield

    return Starlette(
        routes=[
            Route("/", index),
            Route("/health", lambda request: JSONResponse({"status": "ok"})),
            Route("/api/session", session),
            Route("/api/login", login, methods=["POST"]),
            Route("/api/logout", logout, methods=["POST"]),
            Route("/api/preferences", preferences, methods=["GET", "PUT"]),
            Route("/api/preferences/background", background_image),
            Route("/api/conversations", conversations, methods=["GET", "POST"]),
            Route("/api/conversations/{conversation_id}", conversation, methods=["GET", "DELETE"]),
            Route("/api/conversations/{conversation_id}/messages", send_message, methods=["POST"]),
            Mount("/static", StaticFiles(directory=ROOT / "web"), name="static"),
        ],
        middleware=[Middleware(WebHeaders)],
        exception_handlers={HTTPException: http_error},
        lifespan=lifespan,
    )


app = create_app()
