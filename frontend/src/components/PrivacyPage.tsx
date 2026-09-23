import React from 'react';

// ─── นโยบายความเป็นส่วนตัว (PDPA) — เปิดสาธารณะ ─────────────────────
export default function PrivacyPage({ onBack }: { onBack: () => void }) {
  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 720 }}>
        <div className="login-logo">
          <div style={{ textAlign: 'center', width: '100%' }}>
            <h1 className="login-title">นโยบายความเป็นส่วนตัว (Privacy Policy)</h1>
            <p className="login-subtitle">บริษัท ไอว่า ริช ยู ดี จำกัด — ระบบ Smart Classroom Support</p>
          </div>
        </div>
        <div className="login-divider" />
        <div style={{ fontSize: '0.9rem', lineHeight: 1.8, textAlign: 'left' }}>
          <p><strong>1. ข้อมูลที่เราจัดเก็บ</strong><br />
          ระบบจัดเก็บข้อมูลส่วนบุคคลเท่าที่จำเป็นต่อการให้บริการแจ้งซ่อมและติดตามงาน ได้แก่ ชื่อผู้แจ้ง เบอร์โทรศัพท์ อีเมล (ถ้ามี) ประเภทอุปกรณ์ อาการที่แจ้ง และประวัติการแจ้งซ่อม</p>

          <p><strong>2. วัตถุประสงค์การใช้งานข้อมูล</strong><br />
          ข้อมูลถูกใช้เพื่อประมวลผลการแจ้งซ่อม ติดต่อกลับผู้แจ้ง ติดตามสถานะ และพัฒนาคุณภาพการบริการเท่านั้น</p>

          <p><strong>3. การเก็บรักษา</strong><br />
          ข้อมูลถูกจัดเก็บอย่างปลอดภัยในฐานข้อมูลระบบ และเข้าถึงได้เฉพาะเจ้าหน้าที่ที่เกี่ยวข้องเท่านั้น</p>

          <p><strong>4. สิทธิ์ของเจ้าของข้อมูล</strong><br />
          ท่านมีสิทธิ์ตาม พ.ร.บ.คุ้มครองข้อมูลส่วนบุคคล (PDPA) ในการขอเข้าถึง แก้ไข หรือขอลบข้อมูลของท่านได้ โดยติดต่อผ่านช่องทางสนับสนุนของบริษัท</p>

          <p><strong>5. การเปิดเผยแก่บุคคลภายนอก</strong><br />
          ข้อมูลจะไม่ถูกขายหรือเปิดเผยแก่บุคคลภายนอก ยกเว้นตามที่กฎหมายกำหนด หรือใช้บริการประมวลผล AI (Gemini) เฉพาะในส่วนที่ไม่เป็นข้อมูลระบุตัวตน</p>

          <p><strong>6. การติดต่อ</strong><br />
          สอบถามหรือใช้สิทธิ์เกี่ยวกับข้อมูลส่วนบุคคล ติดต่อ: supannee@iwarichyoudee.com หรือ LINE: @590cbneh</p>

          <p style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem', marginTop: 16 }}>ปรับปรุงล่าสุด: {new Date().toLocaleDateString('th-TH')}</p>
        </div>
        <button className="btn btn-ghost" style={{ marginTop: 16, width: '100%' }} onClick={onBack}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 6, verticalAlign: '-2px' }}>
            <path d="M15 18l-6-6 6-6" />
          </svg>
          กลับ
        </button>
      </div>
    </div>
  );
}
