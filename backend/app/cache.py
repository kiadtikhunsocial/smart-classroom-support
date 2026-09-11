"""cache.py — TTL cache แบบง่ายสำหรับ endpoint ที่อ่านบ่อย (ลด DB load)

ข้อควรระวังด้านความปลอดภัย (RBAC):
- ห้าม cache ข้อมูลที่ขึ้นกับสิทธิ์ผู้ใช้โดยไม่ใส่ scope ใน cache key
- ทุก key ต้องมีองค์ประกอบ scope (เช่น org id / role) เพื่อกันข้อมูลข้ามโรงเรียน
"""
import os
from cachetools import TTLCache, cached as _cached

# ขนาด/อายุ cache ปรับได้ผ่าน env (default 256 entries, 60 วินาที)
CACHE_MAXSIZE = int(os.environ.get("CACHE_MAXSIZE", "256"))
CACHE_TTL = int(os.environ.get("CACHE_TTL", "60"))

cache = TTLCache(maxsize=CACHE_MAXSIZE, ttl=CACHE_TTL)


def ttl_cache(func):
    """decorator: cache ผลลัพธ์ตาม argument ทั้งหมด (caller ต้องใส่ scope ใน args เอง)"""
    return _cached(cache)(func)


def invalidate_all():
    """ล้าง cache ทั้งหมด — เรียกหลังมีการเขียนข้อมูล (create/update/delete)"""
    cache.clear()
