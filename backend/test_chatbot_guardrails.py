import sys
sys.path.insert(0, '.')

from app.chatbot_core import _create_ticket_from_fields


def test_unknown_device_never_falls_back_to_test_device():
    ticket_no, error = _create_ticket_from_fields({
        'device_id': 'Interactive Display ห้องที่ไม่ลงทะเบียน',
        'name': 'ทดสอบระบบ',
        'phone': '0812345678',
        'symptom': 'ทดสอบไม่ควรสร้าง ticket ผูกผิดอุปกรณ์',
    })
    assert ticket_no is None
    assert 'ไม่พบอุปกรณ์' in error


def test_safety_case_starts_urgent_collection():
    from app.assistant_policy import classify_urgency
    assert classify_urgency('มีกลิ่นไหม้และมีควัน') == 'safety_critical'
