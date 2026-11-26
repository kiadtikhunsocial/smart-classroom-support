# scripts — เครื่องมือเสริมระดับโปรเจกต์

ไม่ใช่ส่วนของเว็บและไม่ได้รันตอน deploy

| สคริปต์ | ทำอะไร | ต่อกับอะไร |
|---|---|---|
| `test_chatbot_flow.py` | ยิงชุดคำถามจริงไปที่ chatbot แล้วตรวจหมวดคำตอบ — **GitHub Actions ใช้** (`.github/workflows/chatbot-test.yml`) ห้ามเปลี่ยนชื่อ | backend ที่ deploy แล้ว |
| `build_training_dataset.py` | สร้างชุดข้อมูลฝึก/ประเมิน AI (JSONL) จาก KB และแค็ตตาล็อกที่อนุมัติแล้ว ไม่อ่าน log/ticket/ข้อมูลลูกค้า | ไฟล์ในเครื่อง → `training_data/` (ไม่ขึ้น git) |
| `convert_to_vertex_sft.py` | แปลง `training_data/*.jsonl` เป็นรูปแบบของ Vertex AI | ไฟล์ในเครื่อง |
| `tune_vertex_sft.py` | สร้างและติดตามงาน fine-tune บน Google Vertex AI | Google Cloud (ต้องมีบัญชี/สิทธิ์) |
| `eval_finetune.py` | เทียบโมเดลเดิมกับโมเดลที่ fine-tune แล้วด้วยกฎ | Vertex AI |

ลำดับ fine-tune: `build_training_dataset` → `convert_to_vertex_sft` → `tune_vertex_sft` → `eval_finetune`
(ตอนนี้ระบบจริงใช้ Gemini ปกติ + prompt ไม่ได้ใช้โมเดลที่ fine-tune)

การ import / แก้ workflow ของ n8n ดู `n8n_workflows/README.md` (สคริปต์ `n8n_workflows/prepare_import.py`)
