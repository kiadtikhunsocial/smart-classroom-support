import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { initTheme } from "./theme";
import "./styles/global.css";
import "./styles/themes.css";
// ต้องโหลดท้ายสุด — เลเยอร์นี้ทับ token/สไตล์ของสองไฟล์ด้านบนด้วยลำดับ (ไม่ใช้ !important)
import "./styles/design-system.css";
// เลเยอร์ธีมสุดท้าย: นิยาม token ตาม [data-mode]/[data-accent] จึงต้องอยู่หลังสุดจริง ๆ
import "./styles/theme-tokens.css";
// แอนิเมชันเปลี่ยนหน้า/โหลด — ใช้ token สีจากไฟล์บน จึงโหลดต่อท้าย
import "./styles/motion.css";
// ดีไซน์ Calm / ทางการ — เลเยอร์สุดท้าย (ถอดได้ด้วยการลบบรรทัดนี้)
import "./styles/calm-ui.css";
import "./styles/workspace-ui.css";

// ทาธีมที่ผู้ใช้เลือกไว้ก่อน render — กันจอกระพริบเป็นธีมผิดตอนโหลด
initTheme();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);