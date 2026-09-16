"""
Ticket state machine — source of truth เดียวสำหรับกฎการเปลี่ยนสถานะ ticket.

apply_transition() ทำ 3 อย่างเท่านั้น: validate transition, เปลี่ยน status, เขียน history
(ไม่ยุ่งกับ side-effect fields เช่น closed_at/resolved_at/assigned_to — แต่ละ endpoint
จัดการ field เฉพาะทางของตัวเองเหมือนเดิม เพื่อไม่ให้พฤติกรรมเพี้ยน)
"""

from fastapi import HTTPException

from app.models import TicketUpdate

# ตาราง transition (คัดจาก main.py เดิม บรรทัด 441-451 — ไม่แก้กฎ)
STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"assigned", "cancelled"},
    "assigned": {"in_progress", "new", "cancelled"},
    "in_progress": {"pending", "waiting_parts", "waiting_user", "resolved", "cancelled"},
    "pending": {"in_progress", "cancelled"},
    "waiting_parts": {"in_progress", "pending", "resolved", "cancelled"},
    "waiting_user": {"in_progress", "pending", "resolved", "cancelled"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
    "cancelled": set(),
}


def apply_transition(db, ticket, target, *, force=False,
                     author_name=None, author_role=None, note=None):
    """Validate transition + เปลี่ยน status + เขียน TicketUpdate (history).

    - target ต้องเป็นสถานะที่รู้จัก มิฉะนั้น 400
    - ถ้า force=False ต้องเป็น transition ที่อนุญาตตาม STATUS_TRANSITIONS มิฉะนั้น 400
    - ไม่แตะ closed_at/resolved_at/assigned_to — เป็นหน้าที่ของ caller
    คืน (current, target)
    """
    current = ticket.status

    if target not in STATUS_TRANSITIONS:
        raise HTTPException(status_code=400, detail=f"Unknown ticket status: {target}")

    if not force and target not in STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: {current} → {target}",
        )

    ticket.status = target
    db.add(TicketUpdate(
        ticket=ticket,
        from_status=current,
        to_status=target,
        note=note,
        author_name=author_name,
        author_role=author_role,
    ))
    return current, target