import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

/** URL ที่ชี้กลับมาเครื่องของผู้ใช้เอง — ใช้ได้แค่ตอน dev ห้ามฝังลง production build */
function isLoopback(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1|\[::1\]|0\.0\.0\.0)(:|\/|$)/i.test(url);
}

export default defineConfig(({ mode }) => {
  // loadEnv อ่าน .env, .env.[mode], .env.local และ env ของแพลตฟอร์ม (prefix '' = ไม่กรองชื่อ)
  // เดิมโค้ดอ่านแค่ process.env จึงข้ามไฟล์ .env ทั้งหมด
  const env = loadEnv(mode, process.cwd(), '');
  let apiUrl = (env.VITE_API_URL || '').trim().replace(/\/+$/, '');

  const isProd = mode === 'production';

  if (isProd && apiUrl && isLoopback(apiUrl)) {
    // กันเคสจริงที่เคยเกิด: .env ในเครื่อง dev ตั้ง localhost ไว้ แล้วค่านี้ถูกฝังลงบันเดิล
    // ที่ deploy → เบราว์เซอร์ผู้ใช้ยิงไป localhost ของตัวเอง คำขอไม่เคยถึง backend
    console.warn(
      `\n[vite] ไม่ใช้ VITE_API_URL="${apiUrl}" ใน production build เพราะเป็น URL แบบ loopback` +
        '\n       → บันเดิลจะเรียก API แบบ same-origin ที่ /api แทน\n'
    );
    apiUrl = '';
  }

  if (isProd && !apiUrl) {
    console.warn(
      '\n[vite] ไม่ได้ตั้ง VITE_API_URL สำหรับ production build' +
        '\n       frontend จะเรียก API แบบ same-origin ที่ /api' +
        '\n       ถ้า backend อยู่คนละโดเมน (เช่น Render) ต้องตั้ง VITE_API_URL' +
        ' ใน environment variables ของแพลตฟอร์มที่ deploy\n'
    );
  }

  return {
    define: {
      // ค่าว่าง = ไม่ได้ระบุ → client.ts fallback เป็น '/api' (ดู resolveApiBase)
      __VITE_API_URL__: JSON.stringify(apiUrl),
    },
    plugins: [react()],
    build: {
      rollupOptions: {
        output: {
          // แยกไลบรารีที่ใหญ่และไม่ค่อยเปลี่ยนออกจากโค้ดแอป
          // ผลพลอยได้: เบราว์เซอร์แคช vendor ไว้ได้ ดีพลอยรอบถัดไปโหลดแค่ก้อนแอป
          // (html5-qrcode ไม่ต้องใส่ที่นี่ — ถูก dynamic import อยู่แล้ว
          //  ใน ScanPage/PublicNoLoginReportView จึงแตกก้อนเองตอนเปิดกล้อง)
          //
          // ใช้แบบฟังก์ชันเพราะ recharts ลาก d3-* / victory-vendor มาด้วย
          // ถ้าจับเป็นก้อนเดียวจะโตเกิน 500 kB; แยก d3 ออกให้แต่ละก้อนเล็กลง
          // path บน Windows เป็น backslash จึงต้องรับทั้ง / และ \ ในแพตเทิร์น
          manualChunks(id: string) {
            if (!/node_modules/.test(id)) return undefined;
            const inPkg = (name: string) =>
              new RegExp(`node_modules[\\\\/]${name}[\\\\/]`).test(id);

            if (
              inPkg('victory-vendor') ||
              /node_modules[\\/]d3-[^\\/]+[\\/]/.test(id) ||
              inPkg('internmap') ||
              inPkg('delaunator') ||
              inPkg('robust-predicates')
            ) {
              return 'vendor-d3';
            }
            if (inPkg('recharts')) return 'vendor-charts';
            if (inPkg('react') || inPkg('react-dom') || inPkg('scheduler')) {
              return 'vendor-react';
            }
            if (inPkg('qrcode') || inPkg('pngjs') || inPkg('dijkstrajs')) {
              return 'vendor-qrcode';
            }
            return undefined;
          },
        },
      },
    },
    server: {
      port: 5173,
      // ฟังทุก interface — จำเป็นเมื่อ dev server รันในคอนเทนเนอร์ (ไม่งั้น port mapping เข้าไม่ถึง)
      // รันบนเครื่องตรง ๆ ก็ยังเข้าที่ http://localhost:5173 ได้เหมือนเดิม
      host: true,
      strictPort: true,
      // bind mount จาก Windows/macOS ไม่ส่งอีเวนต์ inotify เข้าคอนเทนเนอร์ → ต้อง poll
      // เปิดด้วย CHOKIDAR_USEPOLLING=true (ตั้งไว้ใน docker-compose.yml) เท่านั้น
      // เพื่อไม่ให้เครื่อง dev ปกติต้องเสีย CPU กับการวนเช็คไฟล์
      watch: process.env.CHOKIDAR_USEPOLLING
        ? { usePolling: true, interval: 300 }
        : undefined,
      proxy: {
        // dev: '/api' → backend ที่พอร์ต 8000 ทำให้ไม่ต้องพึ่ง CORS เลย
        '/api': {
          // รันบนเครื่องตรง ๆ ใช้ 127.0.0.1 ไม่ใช่ 'localhost': Node 17+ resolve localhost
          // เป็น ::1 ก่อน ถ้า uvicorn bind ไว้แค่ 127.0.0.1 พร็อกซีจะได้ ECONNREFUSED
          // แล้วตอบ 500 / ตัดการเชื่อมต่อ ซึ่งเบราว์เซอร์แสดงเป็น "Failed to fetch"
          // ในคอนเทนเนอร์: API_PROXY_TARGET=http://backend:8000 (ชื่อ service ใน compose)
          target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          // พิมพ์สาเหตุจริงลง terminal ของ vite เวลาพร็อกซีล้ม (เดิมเห็นแค่ 500 เปล่า ๆ)
          configure: (proxy) => {
            proxy.on('error', (err) => {
              console.error(
                `[vite proxy] ส่งต่อ /api ไป backend ไม่สำเร็จ: ${err.message}` +
                  ` — target=${process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'}` +
                  ' (ตรวจว่า backend รันอยู่จริงที่ปลายทางนี้)'
              );
            });
          },
        },
        '/uploads': {
          target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
    preview: {
      allowedHosts: ['.up.railway.app', '.vercel.app', 'localhost'],
      // vite preview (ใช้ในคอนเทนเนอร์ frontend) เสิร์ฟไฟล์ dist และ "ไม่ได้" ใช้ server.proxy
      // ถ้าไม่มีบล็อกนี้ คำขอ /api แบบ same-origin จะตกที่ตัวเสิร์ฟ static แล้วตอบ 500
      // ซึ่งเบราว์เซอร์แสดงเป็น "Failed to fetch"
      // target มาจาก env ตอน "รัน" (ไม่ใช่ตอน build):
      //   - docker compose : API_PROXY_TARGET=http://backend:8000 (ชื่อ service ในเครือข่าย)
      //   - รันบนเครื่องตรง ๆ : default 127.0.0.1:8000 (ไม่ใช้ 'localhost' เพราะ Node 17+
      //     resolve เป็น ::1 ก่อน ซึ่งอาจไม่ใช่โปรเซสที่ backend bind ไว้)
      proxy: {
        '/api': {
          target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          configure: (proxy) => {
            proxy.on('error', (err) => {
              console.error(
                `[vite preview proxy] ส่งต่อ /api ไป backend ไม่สำเร็จ: ${err.message}` +
                  ` — target=${process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000'}`
              );
            });
          },
        },
        '/uploads': {
          target: process.env.API_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
        },
      },
    },
  };
});
