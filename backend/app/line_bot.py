"""
line_bot.py — LINE chatbot + AI troubleshooting ครบวงจร (ทำงานฝั่ง backend)
รับข้อความจาก n8n webhook → จัด session multi-turn → Gemini คุยถามข้อมูล
→ สร้าง ticket / บันทึก self-service → ส่ง notification (LINE group / push / email)

Flow:
  1. ผู้ใช้ส่งข้อความใน LINE (หรือคุยกับ OA)
  2. n8n รับ webhook → POST มาที่ /api/line/bot (endpoint ใน main.py)
  3. line_bot.handle_message() เรียก Gemini วิเคราะห์ + ตอบกลับ
  4. ถ้าอาการพื้นฐาน → แนะนำขั้นตอน (self-service)
  5. ถ้าไม่หาย/ซับซ้อน → คุยถามข้อมูล (ชื่อ/เบอร์/อุปกรณ์/ห้อง/อาการ) → สร้าง ticket
  6. แจ้งเตือน: กลุ่ม LINE + push ส่วนตัวเจ้าหน้าที่ + email
"""
import os
import json
import logging
import httpx
from datetime import datetime

from app.ai_client import request_text


logger = logging.getLogger(__name__)

LINE_TOKEN = os.environ.get("LINE_CHANNEL_TOKEN", "")
LINE_GROUP_ID = os.environ.get("LINE_GROUP_ID", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
LINE_API = "https://api.line.me/v2/bot"


def send_line_reply(reply_token: str, text: str, quick_replies: list | None = None,
                    image_url: str | None = None):
    """ตอบกลับ LINE (reply message) — รองรับ quick reply + ภาพสินค้า
    ส่ง text และ image ใน reply เดียวกันเสมอ (LINE ใช้ replyToken ได้ครั้งเดียว)
    ภาพต้องเป็น URL HTTPS ที่ LINE server ดึงได้"""
    if not LINE_TOKEN or not reply_token:
        return False
    text = (text or "ขออภัยค่ะ ระบบยังไม่สามารถตอบข้อความนี้ได้ กรุณาลองใหม่อีกครั้งนะคะ")[:5000]
    msgs = []
    msg = {"type": "text", "text": text}
    if quick_replies:
        msg["quickReply"] = {"items": [{"type": "action", "action": {
            "type": "message", "label": q[:20], "text": q}} for q in quick_replies[:13]]}
    msgs.append(msg)
    if image_url and image_url.startswith("https://"):
        msgs.append({"type": "image", "originalContentUrl": image_url,
                     "previewImageUrl": image_url})
    try:
        response = httpx.post(
            f"{LINE_API}/message/reply",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            json={"replyToken": reply_token, "messages": msgs},
            timeout=5,
        )
        if response.status_code >= 300:
            logger.warning("LINE reply failed with HTTP %s: %s", response.status_code, response.text[:300])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("LINE reply request failed: %s", exc)
        return False


def send_line_push(to: str, text: str):
    """Push ข้อความหา user/group (ใช้ตอนแจ้งเตือน ไม่ใช่ตอบกลับ)"""
    if not LINE_TOKEN or not to:
        return False
    try:
        response = httpx.post(
            f"{LINE_API}/message/push",
            headers={"Authorization": f"Bearer {LINE_TOKEN}"},
            json={"to": to, "messages": [{"type": "text", "text": (text or "")[:5000]}]},
            timeout=5,
        )
        if response.status_code >= 300:
            logger.warning("LINE push failed with HTTP %s: %s", response.status_code, response.text[:300])
            return False
        return True
    except httpx.HTTPError as exc:
        logger.warning("LINE push request failed: %s", exc)
        return False


def _gemini_text(prompt: str, system: str | None = None) -> str:
    """เรียก Gemini สำหรับภาษาอิสระ โดยใช้ policy กลางและ grounding ของ caller"""
    if system is None:
        try:
            from app.assistant_policy import build_system_prompt
            system = build_system_prompt()
        except Exception:
            system = "คุณคือผู้ช่วยบริการลูกค้า Smart Classroom ตอบจากข้อมูลอ้างอิงเท่านั้น"
    if not GEMINI_KEY:
        return ""
    from app.prompt_extensions import with_extension
    return request_text(
        [system, with_extension("line_reply", prompt)],
        generation_config={"temperature": 0.2, "maxOutputTokens": 500},
        timeout=15.0,
        retries=1,
    ) or ""
