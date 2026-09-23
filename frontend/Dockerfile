FROM node:20-alpine

WORKDIR /app

# คัดลอก package files ก่อน เพื่อใช้ cache สำหรับ npm install
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# คัดลอก source code ทั้งหมด
COPY . .

# Vite ฝังค่า env ลงใน bundle "ตอน build" ไม่ใช่ตอน run
# → ต้องรับผ่าน build arg (การตั้ง environment ใน compose/Railway ไม่มีผลกับ bundle)
# ห้าม default เป็น localhost: ค่านี้ถูกฝังลงบันเดิล แล้วเบราว์เซอร์ของผู้ใช้จะยิงไป
# localhost ของเครื่องตัวเอง (คำขอไม่เคยถึง backend) — ปล่อยว่างไว้เพื่อให้ client.ts
# fallback เป็น '/api' แบบ same-origin แล้วให้ proxy ของ vite preview ส่งต่อไป backend
ARG VITE_API_URL=""
ENV VITE_API_URL=$VITE_API_URL

# Build production bundle — ถ้า build พังต้องให้ image build พังไปเลย
# (เดิมมี `|| echo "No build script found"` ทำให้ได้ image ที่ไม่มี dist/
#  แล้ว vite preview เสิร์ฟหน้าเปล่าโดยไม่มีใครรู้ว่า build ล้มเหลว)
RUN npm run build

EXPOSE 5173

# vite preview เสิร์ฟไฟล์จาก dist/ — ฟัง port จาก env PORT (Railway inject) หรือ default 5173
CMD ["sh", "-c", "npx vite preview --host 0.0.0.0 --port ${PORT:-5173} --strictPort"]