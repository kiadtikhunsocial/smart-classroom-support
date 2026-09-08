"""setup.py — ติดตั้ง backend package (สำหรับ develop)"""
from setuptools import setup, find_packages

setup(
    name="smart-classroom-support-api",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "fastapi>=0.109.0",
        "uvicorn[standard]>=0.27.0",
        "sqlalchemy>=2.0.0",
        "pydantic>=2.6.0",
        "pydantic-settings>=2.1.0",
        "python-multipart>=0.0.9",
        "qrcode[pil]>=8.0",
        "Pillow>=10.2.0",
    ],
)
