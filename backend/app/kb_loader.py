"""kb_loader.py — โหลดบทความ KB (published) แบบมี cache

ใช้ใน hot path ของ chatbot (ทุกข้อความต้อง match KB)
- cache key รวม org scope → กันข้อมูลข้ามโรงเรียน
- org_id=None = เห็นเฉพาะบทความส่วนกลาง (ระดับบริษัท)
- ล้าง cache ทันทีเมื่อมีการ create/update/delete KB (ดู invalidate_kb_cache)
"""
import json

from app.cache import cache


def _build(db, org_id):
    from sqlalchemy import select
    from app.models import KBArticle

    rows = db.execute(
        select(KBArticle).where(KBArticle.is_published == True)  # noqa: E712
    ).scalars().all()

    out = []
    for a in rows:
        a_org = getattr(a, "organization_id", None)
        # เห็นได้เมื่อ: บทความส่วนกลาง (a_org is None) หรือ ของโรงเรียนตัวเอง
        if a_org is not None and org_id is not None and a_org != org_id:
            continue
        if a_org is not None and org_id is None:
            continue
        try:
            steps = [s["text"] for s in (json.loads(a.steps) if a.steps else [])]
        except Exception:
            steps = []
        out.append({"kb_id": a.kb_id, "device_type": a.device_type,
                    "title": a.title, "steps": steps})
    return out


def load_kb_candidates(db, org_id=None):
    """คืน list ของ candidate บทความ KB (cache ตาม org scope)"""
    key = ("kb_candidates", org_id)
    hit = cache.get(key)
    if hit is not None:
        return hit
    data = _build(db, org_id)
    cache[key] = data
    return data


def invalidate_kb_cache():
    """ล้างเฉพาะ key ที่เกี่ยวกับ KB"""
    for k in [k for k in list(cache.keys()) if isinstance(k, tuple) and k and k[0] == "kb_candidates"]:
        cache.pop(k, None)
