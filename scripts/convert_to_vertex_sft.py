"""Convert training_data/*.jsonl into the Vertex AI supervised fine-tuning format.

`build_training_dataset.py` emits `{"messages": [{"role": "user", ...}, {"role": "model", ...}]}`,
which is the Gemini API tuning shape. Vertex AI supervised fine-tuning expects one JSON object
per line with `contents` (and an optional `systemInstruction`):

    {"systemInstruction": {"role": "system", "parts": [{"text": "..."}]},
     "contents": [{"role": "user", "parts": [{"text": "..."}]},
                  {"role": "model", "parts": [{"text": "..."}]}]}

The system instruction is the same assistant policy the runtime uses, so the tuned model is
trained under the guardrails it will actually serve with.

Usage:
    python scripts/convert_to_vertex_sft.py
    python scripts/convert_to_vertex_sft.py --no-system-instruction
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" if (ROOT / "backend" / "app").exists() else ROOT
sys.path.insert(0, str(BACKEND))

IN_DIR = ROOT / "training_data"
OUT_DIR = IN_DIR / "vertex"

# Documented Vertex AI supervised fine-tuning limits (Gemini 2.5/3.x text tuning).
MAX_TOKENS_PER_EXAMPLE = 131_072
MAX_VALIDATION_EXAMPLES = 5_000
CHARS_PER_TOKEN_ESTIMATE = 2  # Thai is byte-heavy; deliberately pessimistic.

PII_PATTERNS = (
    re.compile(r"\b0\d{8,9}\b"),
    re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b(?:TK|SC|DEV|TEST1)-[A-Z0-9-]+\b", re.IGNORECASE),
)

FALLBACK_POLICY = (
    "คุณคือผู้ช่วยบริการลูกค้าของระบบ Smart Classroom Support "
    "ตอบเฉพาะข้อมูลที่ได้รับอนุมัติ ห้ามเดาราคา ห้ามเปิดเผยข้อมูลภายใน "
    "และห้ามแนะนำการถอดหรือเปิดฝาอุปกรณ์"
)


def load_system_prompt() -> str:
    """Reuse the runtime policy so tuning and serving stay aligned."""
    try:
        from app.assistant_policy import build_system_prompt
    except Exception as exc:  # pragma: no cover - depends on host env
        print(f"[warn] ใช้ policy สำรอง เพราะ import app.assistant_policy ไม่ได้: {exc}", file=sys.stderr)
        return FALLBACK_POLICY
    text = (build_system_prompt() or "").strip()
    return text or FALLBACK_POLICY


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path.name}:{line_no} ไม่ใช่ JSON ที่ถูกต้อง: {exc}") from exc
            if not isinstance(row, dict):
                raise SystemExit(f"{path.name}:{line_no} ต้องเป็น JSON object")
            yield row


def to_vertex_row(row: dict[str, Any], system_prompt: str | None, origin: str, line_no: int) -> dict[str, Any]:
    messages = row.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise SystemExit(f"{origin}:{line_no} ต้องมี messages อย่างน้อย 2 รายการ")

    contents: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if not isinstance(message, dict):
            raise SystemExit(f"{origin}:{line_no} message ลำดับ {index + 1} ไม่ใช่ object")
        role = str(message.get("role", "")).strip()
        text = str(message.get("content", "")).strip()
        expected = "user" if index % 2 == 0 else "model"
        if role != expected:
            raise SystemExit(f"{origin}:{line_no} role ต้องสลับ user/model (พบ '{role}' ที่ลำดับ {index + 1})")
        if not text:
            raise SystemExit(f"{origin}:{line_no} message ลำดับ {index + 1} มีเนื้อหาว่าง")
        contents.append({"role": role, "parts": [{"text": text}]})

    if contents[-1]["role"] != "model":
        raise SystemExit(f"{origin}:{line_no} ตัวอย่างต้องจบด้วย role 'model'")

    out: dict[str, Any] = {}
    if system_prompt:
        out["systemInstruction"] = {"role": "system", "parts": [{"text": system_prompt}]}
    out["contents"] = contents
    return out


def validate_rows(rows: list[dict[str, Any]], origin: str, max_examples: int | None = None) -> None:
    if not rows:
        raise SystemExit(f"{origin}: ไม่มีตัวอย่างเลย")
    if max_examples is not None and len(rows) > max_examples:
        raise SystemExit(f"{origin}: มี {len(rows)} ตัวอย่าง เกินเพดาน {max_examples}")
    for index, row in enumerate(rows, start=1):
        serialized = json.dumps(row, ensure_ascii=False)
        for pattern in PII_PATTERNS:
            if pattern.search(serialized):
                raise SystemExit(f"{origin}:{index} ยังพบข้อมูลที่ต้อง mask ({pattern.pattern})")
        approx_tokens = len(serialized) // CHARS_PER_TOKEN_ESTIMATE
        if approx_tokens > MAX_TOKENS_PER_EXAMPLE:
            raise SystemExit(f"{origin}:{index} ยาวเกินเพดาน ~{approx_tokens} tokens")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def convert(name: str, system_prompt: str | None, max_examples: int | None = None) -> tuple[Path, int]:
    source = IN_DIR / f"{name}.jsonl"
    if not source.exists():
        raise SystemExit(f"ไม่พบ {source} — รัน scripts/build_training_dataset.py ก่อน")
    rows = [
        to_vertex_row(row, system_prompt, source.name, line_no)
        for line_no, row in enumerate(read_jsonl(source), start=1)
    ]
    validate_rows(rows, source.name, max_examples)
    target = OUT_DIR / f"{name}_sft.jsonl"
    write_jsonl(target, rows)
    return target, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="แปลงชุดข้อมูลเป็นรูปแบบ Vertex AI supervised fine-tuning")
    parser.add_argument(
        "--no-system-instruction",
        action="store_true",
        help="ไม่ฝัง systemInstruction ลงในไฟล์ (ใช้เมื่อจะส่ง policy ตอน inference เท่านั้น)",
    )
    args = parser.parse_args()

    system_prompt = None if args.no_system_instruction else load_system_prompt()

    train_path, train_count = convert("train", system_prompt)
    validation_path, validation_count = convert("validation", system_prompt, MAX_VALIDATION_EXAMPLES)

    # Vertex allows at most 5000 validation examples, or 30% of training size above 1000.
    if validation_count > 1000 and validation_count > train_count * 0.3:
        raise SystemExit("validation ใหญ่เกิน 30% ของ train — ปรับสัดส่วนใน build_training_dataset.py")

    manifest = {
        "schema": "vertex_supervised_tuning_contents_v1",
        "source_schema": "gemini_supervised_tuning_messages_v1",
        "system_instruction_embedded": system_prompt is not None,
        "train_examples": train_count,
        "validation_examples": validation_count,
        "files": {
            "train": str(train_path.relative_to(ROOT)),
            "validation": str(validation_path.relative_to(ROOT)),
        },
        "status": "synthetic_baseline_only_not_production_approved",
    }
    (OUT_DIR / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()