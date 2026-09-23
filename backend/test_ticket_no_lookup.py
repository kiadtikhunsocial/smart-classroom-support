"""test_ticket_no_lookup.py — การตีความเลข Ticket ที่ผู้ใช้กรอก/สแกนมา

โจทย์ด้านความปลอดภัยของข้อมูลที่ไฟล์นี้เฝ้าไว้: เลข Ticket มีตัวตรวจสอบตัวท้าย
(mod 37,36) ถ้าผู้แจ้งพิมพ์เพี้ยนไปหนึ่งตัว เลขที่ได้อาจเป็นเลขจริงของใบอื่น หรือ
ของโรงเรียนอื่นพอดี ระบบจึงต้อง "ไม่" ส่งเลขที่พิสูจน์แล้วว่าตัวตรวจสอบไม่ตรงไปค้น
ฐานข้อมูล และต้อง "ไม่" เติมตัวตรวจสอบให้เมื่อผู้ใช้ไม่ได้กรอกมา (การเติมจะเปลี่ยน
เลขที่พิมพ์เพี้ยนให้กลายเป็นเลขที่ถูกต้องของใบอื่น)

ขณะเดียวกันต้องยังยืดหยุ่นเรื่องตัวคั่น/ตัวพิมพ์ และต้องไม่ทำให้ Ticket รูปแบบเก่า
(TK-YYYYMM-NNNN ซึ่งไม่มีตัวตรวจสอบ) ถูกตีว่ากรอกผิด
"""
import re

from app.main import (
    _CHECK_ALPHABET,
    _mod37_36_check_char,
    _ticket_no_candidates,
    TICKET_NO_PREFIX,
    ticket_no_of,
)

CANONICAL = ticket_no_of("SCHM01", 2026, 1)          # TK.SCHM01.26.0001-<check>
BODY, CHECK = CANONICAL.rsplit("-", 1)


def _letters(value: str) -> str:
    """ตัวอักษรของเลขโดยไม่สนตัวคั่นและตัวพิมพ์ — ใช้เทียบว่า 'ตัวอักษรไม่ถูกแก้'"""
    return re.sub(r"[.\-_/\s]", "", (value or "").upper())


def _assert_nothing_invented(raw: str, candidates: list[str]) -> None:
    """ทุกค่าที่จะเอาไปค้น DB ต้องมีตัวอักษรตรงกับที่ผู้ใช้กรอกเป๊ะ

    ต่างกันได้แค่ตัวคั่นกับตัวพิมพ์ ถ้ามี candidate ที่ตัวอักษรเปลี่ยนไปแม้ตัวเดียว
    แปลว่าระบบกำลังเดาเลขแทนผู้ใช้ ซึ่งเป็นช่องที่ทำให้เห็นใบงานของคนอื่น
    """
    for candidate in candidates:
        assert _letters(candidate) == _letters(raw), (
            f"candidate {candidate!r} ไม่ตรงกับที่กรอก {raw!r}"
        )


def _wrong_check_char() -> str:
    """ตัวตรวจสอบที่ 'ไม่' ตรงกับ BODY — เอามาจำลองการพิมพ์ผิดตัวท้าย"""
    return next(c for c in _CHECK_ALPHABET if c != CHECK)


def test_canonical_number_is_accepted():
    candidates, problem = _ticket_no_candidates(CANONICAL)
    assert problem is None
    assert CANONICAL in candidates


def test_lowercase_and_dash_separators_still_match():
    typed = CANONICAL.lower().replace(".", "-")
    candidates, problem = _ticket_no_candidates(typed)
    assert problem is None
    assert CANONICAL in candidates
    _assert_nothing_invented(typed, candidates)


def test_no_separators_at_all_still_match():
    typed = _letters(CANONICAL)          # TKSCHM01260001Q
    candidates, problem = _ticket_no_candidates(typed)
    assert problem is None
    assert CANONICAL in candidates
    _assert_nothing_invented(typed, candidates)


def test_surrounding_spaces_are_ignored():
    candidates, problem = _ticket_no_candidates(f"  {CANONICAL}  ")
    assert problem is None
    assert CANONICAL in candidates


def test_wrong_check_char_returns_no_candidates():
    """ตัวตรวจสอบไม่ตรง = พิสูจน์แล้วว่าเพี้ยน ห้ามเอาไปค้น DB เลย"""
    typed = f"{BODY}-{_wrong_check_char()}"
    candidates, problem = _ticket_no_candidates(typed)
    assert candidates == []
    assert problem is not None
    kind, value = problem
    assert kind == "check_mismatch"
    assert value == _letters(typed) or value == typed.upper()


def test_mistyped_digit_is_not_silently_corrected():
    """พิมพ์ลำดับเพี้ยน (0001 -> 0002) ต้องไม่ถูกแก้ให้กลายเป็นใบอื่น"""
    typed = CANONICAL.replace(".0001-", ".0002-")
    assert typed != CANONICAL
    candidates, problem = _ticket_no_candidates(typed)
    _assert_nothing_invented(typed, candidates)
    assert ticket_no_of("SCHM01", 2026, 2) not in candidates
    assert problem is not None and problem[0] == "check_mismatch"


def test_missing_check_char_is_not_filled_in():
    """ไม่กรอกตัวตรวจสอบ: ค้นตรงตัวได้ แต่ห้ามเติมตัวท้ายให้เอง"""
    candidates, problem = _ticket_no_candidates(BODY)
    assert problem is not None and problem[0] == "missing_check"
    assert CANONICAL not in candidates
    _assert_nothing_invented(BODY, candidates)


def test_legacy_number_without_check_char_is_not_flagged():
    """Ticket รูปแบบเก่ายังต้องเปิดดูได้ ไม่ใช่ถูกตีว่ากรอกผิด"""
    candidates, problem = _ticket_no_candidates("TK-202401-0001")
    assert problem is None
    assert "TK-202401-0001" in candidates


def test_device_code_is_passed_through_untouched():
    """รหัสอุปกรณ์ (ไม่ขึ้นต้น TK) ไม่เข้ากติกาตัวตรวจสอบ — ปล่อยผ่านให้ชั้นบนแจ้งเอง"""
    typed = "TEST1-B1-R101-DISP-01"
    candidates, problem = _ticket_no_candidates(typed)
    assert problem is None
    assert typed in candidates
    assert not any(c.upper().startswith(f"{TICKET_NO_PREFIX}.") for c in candidates)


def test_empty_input_returns_nothing():
    assert _ticket_no_candidates("") == ([], None)
    assert _ticket_no_candidates("   ") == ([], None)
    assert _ticket_no_candidates(None) == ([], None)


def test_org_wide_six_digit_sequence_round_trips():
    """เลขที่ไม่ผูกโรงเรียน (token ALL, ลำดับ 6 หลัก) ต้องตีความได้เหมือนกัน"""
    number = ticket_no_of("ALL", 2026, 1, 6)
    assert _mod37_36_check_char(number.rsplit("-", 1)[0]) == number.rsplit("-", 1)[1]
    for typed in (number, number.lower(), _letters(number)):
        candidates, problem = _ticket_no_candidates(typed)
        assert problem is None, typed
        assert number in candidates, typed