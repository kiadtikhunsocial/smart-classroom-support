# frontend — เว็บ (React 18 + Vite + TypeScript)

Deploy บน **Vercel** (`https://iwasmart-service.vercel.app`) ไฟล์ตั้งค่า: `vercel.json`, `vite.config.ts`
ทุกหน้าคุยกับ backend ผ่าน **`src/api/client.ts`** ที่เดียว (ไม่มี fetch กระจายในหน้าอื่น)

```
เบราว์เซอร์ ── src/api/client.ts ──HTTPS──> backend Render  /api/*  ──> Supabase / LINE / Gemini / R2
                 (JWT ใน localStorage)
```

- URL ของ backend: env `VITE_API_URL` ตอน build ถ้าไม่ตั้ง = `/api` ของโดเมนเดียวกัน ซึ่ง Vercel ส่งต่อไป Render ตาม `vercel.json` (rewrites `/api/*`, `/uploads/*`)
- dev ในเครื่อง: `docker compose up -d frontend` → http://127.0.0.1:5173 (vite proxy `/api` → backend :8000)
- ไม่มี router library: หน้าสาธารณะเลือกจาก query string, หน้าเจ้าหน้าที่เลือกจาก hash `#/<เมนู>` (ทั้งหมดอยู่ใน `src/App.tsx`)

## หน้าสาธารณะ (ไม่ต้องล็อกอิน) — เลือกจาก URL ใน `App.tsx`

| URL | หน้า (component) | ใช้ API |
|---|---|---|
| `/?home=1` | `PublicHomeView` (หน้าแรก, ติดตามงาน, แชต AI) | `/api/tickets/track/*`, `/api/public/warranty/*`, `/api/chatbot/web` |
| `/?ticket=<เลข>` | `PublicHomeView` เปิดพร้อมค้นเลข Ticket | `/api/tickets/track/{no}` |
| `/?publicreport=1`, `/?device=<รหัส>`, `/?t=<token>` | `PublicNoLoginReportView` (ฟอร์มแจ้งซ่อม / สแกน QR) | `/api/public/*`, `/api/qr/resolve/*` |
| `/?customer=1` | `CustomerSignupPage` (ลูกค้าฝากข้อมูลให้ทีมขาย) | `/api/public/customer-signup` |
| `/?register=1` | `RegisterPage` (ขอเปิดบัญชีเจ้าหน้าที่) | `/api/public/register` |
| `/?privacy` | `PrivacyPage` | – |
| `/?login`, `/?job=<เลข>` | หน้าเข้าสู่ระบบ / เปิดใบงานจากลิงก์ LINE ของช่าง | `/api/auth/login` |

แชต AI ลอยในหน้าแรก: `components/AIChatWidget.tsx` → `POST /api/chatbot/web` → `backend/app/web_agent.py`
ภาษา 5 ภาษาของหน้าสาธารณะ: `src/publicI18n.ts`

## หน้าเจ้าหน้าที่ (ต้องล็อกอิน) — เมนูใน `components/Sidebar.tsx`, แสดงผลใน `App.tsx`

| เมนู (`#/...`) | component | API หลัก |
|---|---|---|
| `dashboard` | ใน `App.tsx` + `DashboardCharts`, `StatCard` | `/api/stats`, `/api/tickets` |
| `tickets` | `components/tickets/*` | `/api/tickets*` |
| `team` | `components/dispatch/*` | `/api/dispatch/*`, `/api/staff` |
| `devices` | `DevicesPage` | `/api/devices*`, `/api/device-types` |
| `kb` | `KBPage` | `/api/kb*` |
| `chatbot`, `ratings` | `ChatbotStudioPage`, `RatingsResults` (owner/super_admin) | `/api/chatbot/manage/*` |
| `qrbatch` | `QRBatchPage` | `/api/qr/batch` |
| `pm` | `PMPage` | `/api/pm/*` |
| `scan` | `ScanPage` (ใช้กล้องผ่าน `lib/qrCamera.ts`) | `/api/qr/resolve/*`, `/api/devices/*` |
| `schools` | `SchoolsPage` | `/api/organizations*` |
| `users` | `UsersPage` | `/api/users*` |
| `reports` | `ReportsPage` | `/api/reports/*` |
| `audit` | `AuditLogPage` | `/api/audit-logs`, `/api/deleted-records` |
| `registrations` | `RegistrationsPage` | `/api/registrations*` |
| `sales` | `SalesPage`, `SalesRecordsPanel` | `/api/sales/*` |
| `settings` | `SettingsPage` | `/api/settings` |
| `profile` | `ProfilePage` | `/api/me/*` |

สิทธิ์ว่าใครเห็นเมนูไหน: `visibleMenusForRole()` ใน `Sidebar.tsx` (backend ตรวจสิทธิ์ซ้ำทุก endpoint)

## โฟลเดอร์
- `src/api/client.ts` — ฟังก์ชันเรียก API ทุกตัว + จัดการ token
- `src/types/` — ชนิดข้อมูลที่ตรงกับ response ของ backend
- `src/components/` — หน้าและชิ้นส่วน UI (`ConfirmDialog`, `ModalOverlay` ใช้แทน alert/confirm)
- `src/styles/` — CSS แยกตามหน้า, ธีมอยู่ที่ `theme.ts` + `styles/themes.css`, `theme-tokens.css`
- `public/hero/` — รูปสไลด์หน้าแรก

## ทดสอบ
```bash
docker exec smart_classroom_frontend npx tsc --noEmit   # ตรวจชนิดข้อมูล
docker exec smart_classroom_frontend npx vitest run     # unit test (*.test.ts)
```
