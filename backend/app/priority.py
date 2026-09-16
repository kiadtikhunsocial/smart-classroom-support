# -*- coding: utf-8 -*-
"""app/priority.py — Priority Engine (Blueprint §15)

แยกความสำคัญเป็นสองชั้น:

* ``user_priority``   — ผู้แจ้งเลือกเอง เก็บไว้เป็นข้อมูลอ้างอิง ไม่ใช้จัดคิว
* ``system_priority`` — P1–P4 ที่ระบบคำนวณจาก Impact × Urgency ใช้จัดคิวและตั้ง SLA

โมดูลนี้เป็น pure function ทั้งหมด (ไม่แตะ DB) เพื่อให้เรียกได้จากทั้ง endpoint
สร้าง ticket, งาน batch และเทสต์
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

# ─── ระดับที่รองรับ ────────────────────────────────────────────────────
IMPACT_LEVELS: tuple[str, ...] = ("school", "multi_room", "room", "single_user")
URGENCY_LEVELS: tuple[str, ...] = ("critical", "high", "normal", "low")
SYSTEM_PRIORITIES: tuple[str, ...] = ("P1", "P2", "P3", "P4")

DEFAULT_IMPACT = "room"
DEFAULT_URGENCY = "normal"

# ─── ตาราง Impact × Urgency → P1–P4 (§15) ─────────────────────────────
# แถว = impact (กว้าง→แคบ), คอลัมน์ = urgency (ด่วน→ไม่ด่วน)
PRIORITY_MATRIX: dict[str, dict[str, str]] = {
    "school":      {"critical": "P1", "high": "P1", "normal": "P2", "low": "P2"},
    "multi_room":  {"critical": "P1", "high": "P2", "normal": "P2", "low": "P3"},
    "room":        {"critical": "P2", "high": "P2", "normal": "P3", "low": "P3"},
    "single_user": {"critical": "P2", "high": "P3", "normal": "P4", "low": "P4"},
}

# ชั่วโมงเป้าหมายสำหรับ SLA (ค่าเริ่มต้น — override ได้ผ่านตาราง settings คีย์ sla_hours)
DEFAULT_SLA_HOURS: dict[str, int] = {"P1": 4, "P2": 8, "P3": 24, "P4": 72}

# แปลง priority แบบเดิม (low/normal/high/critical) ↔ P1–P4 เพื่อ backward compatibility
LEGACY_TO_URGENCY: dict[str, str] = {
    "critical": "critical",
    "high": "high",
    "normal": "normal",
    "low": "low",
}
SYSTEM_TO_LEGACY: dict[str, str] = {
    "P1": "critical",
    "P2": "high",
    "P3": "normal",
    "P4": "low",
}


def normalize_impact(value: Optional[str]) -> str:
    """คืนค่า impact ที่ถูกต้อง — ค่าไม่รู้จัก/ว่าง จะได้ค่าเริ่มต้น ``room``"""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in IMPACT_LEVELS:
            return v
    return DEFAULT_IMPACT


def normalize_urgency(value: Optional[str]) -> str:
    """คืนค่า urgency ที่ถูกต้อง — ค่าไม่รู้จัก/ว่าง จะได้ค่าเริ่มต้น ``normal``"""
    if isinstance(value, str):
        v = value.strip().lower()
        if v in URGENCY_LEVELS:
            return v
        if v in LEGACY_TO_URGENCY:
            return LEGACY_TO_URGENCY[v]
    return DEFAULT_URGENCY


def compute_system_priority(
    impact: Optional[str] = None,
    urgency: Optional[str] = None,
) -> str:
    """คำนวณ P1–P4 จาก Impact × Urgency ตามตาราง §15

    >>> compute_system_priority("school", "critical")
    'P1'
    >>> compute_system_priority("single_user", "normal")
    'P4'
    >>> compute_system_priority(None, None)   # room × normal
    'P3'
    """
    imp = normalize_impact(impact)
    urg = normalize_urgency(urgency)
    return PRIORITY_MATRIX[imp][urg]


def sla_hours(system_priority: Optional[str], overrides: Optional[dict] = None) -> int:
    """ชั่วโมงเป้าหมายของ system_priority — ``overrides`` มาจาก settings ได้"""
    p = (system_priority or "").upper()
    if p not in SYSTEM_PRIORITIES:
        p = "P3"
    if overrides:
        raw = overrides.get(p, overrides.get(p.lower()))
        try:
            if raw is not None and int(raw) > 0:
                return int(raw)
        except (TypeError, ValueError):
            pass
    return DEFAULT_SLA_HOURS[p]


def compute_sla_due(
    system_priority: Optional[str],
    start: Optional[datetime] = None,
    overrides: Optional[dict] = None,
) -> datetime:
    """เวลาครบกำหนด SLA — นับจาก ``start`` (ค่าเริ่มต้น = เวลาปัจจุบัน UTC)"""
    base = start or datetime.now(timezone.utc)
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    return base + timedelta(hours=sla_hours(system_priority, overrides))


def legacy_priority_for(system_priority: Optional[str]) -> str:
    """map P1–P4 กลับเป็นค่า priority_enum เดิม เพื่อให้ UI/รายงานที่มีอยู่ยังทำงาน"""
    return SYSTEM_TO_LEGACY.get((system_priority or "").upper(), "normal")


def resolve_priority(
    impact: Optional[str] = None,
    urgency: Optional[str] = None,
    user_priority: Optional[str] = None,
    category_default_impact: Optional[str] = None,
    category_default_urgency: Optional[str] = None,
) -> dict:
    """คำนวณชุดค่าความสำคัญทั้งหมดสำหรับ ticket หนึ่งใบ

    ลำดับการเลือกค่า: ค่าที่ส่งมาตรง ๆ → ค่าเริ่มต้นของหมวดปัญหา →
    ค่าที่อนุมานจาก user_priority → ค่าเริ่มต้นของระบบ

    คืน dict ที่มีคีย์ impact, urgency, system_priority, user_priority, priority
    (คีย์ ``priority`` คือค่าที่เขียนลงคอลัมน์เดิมเพื่อ backward compatibility)
    """
    imp_src = impact or category_default_impact
    urg_src = urgency or category_default_urgency or user_priority

    imp = normalize_impact(imp_src)
    urg = normalize_urgency(urg_src)
    sysp = compute_system_priority(imp, urg)

    up = None
    if isinstance(user_priority, str) and user_priority.strip().lower() in LEGACY_TO_URGENCY:
        up = user_priority.strip().lower()

    return {
        "impact": imp,
        "urgency": urg,
        "system_priority": sysp,
        "user_priority": up,
        "priority": legacy_priority_for(sysp),
    }