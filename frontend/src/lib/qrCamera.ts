/**
 * Shared QR camera helpers for ScanPage and the public no-login report form.
 *
 * Why this exists: both pages opened the camera slightly differently and failed
 * in different ways on real devices (laptop with only a front camera, phone on
 * plain HTTP, scanner container still display:none when the video started).
 */

type Html5QrcodeInstance = {
  start: (...args: any[]) => Promise<unknown>;
  stop: () => Promise<void>;
  clear: () => void;
  isScanning?: boolean;
};

const SCAN_CONFIG = { fps: 10, qrbox: { width: 220, height: 220 }, aspectRatio: 1 };

/** Camera APIs exist only on HTTPS or localhost. Phones on http://192.168.x.x get nothing. */
export function cameraBlockedReason(): string | null {
  if (typeof window === 'undefined') return null;
  if (!window.isSecureContext) {
    return 'เบราว์เซอร์บล็อกกล้องเพราะหน้านี้ไม่ได้เปิดผ่าน HTTPS — ใช้ปุ่ม "ถ่ายรูป QR" ด้านล่างแทน หรือเปิดลิงก์แบบ https://';
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return 'เบราว์เซอร์นี้เปิดกล้องไม่ได้ — ใช้ปุ่ม "ถ่ายรูป QR" ด้านล่างแทน';
  }
  return null;
}

/** Turn a getUserMedia / html5-qrcode error into a Thai message the reporter can act on. */
export function cameraErrorMessage(err: unknown): string {
  const text = `${(err as any)?.name || ''} ${(err as any)?.message || err || ''}`;
  if (/NotAllowed|Permission|denied/i.test(text)) {
    return 'ยังไม่ได้อนุญาตให้ใช้กล้อง — กดไอคอนแม่กุญแจ/กล้องข้างช่อง URL แล้วเลือก "อนุญาต" จากนั้นกดเปิดกล้องอีกครั้ง';
  }
  if (/NotFound|NO_CAMERA|DevicesNotFound/i.test(text)) {
    return 'ไม่พบกล้องบนเครื่องนี้ — ใช้ปุ่ม "ถ่ายรูป QR" หรือพิมพ์รหัสใต้สติกเกอร์แทน';
  }
  if (/NotReadable|TrackStart|in use|Could not start/i.test(text)) {
    return 'กล้องถูกแอปอื่นใช้อยู่ (เช่น Zoom/LINE/กล้อง) — ปิดแอปนั้นแล้วลองใหม่';
  }
  if (/secure|https/i.test(text)) {
    return cameraBlockedReason() || 'ต้องเปิดหน้านี้ผ่าน HTTPS จึงจะใช้กล้องได้';
  }
  return 'เปิดกล้องไม่สำเร็จ — ลองใหม่อีกครั้ง หรือใช้ปุ่ม "ถ่ายรูป QR" / พิมพ์รหัสแทน';
}

/** Let React commit the now-visible scanner box before html5-qrcode measures it. */
const nextFrame = () => new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));

/**
 * Open the camera inside `elementId` and call `onDecode` once with the first QR found.
 * Prefers the back camera; falls back to any camera (laptops usually have only a front one).
 * Returns a stop function. Throws with a friendly message on failure.
 */
export async function startQrCamera(
  elementId: string,
  onDecode: (text: string) => void,
): Promise<() => Promise<void>> {
  const blocked = cameraBlockedReason();
  if (blocked) throw new Error(blocked);

  await nextFrame();
  const { Html5Qrcode } = await import('html5-qrcode');
  const scanner: Html5QrcodeInstance = new Html5Qrcode(elementId, false) as any;

  let done = false;
  const stop = async () => {
    try {
      if ((scanner as any).isScanning !== false) await scanner.stop();
    } catch { /* already stopped */ }
    try { scanner.clear(); } catch { /* nothing rendered */ }
  };
  const handle = (text: string) => {
    if (done) return;
    done = true;
    stop().finally(() => onDecode(text));
  };

  try {
    // facingMode is a soft preference: phones pick the back camera, laptops use the one they have.
    await scanner.start({ facingMode: 'environment' }, SCAN_CONFIG, handle, () => {});
  } catch (first) {
    // Some browsers reject facingMode outright (OverconstrainedError). Retry with a listed camera.
    if (/NotAllowed|Permission|denied/i.test(String((first as any)?.name || first))) {
      throw new Error(cameraErrorMessage(first));
    }
    try {
      const cameras = await Html5Qrcode.getCameras();
      if (!cameras.length) throw new Error('NO_CAMERA');
      const back = cameras.find((c) => /back|rear|environment|หลัง/i.test(c.label)) || cameras[cameras.length - 1];
      await scanner.start(back.id, SCAN_CONFIG, handle, () => {});
    } catch (second) {
      await stop();
      throw new Error(cameraErrorMessage(second));
    }
  }
  return stop;
}

/**
 * Decode a QR from a photo (input type=file capture=environment).
 * Works on phones even over plain HTTP because the native camera app takes the picture.
 */
export async function scanQrFromFile(file: File, scratchElementId: string): Promise<string> {
  const { Html5Qrcode } = await import('html5-qrcode');
  const scanner = new Html5Qrcode(scratchElementId, false);
  try {
    return await scanner.scanFile(file, false);
  } catch {
    throw new Error('ไม่พบ QR ในรูปนี้ — ถ่ายให้ QR อยู่กลางภาพ ชัด ไม่สะท้อนแสง แล้วลองอีกครั้ง');
  } finally {
    try { scanner.clear(); } catch { /* nothing rendered */ }
  }
}
