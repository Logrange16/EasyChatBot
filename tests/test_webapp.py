"""Integration tests use a local fake model; no paid requests or real keys."""

import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Override credentials before loading the application or its .env configuration.
os.environ["QWEN_API_KEY"] = "local-test-only"
os.environ["QWEN_BASE_URL"] = "https://example.invalid/v1"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["CHAT_PASSWORD"] = "test-password-123"
os.environ["CHAT_COOKIE_SECURE"] = "false"

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from starlette.testclient import TestClient

import chatbot
from webapp import COOKIE, create_app


class LocalModel(BaseChatModel):
    @property
    def _llm_type(self):
        return "offline-test"

    def reply(self, messages):
        assert isinstance(messages[0], SystemMessage)
        assert messages[0].content == chatbot.DEFAULT_SYSTEM_PROMPT
        humans = [m.content for m in messages if m.type == "human"]
        if humans[-1] == "fail":
            raise RuntimeError("private-provider-error-do-not-expose")
        return "你好，我记得：" + "；".join(humans)

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=self.reply(messages)))])

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
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
        self.directory = tempfile.TemporaryDirectory()
        self.storage = Path(self.directory.name)
        self.model_patch = patch.object(chatbot, "llm", LocalModel())
        self.model_patch.start()
        self.app = create_app(data_dir=self.storage)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.model_patch.stop()
        self.directory.cleanup()

    def login(self):
        response = self.client.post("/api/login", json={"password": "test-password-123"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["set-cookie"])
        self.assertIn("SameSite=strict", response.headers["set-cookie"])

    def new_chat(self):
        response = self.client.post("/api/conversations")
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


if __name__ == "__main__":
    unittest.main()
