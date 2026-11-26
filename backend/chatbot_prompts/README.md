# Prompt AI ทั้งหมดอยู่ที่ไหน และแก้ยังไง

## แก้ได้ 3 ทาง (เลือกตามความต้องการ)

| ต้องการ | ทำที่ไหน | มีผลเมื่อไร |
|---|---|---|
| ปรับน้ำเสียง/แนวทางตอบ **ทันที** | เว็บ → เมนู “จัดการ AI / LINE OA” → แท็บ “คำแนะนำ AI” → เลือกประเภทงาน → แก้ → บันทึก (owner/super_admin) | ทันที ไม่ต้อง deploy |
| เปลี่ยน **ค่าเริ่มต้น** ที่มากับโค้ด | ไฟล์ `.txt` ในโฟลเดอร์นี้ (ชื่อไฟล์ = ชื่องาน) | หลัง deploy backend ใหม่ และ **เฉพาะงานที่ยังไม่เคยบันทึกจากเว็บ** |
| แก้ **prompt หลัก / กฎ** | ไฟล์ Python ตามตารางด้านล่าง | หลัง deploy backend ใหม่ |

> ⚠️ ถ้างานไหนเคยกดบันทึกจากเว็บแล้ว ค่าบนเว็บ (ตาราง `chatbot_prompt_settings` ใน Supabase) จะชนะไฟล์เสมอ
> แก้ไฟล์แล้วไม่เห็นผล → เข้าเว็บ แท็บ “คำแนะนำ AI” เลือกงานนั้น กด **“กลับไปใช้ค่าจากไฟล์”**
> (เรียก `DELETE /api/chatbot/manage/prompts/<งาน>`)

คำแนะนำทุกงานยาวได้ไม่เกิน 2,000 ตัวอักษร และถูก **ต่อท้าย** prompt หลัก (ไม่แทนที่) ถ้าขัดกับกฎความปลอดภัย AI จะยึดกฎ
`global_style` ถูกต่อท้ายทุกงาน กลไกทั้งหมดอยู่ใน `backend/app/prompt_extensions.py`

## แผนที่ prompt (ใครเรียก → ส่งไปไหน)

AI ทุกตัวเรียก Google Gemini ผ่าน `backend/app/ai_client.py` (env `GEMINI_API_KEY`, `GEMINI_MODEL`)

| ชื่องาน (แก้บนเว็บได้) | ไฟล์ค่าเริ่มต้น | prompt หลักอยู่ที่ | ใช้ตอนไหน |
|---|---|---|---|
| `global_style` | `global_style.txt` (ยังไม่มีไฟล์ = ว่าง) | — | ต่อท้ายทุกงาน |
| `web_chat` | `web_chat.txt` | `app/web_agent.py` → `_system_prompt()` | แชต AI บนหน้าเว็บ (`AIChatWidget.tsx` → `POST /api/chatbot/web`) |
| `intent` | `intent.txt` | `app/gemini_service.py` → `classify_intent()` | แยกเจตนาข้อความ LINE |
| `field_extraction` | `field_extraction.txt` | `app/gemini_service.py` → `extract_fields_ai()` | ดึงชื่อ/เบอร์/อาการจากข้อความ |
| `slot_question` | `slot_question.txt` | `app/gemini_service.py` → `phrase_slot_question()` | ถามข้อมูลที่ยังขาดตอนแจ้งซ่อม |
| `orchestration` | `orchestration.txt` | `app/gemini_service.py` → `gemini_orchestrate()` | ตัดสินลำดับบทสนทนา |
| `repair_reply` | `repair_reply.txt` | `app/gemini_service.py` → `phrase_repair_reply()` | เรียบเรียงคำตอบเรื่องแจ้งซ่อม |
| `kb_match` | `kb_match.txt` | `app/gemini_service.py` → `match_article()` | เลือกบทความฐานความรู้ที่ตรงอาการ |
| `kb_explanation` | `kb_explanation.txt` | `app/gemini_service.py` → `explain_steps()` | อธิบายขั้นตอนแก้จากบทความ |
| `line_reply` | `line_reply.txt` | `app/line_bot.py` → `_gemini_text()` | ข้อความตอบกลับใน LINE |

prompt ที่ **ไม่มี** ช่องแก้บนเว็บ (แก้ในโค้ดเท่านั้น):

| ส่วน | ที่อยู่ | หมายเหตุ |
|---|---|---|
| กฎความปลอดภัยหลักของแชตบอต LINE | `app/assistant_policy.py` → `build_system_prompt()` | ห้ามย้ายไปไฟล์คำแนะนำ (กัน prompt injection) |
| น้ำเสียงต่อท้ายกฎหลัก | `backend/chatbot_extra_prompt.txt` | ต่อท้าย `build_system_prompt()` ต้อง deploy |
| กฎของแชตเว็บ (RULES) | `app/web_agent.py` → `_system_prompt()` | ส่วนกฎห้ามแก้ผ่านเว็บ |
| แปลภาษาแชตเว็บ (5 ภาษา) | `app/chatbot_i18n.py` → `to_thai()` / `from_thai()` | ใช้ตอน Gemini ตอบแบบสนทนาไม่ได้ |

## ข้อมูลที่ไม่ควรใส่ใน prompt
- วิธีแก้อาการ → เพิ่มเป็นบทความใน “ฐานความรู้แชตบอต” (ตาราง `kb_articles`)
- ราคา/สินค้า/ช่องทางติดต่อ → `app/company_catalog.py`
- คำถาม–คำตอบสำเร็จรูป → แท็บ “คำถาม–คำตอบ” ในหน้า “จัดการ AI / LINE OA” (ใช้เฉพาะคำถามที่ตรงกันทุกตัวอักษร ต้องกดเผยแพร่ก่อน)
- สถานะงาน/ประกัน/การชำระเงิน → AI อ่านจากฐานข้อมูลเองผ่าน backend ห้ามเขียนลง prompt

## ขั้นตอนแนะนำเวลาแก้
บันทึก → แท็บ “ทดลองถาม” → ทดสอบคำถามจริงใน LINE / แชตเว็บ รวมคำถามกำกวม อันตราย และคำสั่งหลอกให้เปิด prompt
การแก้ prompt ไม่ใช่การฝึกโมเดล และห้ามใช้แก้ข้อมูลจริงในฐานข้อมูล
