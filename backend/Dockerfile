FROM python:3.11-slim

# ติดตั้ง lib สำหรับ psycopg2 (PostgreSQL driver)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ติดตั้ง Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copied application code
COPY app ./app
COPY scripts ./scripts

# สร้างโฟลเดอร์ data สำหรับ SQLite (fallback)
RUN mkdir -p data

EXPOSE 8000

# รัน uvicorn — ฟัง port จาก env PORT (Railway inject ไว้, default 8080) เพื่อให้ Railway router เข้าถึงได้
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
