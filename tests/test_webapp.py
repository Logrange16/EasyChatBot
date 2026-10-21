"""Integration tests use a local fake model; no paid requests or real keys."""

import asyncio
import base64
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

# Override credentials before loading the application or its .env configuration.
os.environ["QWEN_API_KEY"] = "local-test-only"
os.environ["QWEN_BASE_URL"] = "https://example.invalid/v1"
os.environ["TAVILY_API_KEY"] = ""
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["CHAT_PASSWORD"] = "test-password-123"
os.environ["CHAT_COOKIE_SECURE"] = "false"

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.tools import tool
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.testclient import TestClient
from PIL import Image

import chatbot
import assistant
import agent_runtime
import webapp
from webapp import COOKIE, create_app


@tool
def offline_search(query: str) -> str:
    """Return an offline source for integration tests."""
    return "本地检索资料：" + query


class LocalModel(BaseChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    @property
    def _llm_type(self):
        return "offline-test"

    def reply(self, messages):
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content.startswith((chatbot.DEFAULT_SYSTEM_PROMPT, assistant.TOOL_SYSTEM_PROMPT))
        if messages[-1].type == "tool":
            return "根据工具资料回答：" + messages[-1].content
        humans = [m.content for m in messages if m.type == "human"]
        if humans[-1] == "fail":
            raise RuntimeError("private-provider-error-do-not-expose")
        return "你好，我记得：" + "；".join(humans)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply(messages)))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        if messages[-1].type == "human" and messages[-1].content.startswith("search:"):
            yield ChatGenerationChunk(message=AIMessageChunk(
                content="", tool_call_chunks=[{
                    "name": "offline_search", "args": json.dumps({"query": messages[-1].content[7:]}),
                    "id": "offline-search-call", "index": 0,
                }],
            ))
            return
        for character in self.reply(messages):
            yield ChatGenerationChunk(message=AIMessageChunk(content=character))


def events(response):
    result = []
    for frame in response.text.strip().split("\n\n"):
        if not frame:
            continue
        lines = frame.splitlines()
        result.append((lines[0][7:], json.loads(lines[1][6:])))
    return result


class WebAppTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / ".tmp"
        temp_root.mkdir(exist_ok=True)
        self.directory = tempfile.TemporaryDirectory(dir=temp_root)
        self.storage = Path(self.directory.name)
        self.model_patch = patch.object(agent_runtime, "llm", LocalModel())
        self.model_patch.start()
        self.companion_tools_patch = patch.object(chatbot, "tools", [offline_search])
        self.assistant_tools_patch = patch.object(assistant, "tools", [offline_search])
        self.companion_tools_patch.start()
        self.assistant_tools_patch.start()
        self.app = create_app(data_dir=self.storage)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.model_patch.stop()
        self.companion_tools_patch.stop()
        self.assistant_tools_patch.stop()
        self.directory.cleanup()

    def login(self):
        response = self.client.post("/api/login", json={"password": "test-password-123"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])

    def new_chat(self, mode="companion"):
        response = self.client.post("/api/conversations", json={"mode": mode})
        self.assertEqual(response.status_code, 201)
        return response.json()["id"]

    def send(self, thread, content):
        return self.client.post(f"/api/conversations/{thread}/messages", json={"content": content})

    def test_login_cookie_logout_and_static_assets(self):
        self.assertEqual(self.client.get("/api/conversations").status_code, 401)
        self.assertFalse(self.client.get("/api/session").json()["authenticated"])
        self.assertEqual(self.client.post("/api/login", json={"password": "wrong"}).status_code, 401)
        self.login()
        self.assertTrue(self.client.get("/api/session").json()["authenticated"])
        for path in ("/", "/static/app.js", "/static/style.css", "/static/icon.svg"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        self.client.post("/api/logout")
        self.assertEqual(self.client.get("/api/conversations").status_code, 401)

    def test_context_streaming_and_thread_isolation(self):
        self.login()
        thread = self.new_chat()
        first = events(self.send(thread, "暗号是蓝色风铃"))
        self.assertEqual(first[0][0], "meta")
        self.assertTrue(any(kind == "delta" for kind, _ in first))
        self.assertEqual(first[-1][0], "done")
        second = events(self.send(thread, "暗号是什么？"))
        self.assertIn("暗号是蓝色风铃", second[-1][1]["content"])
        saved = self.client.get(f"/api/conversations/{thread}").json()
        self.assertEqual([m["role"] for m in saved["messages"]], ["user", "assistant", "user", "assistant"])
        other = self.new_chat()
        isolated = events(self.send(other, "你好"))
        self.assertNotIn("蓝色风铃", isolated[-1][1]["content"])

    def test_modes_use_separate_graphs_prompts_and_conversation_history(self):
        self.login()
        self.assertIsNot(self.app.state.graphs["companion"], self.app.state.graphs["assistant"])
        companion = self.new_chat()
        research = self.new_chat("assistant")
        captured = []
        original = LocalModel.reply
        def capture(model, messages):
            captured.append(messages[0].content)
            return original(model, messages)
        with patch.object(LocalModel, "reply", capture):
            self.send(companion, "陪伴会话的暗号")
            answer = events(self.send(research, "助手的研究问题"))
        self.assertTrue(captured[0].startswith(chatbot.DEFAULT_SYSTEM_PROMPT))
        self.assertNotIn(assistant.TOOL_SYSTEM_PROMPT, captured[0])
        self.assertTrue(captured[1].startswith(assistant.TOOL_SYSTEM_PROMPT))
        self.assertNotIn(chatbot.DEFAULT_SYSTEM_PROMPT, captured[1])
        self.assertNotIn("陪伴会话的暗号", answer[-1][1]["content"])
        for thread, mode in ((companion, "companion"), (research, "assistant")):
            self.assertEqual(self.client.get(f"/api/conversations/{thread}").json()["mode"], mode)
        rows = self.client.get("/api/conversations").json()
        self.assertEqual({row["mode"] for row in rows}, {"companion", "assistant"})
        # Mode is fixed at creation; a send cannot redirect an existing thread.
        response = self.client.post(f"/api/conversations/{research}/messages", json={"content": "继续研究", "mode": "companion"})
        self.assertEqual(events(response)[-1][0], "done")
        self.assertEqual(self.client.get(f"/api/conversations/{research}").json()["mode"], "assistant")

    def test_tool_roundtrip_and_visible_history_in_both_modes(self):
        self.login()
        for mode in ("companion", "assistant"):
            with self.subTest(mode=mode):
                thread = self.new_chat(mode)
                reply = events(self.send(thread, "search:验证工具闭环"))
                self.assertTrue(any(kind == "status" for kind, _ in reply))
                self.assertEqual(reply[-1], ("done", {"content": "根据工具资料回答：本地检索资料：验证工具闭环"}))
                saved = self.client.get(f"/api/conversations/{thread}").json()
                self.assertEqual([m["role"] for m in saved["messages"]], ["user", "assistant"])
                self.assertEqual(saved["messages"][-1]["content"], reply[-1][1]["content"])

    def test_mode_validation_and_default_for_older_clients(self):
        self.login()
        for mode in ("unknown", None, [], {}):
            self.assertEqual(self.client.post("/api/conversations", json={"mode": mode}).status_code, 400)
        self.assertEqual(self.client.post("/api/conversations").json()["mode"], "companion")

    def test_legacy_conversation_database_migrates_without_losing_rows(self):
        legacy_storage = self.storage / "legacy"
        legacy_storage.mkdir()
        with closing(sqlite3.connect(legacy_storage / "conversations.sqlite")) as db:
            db.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, title TEXT NOT NULL, updated_at REAL NOT NULL)")
            db.execute("INSERT INTO conversations VALUES ('legacy-thread', '已有对话', 123)")
            db.commit()
        with TestClient(create_app(data_dir=legacy_storage)) as client:
            client.post("/api/login", json={"password": "test-password-123"})
            self.assertEqual(client.get("/api/conversations").json(), [
                {"id": "legacy-thread", "title": "已有对话", "updated_at": 123.0, "mode": "companion"},
            ])

    def test_frontend_asset_urls_refresh_when_source_changes(self):
        # An old cached script must not be reused with a newer page layout.
        source = self.storage / "asset-preview"
        web = source / "web"
        web.mkdir(parents=True)
        (web / "index.html").write_text('<link href="/static/style.css"><script src="/static/app.js"></script>', encoding="utf-8")
        (web / "style.css").write_text("body {color: black}", encoding="utf-8")
        (web / "app.js").write_text("console.log('first')", encoding="utf-8")
        def asset_urls():
            response = self.client.get("/")
            self.assertEqual(response.headers["cache-control"], "no-cache")
            return re.findall(r'/static/[^" ]+', response.text)
        with patch.object(webapp, "ROOT", source):
            first = asset_urls()
            self.assertEqual(first, asset_urls())
            self.assertTrue(all("?v=" in url for url in first))
            (web / "app.js").write_text("console.log('updated settings')", encoding="utf-8")
            updated = asset_urls()
            self.assertEqual(first[0], updated[0])
            self.assertNotEqual(first[1], updated[1])
        for url in asset_urls():
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-cache")

    def test_restart_restores_history_and_login(self):
        self.login()
        thread = self.new_chat()
        self.send(thread, "重启前的消息")
        cookie = self.client.cookies.get(COOKIE)
        self.client.__exit__(None, None, None)
        self.app = create_app(data_dir=self.storage)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.client.cookies.set(COOKIE, cookie)
        self.assertTrue(self.client.get("/api/session").json()["authenticated"])
        saved = self.client.get(f"/api/conversations/{thread}").json()
        self.assertEqual(len(saved["messages"]), 2)
        reply = events(self.send(thread, "重启后继续"))
        self.assertIn("重启前的消息", reply[-1][1]["content"])

    def test_assistant_mode_and_history_survive_restart_without_companion_nickname(self):
        self.login()
        self.client.put("/api/preferences", json={"companion_name": "小岚"})
        thread = self.new_chat("assistant")
        self.send(thread, "助手历史")
        self.client.__exit__(None, None, None)
        self.app = create_app(data_dir=self.storage)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.login()
        saved = self.client.get(f"/api/conversations/{thread}").json()
        self.assertEqual(saved["mode"], "assistant")
        self.assertEqual(len(saved["messages"]), 2)
        captured = []
        original = LocalModel.reply
        def capture(model, messages):
            captured.append(messages[0].content)
            return original(model, messages)
        with patch.object(LocalModel, "reply", capture):
            reply = events(self.send(thread, "继续研究"))
        self.assertIn("助手历史", reply[-1][1]["content"])
        self.assertNotIn("小岚", captured[0])

    def test_delete_removes_conversation_and_checkpoints(self):
        self.login()
        thread = self.new_chat()
        self.send(thread, "之后会删除这条消息")
        self.assertEqual(self.client.delete(f"/api/conversations/{thread}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/conversations/{thread}").status_code, 404)
        self.assertEqual(self.client.get("/api/conversations").json(), [])
        async def checkpoint_is_absent():
            async with AsyncSqliteSaver.from_conn_string(str(self.storage / "checkpoints.sqlite")) as saver:
                return await saver.aget_tuple({"configurable": {"thread_id": thread}}) is None
        self.assertTrue(asyncio.run(checkpoint_is_absent()))

    def test_validation_origin_and_tampered_cookie(self):
        self.assertEqual(self.client.post("/api/login", json={"password": "test-password-123"}, headers={"Origin": "https://unrelated.invalid"}).status_code, 403)
        self.login()
        thread = self.new_chat()
        self.assertEqual(self.send(thread, " ").status_code, 400)
        self.assertEqual(self.send(thread, "a" * 12001).status_code, 400)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE, "9999999999.fake.invalid")
        self.assertEqual(self.client.get("/api/conversations").status_code, 401)

    def test_model_error_is_sanitized_and_releases_thread(self):
        self.login()
        thread = self.new_chat()
        with self.assertLogs("webapp", level="ERROR"):
            response = self.send(thread, "fail")
        self.assertEqual(events(response)[-1][0], "error")
        self.assertNotIn("private-provider-error", response.text)
        self.assertFalse(self.app.state.locks[thread].locked())
        self.assertEqual(events(self.send(thread, "恢复聊天"))[-1][0], "done")

    def test_login_rate_limit_and_password_change(self):
        for _ in range(8):
            self.assertEqual(self.client.post("/api/login", json={"password": "wrong"}).status_code, 401)
        self.assertEqual(self.client.post("/api/login", json={"password": "wrong"}).status_code, 429)
        with self.assertRaisesRegex(ValueError, "CHAT_PASSWORD"):
            create_app(data_dir=self.storage, password="short")

    def test_busy_conversation_rejects_send_and_delete(self):
        self.login()
        thread = self.new_chat()
        lock = self.app.state.locks[thread]
        self.client.portal.call(lock.acquire)
        try:
            self.assertEqual(self.send(thread, "第二个设备的消息").status_code, 409)
            self.assertEqual(self.client.delete(f"/api/conversations/{thread}").status_code, 409)
        finally:
            self.client.portal.call(lock.release)
        self.assertEqual(events(self.send(thread, "现在可以继续"))[-1][0], "done")

    @staticmethod
    def image_data(image_format="PNG", size=(32, 24)):
        output = io.BytesIO()
        Image.new("RGB", size, "#b8a6d9").save(output, format=image_format)
        content = output.getvalue()
        return "data:image/png;base64," + base64.b64encode(content).decode(), content

    def test_preferences_and_background_require_login(self):
        self.assertEqual(self.client.get("/api/preferences").status_code, 401)
        self.assertEqual(self.client.put("/api/preferences", json={"theme": "pink"}).status_code, 401)
        self.assertEqual(self.client.get("/api/preferences/background").status_code, 401)
        self.login()
        defaults = self.client.get("/api/preferences").json()
        self.assertNotIn("app_name", defaults)
        self.assertEqual(defaults["companion_name"], "你的聊天伙伴")
        self.assertEqual(defaults["theme"], "lavender")
        self.assertIsNone(defaults["background_url"])

    def test_preferences_and_png_persist_across_restart_and_devices(self):
        self.login()
        image, content = self.image_data()
        updated = self.client.put("/api/preferences", json={
            "companion_name": "  小岚  ", "theme": "pink",
            "background_opacity": 45, "background_image": image,
        })
        self.assertEqual(updated.status_code, 200)
        saved = updated.json()
        self.assertEqual(saved["companion_name"], "小岚")
        self.client.__exit__(None, None, None)
        self.app = create_app(data_dir=self.storage)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.login()
        self.assertEqual(self.client.get("/api/preferences").json(), saved)
        response = self.client.get(saved["background_url"])
        self.assertEqual(response.content, content)
        self.assertEqual(response.headers["content-type"], "image/png")
        self.assertIn("no-store", response.headers["cache-control"])
        # Another logged-in browser sees the same saved appearance.
        with TestClient(create_app(data_dir=self.storage)) as other:
            other.post("/api/login", json={"password": "test-password-123"})
            self.assertEqual(other.get("/api/preferences").json(), saved)

    def test_background_jpeg_preserved_when_editing_names_and_can_be_removed(self):
        self.login()
        image, content = self.image_data("JPEG")
        saved = self.client.put("/api/preferences", json={"background_image": image}).json()
        response = self.client.get(saved["background_url"])
        self.assertEqual(response.headers["content-type"], "image/jpeg")
        self.assertEqual(response.content, content)
        saved = self.client.put("/api/preferences", json={"companion_name": "小岚"}).json()
        self.assertIsNotNone(saved["background_url"])
        removed = self.client.put("/api/preferences", json={"background_image": None}).json()
        self.assertEqual(removed["companion_name"], "小岚")
        self.assertIsNone(removed["background_url"])
        self.assertEqual(self.client.get("/api/preferences/background").status_code, 404)

    def test_invalid_preferences_do_not_partially_replace_saved_values(self):
        self.login()
        image, _ = self.image_data()
        saved = self.client.put("/api/preferences", json={"background_image": image}).json()
        gif, _ = self.image_data("GIF")
        _, png_bytes = self.image_data()
        broken_png = bytearray(png_bytes)
        broken_png[29] ^= 1  # Corrupt the header checksum without changing its dimensions.
        _, jpeg_bytes = self.image_data("JPEG")
        invalid = [
            {"companion_name": " "}, {"companion_name": "x" * 25}, {"companion_name": "a\nb"},
            {"companion_name": "\ud800"}, {"theme": "unknown"}, {"theme": []},
            {"app_name": "已移除的应用名称"},
            {"background_opacity": 101}, {"background_opacity": True},
            {"unknown": "value"}, {"background_image": gif},
            {"background_image": "data:image/png;base64,not-an-image!"},
            {"background_image": "data:image/png;base64," + base64.b64encode(b"invalid").decode()},
            {"background_image": self.image_data(size=(10001, 1))[0]},
            {"background_image": "data:image/png;base64," + base64.b64encode(broken_png).decode()},
            {"background_image": "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes[:-10]).decode()},
        ]
        for changes in invalid:
            with self.subTest(changes=list(changes)):
                response = self.client.put("/api/preferences", content=json.dumps({"companion_name": "应当回滚", **changes}), headers={"Content-Type": "application/json"})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(self.client.get("/api/preferences").json(), saved)
        too_large = "data:image/png;base64," + base64.b64encode(b"x" * (8 * 1024 * 1024 + 1)).decode()
        self.assertEqual(self.client.put("/api/preferences", json={"background_image": too_large}).status_code, 413)
        self.assertEqual(self.client.get("/api/preferences").json(), saved)

    def test_companion_nickname_is_sent_to_model_without_replacing_persona(self):
        self.login()
        self.client.put("/api/preferences", json={"companion_name": "小岚"})
        captured = []
        def inspect_prompt(model, messages):
            captured.append(messages[0].content)
            return "我叫小岚"
        with patch.object(LocalModel, "reply", inspect_prompt):
            reply = events(self.send(self.new_chat(), "你叫什么名字？"))
        self.assertEqual(reply[-1], ("done", {"content": "我叫小岚"}))
        self.assertTrue(captured[0].startswith(chatbot.DEFAULT_SYSTEM_PROMPT))
        self.assertIn("角色昵称是「小岚」", captured[0])

    def test_legacy_app_name_is_ignored_without_losing_other_preferences_or_history(self):
        self.login()
        thread = self.new_chat()
        self.send(thread, "保留这段聊天")
        image, content = self.image_data()
        saved = self.client.put("/api/preferences", json={
            "companion_name": "Yanami", "theme": "sky", "background_image": image,
        }).json()
        legacy = {key: value for key, value in saved.items() if key != "background_url"}
        legacy["app_name"] = "旧应用名称"
        async def seed_legacy_preferences():
            await self.app.state.db.execute("UPDATE preferences SET value = ? WHERE id = 1", (json.dumps(legacy),))
            await self.app.state.db.commit()
        self.client.portal.call(seed_legacy_preferences)
        self.assertEqual(self.client.get("/api/preferences").json(), saved)
        self.assertEqual(self.client.get(saved["background_url"]).content, content)
        self.assertEqual(self.client.put("/api/preferences", json={"app_name": "不再支持修改"}).status_code, 400)
        updated = self.client.put("/api/preferences", json={"theme": "pink"}).json()
        self.assertEqual(updated["companion_name"], "Yanami")
        self.assertEqual(updated["background_url"], saved["background_url"])
        self.assertNotIn("app_name", updated)
        self.assertEqual(len(self.client.get(f"/api/conversations/{thread}").json()["messages"]), 2)


if __name__ == "__main__":
    unittest.main()
