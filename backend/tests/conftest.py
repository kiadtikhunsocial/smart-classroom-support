"""ทำให้ `import app...` ใช้ได้จากในโฟลเดอร์ tests โดยไม่ต้องติดตั้งแพ็กเกจ"""

import pathlib
import sys

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))