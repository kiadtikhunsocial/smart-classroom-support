import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api/client';

/**
 * หน้าสแกน QR — ใช้กล้องจริง (html5-qrcode) + ช่องกรอกรหัสสำรอง
 * QR ที่ถูกต้องคือรหัสอุปกรณ์ เช่น DEV-2024-00123 หรือ URL ที่มี device_id
 */
export default function ScanPage({ onScanDevice, onBack }: {
  onScanDevice: (deviceId: string) => void;
  onBack: () => void;
}) {
  const videoRef = useRef<HTMLDivElement>(null);
  const scannerRef = useRef<any>(null);
  const [scanning, setScanning] = useState(false);
  const [manualCode, setManualCode] = useState('');
  const [status, setStatus] = useState<string>('พร้อมสแกน — เปิดกล้องเพื่อสแกน QR หรือกรอกรหัสอุปกรณ์');
  const [error, setError] = useState<string | null>(null);

  const extractDeviceId = (raw: string): string | null => {
    const s = raw.trim();
    // กรณีเป็น URL ที่มี token (QR ตาม spec: /scan?t=xxxx หรือ /r/xxxx)
    const tokenMatch = s.match(/[?&](?:t|token|qr)=([^&\s]+)/i);
    if (tokenMatch) return tokenMatch[1];
    // กรณีเป็น URL เช่น http://localhost:5173/scan?device=DEV-2024-00123
    const urlMatch = s.match(/[?&](?:device|device_id|code)=([^&\s]+)/i);
    if (urlMatch) return urlMatch[1];
    // กรณีเป็นรหัสตรงๆ รูปแบบ DEV-xxxx
    const devMatch = s.match(/DEV-[\w-]+/i);
    if (devMatch) return devMatch[0].toUpperCase();
    return null;
  };

  const isToken = (code: string) => /^[A-Za-z0-9_-]{20,}$/.test(code);

  const handleRaw = async (raw: string) => {
    const code = extractDeviceId(raw);
    if (!code) {
      setError(`ไม่พบรหัสใน QR: "${raw.slice(0, 50)}"`);
      return;
    }
    setError(null);
    // ถ้าเป็น token (ยาว ≥20 ตัว ไม่ใช่ pattern DEV-) → resolve ผ่าน /qr/resolve
    if (isToken(code) && !code.startsWith('DEV-')) {
      setStatus('พบ QR token — กำลังตรวจสอบอุปกรณ์...');
      try {
        const resp = await api.qrResolve(code);
        const device = resp?.device;
        if (!device) { setError('QR นี้ไม่ตรงกับอุปกรณ์ในระบบ'); setStatus('พร้อมสแกนอีกครั้ง'); return; }
        setStatus(`✅ ${device.device_id} (${device.device_type}) — ${resp?.room?.name || 'ไม่ระบุห้อง'}`);
        onScanDevice(device.device_id);
      } catch (e: any) {
        setError(`ไม่พบอุปกรณ์ที่ตรงกับ QR token นี้`);
        setStatus('พร้อมสแกนอีกครั้ง');
      }
      return;
    }
    // กรณีเป็น device_id ตรงๆ
    setStatus(`พบอุปกรณ์ ${code} — กำลังโหลดข้อมูล...`);
    try {
      const device = await api.getDevice(code);
      setStatus(`✅ ${device.device_id} (${device.device_type}) — ${device.room_name || 'ไม่ระบุห้อง'}`);
      onScanDevice(device.device_id);
    } catch (e: any) {
      setError(`ไม่พบอุปกรณ์ ${code} ในระบบ`);
      setStatus('พร้อมสแกนอีกครั้ง');
    }
  };

  const startScan = async () => {
    setError(null);
    setScanning(true);
    try {
      const Html5Qrcode = (await import('html5-qrcode')).Html5Qrcode;
      const scanner = new Html5Qrcode('qr-reader');
      scannerRef.current = scanner;
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        (decodedText: string) => {
          // สแกนเจอแล้ว — หยุดก่อน แล้วค่อยประมวลผล
          scanner.stop().then(() => {
            setScanning(false);
            handleRaw(decodedText);
          }).catch(() => {});
        },
        () => { /* frame ไม่มี QR — ข้าม */ }
      );
      setStatus('📷 กำลังสแกน — เล็ง QR ไปที่กล้อง');
    } catch (e: any) {
      setScanning(false);
      setError('เปิดกล้องไม่สำเร็จ — ใช้ช่องกรอกรหัสอุปกรณ์แทนได้ (เช่น DEV-2024-00123)');
    }
  };

  const stopScan = async () => {
    if (scannerRef.current) {
      try { await scannerRef.current.stop(); } catch {}
      scannerRef.current = null;
    }
    setScanning(false);
  };

  useEffect(() => {
    // มาจาก URL ?device=DEV-xxxx หรือ ?t=token (สแกน QR แล้วเบราว์เซอร์เปิด URL นี้)
    const params = new URLSearchParams(window.location.search);
    const deviceParam = params.get('device') || params.get('device_id');
    const tokenParam = params.get('t') || params.get('token') || params.get('qr');
    const code = tokenParam || deviceParam;
    if (code) {
      handleRaw(code);
    }
    return () => { stopScan(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleManual = (e: React.FormEvent) => {
    e.preventDefault();
    if (manualCode.trim()) handleRaw(manualCode.trim());
  };

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">สแกน QR</h1>
            <span className="top-bar-subtitle">สแกน QR ที่ติดกับอุปกรณ์เพื่อแจ้งซ่อม</span>
          </div>
        </div>
      </div>

      <div className="page-section">
        <div className="section-body" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, padding: '24px' }}>
          {/* สถานะ */}
          <div style={{ fontSize: '0.9rem', color: error ? 'var(--color-danger)' : 'var(--color-text-secondary)', textAlign: 'center' }}>
            {error || status}
          </div>

          {/* กล้องสแกน */}
          <div
            id="qr-reader"
            ref={videoRef}
            style={{
              width: '100%', maxWidth: 360, minHeight: 260,
              borderRadius: 'var(--radius-lg)', overflow: 'hidden',
              border: '2px dashed var(--color-border-strong)',
              background: '#0F0E13', display: scanning ? 'block' : 'none',
            }}
          />

          {!scanning && (
            <button className="btn btn-primary" onClick={startScan} style={{ padding: '12px 24px' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 8, verticalAlign: 'middle' }}>
                <path d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M21 17v2a2 2 0 01-2 2h-2M7 21H5a2 2 0 01-2-2v-2M7 12h10"/>
              </svg>
              เปิดกล้องสแกน
            </button>
          )}

          {scanning && (
            <button className="btn btn-ghost" onClick={stopScan}>หยุดสแกน</button>
          )}

          {/* กรอกรหัสสำรอง */}
          <div style={{ width: '100%', maxWidth: 360, borderTop: '1px solid var(--color-border)', paddingTop: 16 }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginBottom: 8, textAlign: 'center' }}>
              — หรือกรอกรหัสอุปกรณ์ (กรณี QR ชำรุด) —
            </div>
            <form onSubmit={handleManual} style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                className="form-input"
                value={manualCode}
                onChange={(e) => setManualCode(e.target.value)}
                placeholder="DEV-2024-00123"
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-secondary">ค้นหา</button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
