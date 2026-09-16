"""conftest.py — ตั้งค่า environment ให้ชุดเทสต์ก่อน pytest จะ import ไฟล์เทสต์ใด ๆ

ปัญหาที่ไฟล์นี้แก้
------------------
`app/main.py` อ่าน secret ของ n8n เป็นค่าคงที่ระดับโมดูล (ตอน import):

    N8N_SHARED_SECRET = os.environ.get("N8N_SHARED_SECRET", "")

pytest เก็บไฟล์เทสต์เรียงตามชื่อ จึง import `test_error_envelope.py`
(ซึ่ง import `app.main`) ก่อน `test_line_create_ticket.py` ที่ตั้ง env ให้ตัวเอง
เมื่อถึงคิวไฟล์หลัง โมดูล `app.main` อยู่ใน sys.modules แล้ว การตั้ง env จึงสายเกินไป
ผลคือ `require_n8n_secret` เห็นค่าว่าง → ตอบ 503 "n8n integration is not configured"
ทุกเคส ทั้งที่รันไฟล์นั้นเดี่ยว ๆ ผ่านหมด

conftest.py ถูก import ก่อนไฟล์เทสต์ทุกไฟล์ จึงเป็นที่ที่ถูกต้องสำหรับตั้งค่านี้

หมายเหตุ: ค่า TEST_SECRET ต้องตรงกับ `TEST_SECRET` ใน test_line_create_ticket.py
(ไฟล์นั้นส่ง header X-N8N-Secret ด้วยค่าเดียวกัน) — แก้ที่ไหนต้องแก้ให้ตรงกันทั้งสองที่
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent

# ให้ `import app.main` ทำงานได้ไม่ว่า pytest จะถูกเรียกจากโฟลเดอร์ใด
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# secret สำหรับเทสต์ automation endpoint (/api/line/create-ticket)
# ตั้งแบบบังคับ ไม่ใช่ setdefault: ถ้าเครื่องนักพัฒนามีค่าจริงของ production อยู่ใน env
# เทสต์จะส่ง header ไม่ตรงและแดงทั้งชุด — ในบริบทเทสต์ต้องใช้ค่าที่เทสต์รู้เท่านั้น
os.environ["N8N_SHARED_SECRET"] = "test-n8n-secret"

# กันการเผลอเปิดโหมด production ระหว่างเทสต์ (main.py จะ raise ถ้า JWT_SECRET เป็นค่า dev)
os.environ.pop("ENVIRONMENT", None)