FROM node:20-alpine

# Docker build cache: สร้าง layer แยกสำหรับ dependencies
WORKDIR /app

# คัดลอก package files ก่อน เพื่อใช้ cache สำหรับ npm install
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps

# คัดลอก source code ทั้งหมด
COPY . .

# Build production bundle (ถ้ามี script ใน package.json)
RUN npm run build --prefix /app 2>/dev/null || echo "No build script found, using dev mode"

EXPOSE 5173

# ใช้ vite preview สำหรับ production — ฟัง port จาก env PORT (Railway inject) หรือ default 5173
CMD ["sh", "-c", "npx vite preview --host 0.0.0.0 --port ${PORT:-5173} --strictPort"]
