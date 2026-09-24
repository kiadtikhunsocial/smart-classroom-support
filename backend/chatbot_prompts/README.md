# จุดปรับพฤติกรรมแชตบอต

- `backend/chatbot_extra_prompt.txt`: น้ำเสียง/หลักสนทนาร่วมของเว็บและ LINE OA
- ไฟล์ `.txt` ในโฟลเดอร์นี้: คำแนะนำเฉพาะงาน; ปล่อยว่างได้ ไม่ต้องแก้ Python
- `backend/app/assistant_policy.py`: กฎความปลอดภัย การอ้างอิงข้อมูล และป้องกัน prompt injection **ห้ามย้ายไปไฟล์คำแนะนำ**
- `backend/app/gemini_service.py`: เส้นทาง AI สำหรับจำแนกเจตนา จับข้อมูล จับคู่ KB และร่างคำตอบ
- `backend/app/line_bot.py`: LINE OA และ fallback; `line_reply.txt` เพิ่มคำแนะนำเฉพาะข้อความ LINE
- บทความวิธีแก้ให้แก้ในหน้า “ฐานความรู้แชตบอต”; ราคา/สินค้าให้แก้แค็ตตาล็อกจริง ไม่ใช่ prompt

ขั้นตอน: แก้ไฟล์เฉพาะงาน → ทดสอบ `backend/tests/test_chatbot_prompt_extension.py` และชุด chatbot → ทดสอบคำถามจริงใน staging รวมทั้งคำถามกำกวม/อันตราย/หลอกให้เปิด prompt → deploy backend ใหม่ การเปลี่ยน prompt ไม่ใช่การฝึกโมเดล และไม่ได้เปลี่ยนข้อมูลจริงใน DB
