"""Persist presentation preferences and validated background images in SQLite."""

import asyncio
import base64
import binascii
import io
import json
import warnings
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from starlette.exceptions import HTTPException

from chatbot_app.companion.prompts import MAX_PERSONA_LENGTH

DEFAULTS = {
    "companion_name": "你的聊天伙伴",
    "companion_prompt": "",
    "theme": "lavender",
    "background_opacity": 30,
}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PREFERENCES_BYTES = 12 * 1024 * 1024


async def initialize_preferences(db):
    await db.execute(
        "CREATE TABLE IF NOT EXISTS preferences ("
        "id INTEGER PRIMARY KEY CHECK (id = 1), value TEXT NOT NULL, "
        "background BLOB, mime TEXT, version TEXT)"
    )
    await db.execute(
        "INSERT OR IGNORE INTO preferences (id, value) VALUES (1, ?)",
        (json.dumps(DEFAULTS, ensure_ascii=False),),
    )


async def get_preferences(db):
    async with db.execute("SELECT value, version FROM preferences WHERE id = 1") as cursor:
        row = await cursor.fetchone()
    stored = json.loads(row[0])
    # Older databases may still contain app_name; keep the saved nickname and image.
    values = {key: stored.get(key, default) for key, default in DEFAULTS.items()}
    values["background_url"] = f"/api/preferences/background?v={row[1]}" if row[1] else None
    return values


def decode_background(value):
    if not isinstance(value, str) or len(value) > MAX_PREFERENCES_BYTES:
        raise HTTPException(400, "请选择不超过 8 MB 的 PNG 或 JPG 图片。")
    prefix, separator, encoded = value.partition(",")
    if not separator or not prefix.startswith("data:") or not prefix.endswith(";base64"):
        raise HTTPException(400, "图片无法读取，请重新选择 PNG 或 JPG 文件。")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(400, "图片无法读取，请重新选择 PNG 或 JPG 文件。")
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "图片超过 8 MB，请选择小一些的图片。")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ("PNG", "JPEG"):
                    raise HTTPException(400, "目前支持 PNG 和 JPG 格式的背景图。")
                if image.width * image.height > 20_000_000 or max(image.size) > 10000:
                    raise HTTPException(400, "图片分辨率过大，请缩小至 2000 万像素以内。")
                mime = "image/png" if image.format == "PNG" else "image/jpeg"
                image.verify()
            # JPEG verify() alone does not decode pixels; reject truncated files too.
            with Image.open(io.BytesIO(content)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(400, "图片内容无法读取，请选择有效的 PNG 或 JPG 文件。")
    return content, mime


async def update_preferences(db, data):
    allowed = set(DEFAULTS) | {"background_image"}
    if set(data) - allowed:
        raise HTTPException(400, "设置项无法识别，请刷新页面后重试。")
    current = await get_preferences(db)
    values = {key: current[key] for key in DEFAULTS}
    for key in ("companion_name",):
        if key in data:
            value = data[key]
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 24:
                raise HTTPException(400, "名称需要填写 1 到 24 个字符。")
            value = value.strip()
            if any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
                raise HTTPException(400, "名称中不能包含换行或控制字符。")
            values[key] = value
    if "companion_prompt" in data:
        value = data["companion_prompt"]
        if not isinstance(value, str) or len(value) > MAX_PERSONA_LENGTH:
            raise HTTPException(400, "陪伴人设需要是最多 20000 个字符的文字。")
        if any((ord(c) < 32 and c not in "\n\r\t") or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise HTTPException(400, "陪伴人设中不能包含无效控制字符。")
        values["companion_prompt"] = value.strip()
    if "theme" in data:
        if data["theme"] not in ("lavender", "pink", "sky"):
            raise HTTPException(400, "请选择淡紫色、粉色或天蓝色配色。")
        values["theme"] = data["theme"]
    if "background_opacity" in data:
        value = data["background_opacity"]
        if type(value) is not int or not 0 <= value <= 100:
            raise HTTPException(400, "背景显示强度需要在 0 到 100 之间。")
        values["background_opacity"] = value
    serialized = json.dumps(values, ensure_ascii=False)
    # One SQL update makes nickname, theme and the background change together.
    if "background_image" in data:
        content, mime, version = None, None, None
        if data["background_image"] is not None:
            content, mime = await asyncio.to_thread(decode_background, data["background_image"])
            version = uuid4().hex
        await db.execute(
            "UPDATE preferences SET value = ?, background = ?, mime = ?, version = ? WHERE id = 1",
            (serialized, content, mime, version),
        )
    else:
        await db.execute("UPDATE preferences SET value = ? WHERE id = 1", (serialized,))
    await db.commit()
    return await get_preferences(db)
