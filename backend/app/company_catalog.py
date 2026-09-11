"""
company_catalog.py — ความรู้บริษัท / สินค้า / บริการ / ติดต่อ ของ IWA RICH YOU D CO.,LTD.
รวบจากเว็บไซต์ https://iwa-web.onrender.com/ (ตัวแทนขายอย่างเป็นทางการ)

โครงสร้าง:
  COMPANY     — ภาพรวมบริษัท + ตัวเลข
  SERVICES    — 5 บริการหลัก
  PRODUCTS    — รายการสินค้าทั้งหมด (จัดหมวด)
  CONTACT     — ช่องทางติดต่อ

ใช้เป็น context ให้ LINE chatbot ตอบเรื่องสินค้า/ขาย/สอบถามได้ (grounded, ไม่สร้างเอง)
"""
import re
import difflib

COMPANY = {
    "name": "บริษัท ไอว่า ริช ยู ดี จำกัด (IWA RICH YOU D CO.,LTD.)",
    "tagline": "ICT Solutions · Digital Learning",
    "about": (
        "พันธมิตรด้านเทคโนโลยีและสื่อการเรียนรู้ มุ่งนำเทคโนโลยีที่เหมาะสมไปใช้งานจริง "
        "ในสถานศึกษาและองค์กร เน้นคุณภาพ ความเหมาะสมของระบบ และการสนับสนุนผู้ใช้งาน "
        "พร้อมเป็นพันธมิตรที่เชื่อถือได้ทุกขั้นตอน"
    ),
    "stats": {"ประสบการณ์": "16+ ปี", "ลูกค้า": "521+ ราย", "โซลูชันที่ส่งมอบ": "52+"},
    "partners": [
        "Picaro English", "Vantage Essential English", "Phonics Hero",
        "Digital Library@School", "CEFR (Common European Framework)",
    ],
    "values": [
        "ICT Solutions — โครงสร้างพื้นฐานและระบบดิจิทัล",
        "Digital Learning — สื่อการเรียนรู้และหลักสูตรดิจิทัล",
        "Professional Team — ทีมงานให้คำปรึกษาและดูแลระบบ",
        "After-sales Service — บริการดูแลหลังการติดตั้ง",
    ],
}

SERVICES = [
    {
        "id": "network",
        "name": "Network Infrastructure & Design",
        "desc": "ออกแบบและวางระบบเครือข่าย",
        "items": ["LAN / Fiber Optic", "Server และ Network Security",
                  "Smart Classroom Solution", "Digital Language Lab"],
    },
    {
        "id": "software",
        "name": "Software & Application Development",
        "desc": "พัฒนาระบบและแอปพลิเคชัน",
        "items": ["Custom Software", "Mobile & Web Application", "System Integration",
                  "Learning Management System (LMS)", "พัฒนา AI Application"],
    },
    {
        "id": "maintenance",
        "name": "IT Maintenance Service",
        "desc": "บริการดูแลรักษาและบำรุงระบบ",
        "items": ["บริการดูแลรายเดือน–รายปี", "ตรวจเช็กระบบและกู้คืนข้อมูล",
                  "ดูแลอุปกรณ์และซอฟต์แวร์"],
    },
    {
        "id": "supply",
        "name": "Hardware & Software Supply",
        "desc": "จัดจำหน่ายอุปกรณ์และซอฟต์แวร์",
        "items": ["อุปกรณ์คอมพิวเตอร์และซอฟต์แวร์ลิขสิทธิ์", "Interactive Smart Display",
                  "สื่อมัลติมีเดียเพื่อการศึกษา"],
    },
    {
        "id": "training",
        "name": "ICT Training & Seminar",
        "desc": "อบรมและสัมมนา",
        "items": ["อบรมการใช้งานระบบและซอฟต์แวร์", "อบรม Smart Classroom / Language Lab",
                  "อบรมสื่อการเรียนรู้และ CEFR"],
    },
]

# ── สินค้า: แต่ละหมวดมี products; แต่ละ product: name, cat, summary, tags ──
PRODUCT_CATEGORIES = [
    {
        "id": "children-english",
        "name": "หลักสูตรภาษาอังกฤษสำหรับเด็ก (Children's English)",
        "products": [
            {"name": "Phonics Hero",
             "summary": "หลักสูตรภาษาอังกฤษสำหรับเด็กวัยเริ่มต้น ฝึกการอ่านออกเสียง (Phonics) อย่างเป็นระบบ",
             "tags": ["phonics", "โฟนิก", "โฟนิค", "ออกเสียง", "หลักสูตรเด็ก", "อ่านภาษาอังกฤษ"],
             "img": "https://iwa-web.onrender.com/assets/img/products/phonics-hero.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "Picaro English",
             "summary": "หลักสูตรภาษาอังกฤษสำหรับเด็ก ใช้แนวคิด Inspire · Motivate · Enjoy เรียนรู้ผ่านกิจกรรม",
             "tags": ["picaro", "พิคาโร", "ปิคาโร", "หลักสูตรเด็ก", "ภาษาอังกฤษ"],
             "img": "https://iwa-web.onrender.com/assets/img/products/picaro-overview.jpg",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
        ],
    },
    {
        "id": "communicative-english",
        "name": "หลักสูตรภาษาอังกฤษเพื่อการสื่อสาร (Communicative English)",
        "products": [
            {"name": "Vantage Connected Learn Social",
             "summary": "เรียนภาษาอังกฤษเพื่อการสื่อสารตามกรอบ CEFR พร้อมการเรียนแบบโต้ตอบและติดตามความก้าวหน้า",
             "tags": ["vantage", "แวนเทจ", "cefr", "เพื่อการสื่อสาร", "communicative", "โต้ตอบ"],
             "img": "https://iwa-web.onrender.com/assets/img/products/vantage-connected-learn-social.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
        ],
    },
    {
        "id": "preschool-multimedia",
        "name": "สื่อมัลติมีเดียระดับปฐมวัย (Preschool Multimedia)",
        "products": [
            {"name": "Click2Plearn",
             "summary": "สื่อมัลติมีเดียสำหรับกิจกรรมการเรียนรู้ของเด็กปฐมวัย ชวนเด็กสำรวจ เรียนรู้ และลงมือทำตามจังหวะผู้สอน",
             "tags": ["click2plearn", "คลิก", "ปฐมวัย", "เด็กเล็ก", "อนุบาล", "กิจกรรม"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/click2plearn.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "พัฒนาทักษะการใช้ภาษา (ACTIV@TEACH · LANGUAGE)",
             "summary": "โปรแกรมสื่อมัลติมีเดียพัฒนาทักษะการใช้ภาษาสำหรับเด็กปฐมวัย",
             "tags": ["ภาษา", "activ@teach", "activateach", "ปฐมวัย"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/activateach-thai.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "พัฒนาทักษะทางคณิตศาสตร์ (ACTIV@TEACH · MATH)",
             "summary": "โปรแกรมสื่อมัลติมีเดียสำหรับกิจกรรมการเรียนรู้ด้านคณิตศาสตร์ระดับปฐมวัย",
             "tags": ["คณิต", "คณิตศาสตร์", "เลข", "ปฐมวัย"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/activateach-math.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "พัฒนาทักษะทางวิทยาศาสตร์ (ACTIV@TEACH · SCIENCE)",
             "summary": "โปรแกรมสื่อมัลติมีเดียสำหรับกิจกรรมการเรียนรู้ด้านวิทยาศาสตร์ระดับปฐมวัย",
             "tags": ["วิทย์", "วิทยาศาสตร์", "ปฐมวัย"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/activateach-science.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "พัฒนาทักษะกระบวนการคิด (ACTIV@TEACH · THINKING)",
             "summary": "โปรแกรมสื่อมัลติมีเดียเสริมกระบวนการคิดและเชาวน์ปัญญาสำหรับเด็กปฐมวัย",
             "tags": ["กระบวนการคิด", "เชาวน์", "คิด", "ปฐมวัย"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/activateach-thinking.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "ชุดอาเซียนน่ารู้",
             "summary": "สื่อมัลติมีเดียประกอบการเรียนรู้เรื่องอาเซียนสำหรับเด็กปฐมวัย",
             "tags": ["อาเซียน", "asean", "ปฐมวัย", "สังคม"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/asean.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "Smart Quiz v1.0",
             "summary": "คลังข้อสอบและระบบวัดผลสำหรับเด็กปฐมวัย ใช้ประกอบการประเมินตามกิจกรรมในชั้นเรียน",
             "tags": ["smart quiz", "ข้อสอบ", "วัดผล", "ประเมิน", "แบบทดสอบ", "assessment"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/smart-quiz.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "E-Learning สำหรับครูปฐมวัย",
             "summary": "บทเรียนอิเล็กทรอนิกส์รูปแบบมัลติมีเดียและเครื่องมือจัดการการเรียนรู้สำหรับครูปฐมวัย",
             "tags": ["e-learning", "อีเลิร์นนิ่ง", "ครู", "ปฐมวัย", "บทเรียนออนไลน์"],
             "img": "https://iwa-web.onrender.com/assets/img/products/preschool/elearning-teacher.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
        ],
    },
    {
        "id": "primary-multimedia",
        "name": "สื่อมัลติมีเดียระดับประถมศึกษา (Primary Multimedia)",
        "products": [
            {"name": "Digital Library@School (คลังสื่อดิจิทัล)",
             "summary": "คลังสื่อดิจิทัลครอบคลุม 8 กลุ่มสาระการเรียนรู้ สำหรับนักเรียน ป.1–ป.6 ใช้เป็นสื่อประกอบการเรียนและค้นหาเนื้อหาได้สะดวก",
             "tags": ["digital library", "ดิจิทัลไลบรารี", "คลังสื่อ", "ประถม", "ห้องสมุด", "dls"],
             "img": "https://iwa-web.onrender.com/assets/img/products/primary/digital-library-school.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "อ่านออก เขียนได้ ง่ายนิดเดียว",
             "summary": "สื่อมัลติมีเดียพัฒนาทักษะการอ่าน การเขียน และภาษาไทยระดับประถมศึกษา",
             "tags": ["ภาษาไทย", "อ่านออกเขียนได้", "อ่าน", "เขียน", "ประถม"],
             "img": "https://iwa-web.onrender.com/assets/img/products/primary/thai-primary.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "โปรแกรมพัฒนาทักษะคณิตศาสตร์",
             "summary": "สื่อมัลติมีเดียเสริมการเรียนรู้คณิตศาสตร์ระดับประถมศึกษา",
             "tags": ["คณิต", "คณิตศาสตร์", "เลข", "ประถม"],
             "img": "https://iwa-web.onrender.com/assets/img/products/primary/math-primary.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "โปรแกรมพัฒนาทักษะวิทยาศาสตร์",
             "summary": "สื่อมัลติมีเดียเสริมการเรียนรู้วิทยาศาสตร์ระดับประถมศึกษา",
             "tags": ["วิทย์", "วิทยาศาสตร์", "ประถม"],
             "img": "https://iwa-web.onrender.com/assets/img/products/primary/science-primary.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
        ],
    },
    {
        "id": "smart-board",
        "name": "Iwa AiBoard (จออัจฉริยะ Interactive Display)",
        "products": [
            {"name": "Iwa AiBoard 65″",
             "summary": "จออัจฉริยะ All-in-One ขนาด 65 นิ้ว 4K UHD ใช้เรียน/ประชุม/นำเสนอ",
             "tags": ["65", "65 นิ้ว", "aiboard", "ai board", "จอ", "สมาร์ทบอร์ด", "interactive"],
             "img": "https://iwa-web.onrender.com/assets/img/page-65.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "Iwa AiBoard 75″",
             "summary": "จออัจฉริยะ All-in-One ขนาด 75 นิ้ว 4K UHD ฟังก์ชัน All-in-One",
             "tags": ["75", "75 นิ้ว", "aiboard", "ai board", "จอ", "สมาร์ทบอร์ด"],
             "img": "https://iwa-web.onrender.com/assets/img/page-75.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
            {"name": "Iwa AiBoard 86″",
             "summary": "จออัจฉริยะ All-in-One ขนาด 86 นิ้ว 4K UHD สำหรับเรียน/ประชุม/นำเสนอ 3840×2160, IR Touch, Dual OS, AI Camera, Multi-Screen Share, Wi-Fi 6",
             "tags": ["86", "86 นิ้ว", "aiboard", "ai board", "จอ", "สมาร์ทบอร์ด", "interactive"],
             "img": "https://iwa-web.onrender.com/assets/img/page-86.png",
             "price": None,
             "link": "https://iwa-web.onrender.com/products/"},
        ],
        "common": (
            "จุดเด่น Iwa AiBoard: หน้าจอ 4K Touch (3840×2160), Anti-Glare + Toughened Glass, "
            "Dual OS, AI Camera, Multi-Screen Share, Wi-Fi 6, Whiteboard Software, อายุการใช้งานจอ ~50,000 ชม."
        ),
    },
]

# ── รวมทุกสินค้าเป็น list แบน ง่ายต่อค้นหา ──
ALL_PRODUCTS = []
for cat in PRODUCT_CATEGORIES:
    for p in cat["products"]:
        ALL_PRODUCTS.append({"name": p["name"], "summary": p["summary"],
                             "tags": p["tags"], "category": cat["name"], "cat_id": cat["id"],
                             "img": p.get("img"), "price": p.get("price"),
                             "link": p.get("link")})

CONTACT = {
    "company": "บริษัท ไอว่า ริช ยู ดี จำกัด (IWA RICH YOU D CO.,LTD.)",
    "phones": ["099-626-9787", "082-731-8082"],
    "address": "222/56 หมู่ 7 ตำบลนิคมสร้างตนเอง อำเภอเมือง จังหวัดลพบุรี 15110",
    "email": "supannee@iwarichyoudee.com",
    "line_id": "@590cbneh",
    "hours": "จันทร์–ศุกร์ เวลาทำการปกติ (แนะนำติดต่อทาง LINE/โทรก่อน)",
    "website": "https://iwa-web.onrender.com/",
}

# ── คำ/หัวข้อที่บอกว่าเป็นคำถามเชิงธุรกิจ/สินค้า (ต่างจากแจ้งซ่อม) ──
BUSINESS_KEYWORDS = [
    "ซื้อ", "ขาย", "ราคา", "โปรโมชั่น", "โปร", "สั่ง", "order", "inquire", "สอบถาม",
    "สินค้า", "product", "ผลิตภัณฑ์", "ขายส่ง", "จัดซื้อ", "อยากได้", "อยากรู้", "สนใจ",
    "catalog", "แคตตาล็อก", "ไดเรกทอรี", "รายการ", "ข้อมูลสินค้า", "สเปก", "spec",
    "demo", "ทดลองใช้", "ใบเสนอราคา", "quotation", "quo", "ติดต่อ", "ติดต่อเรา",
    "address", "ที่อยู่", "เบอร์", "โทร", "line", "อีเมล", "email", "แมสเซนเจอร์",
    "บริษัท", "company", "องค์กร", "iwa", "rich you", "บริการ", "service", "โซลูชัน",
    "solution", "อบรม", "training", "สัมมนา", "seminar", "หลักสูตร", "course",
    "อังกฤษ", "english", "cefr", "ปฐมวัย", "preschool", "อนุบาล", "ประถม", "primary",
    "มัลติมีเดีย", "multimedia", "สื่อ", "aiboard", "ai board", "สมาร์ทบอร์ด", "smart board",
    "จอ", "interactive", "language lab", "lms", "ห้องเรียน", "smart classroom",
    "เรียน", "ฝึกอบรม", "หลักสูตร", "ครุภัณฑ์", "ติดตั้ง",
    "ดูแลรักษา", "บำรุง", "เครือข่าย", "network", "จัดจำหน่าย", "ซัพพลาย", "จำหน่ายอุปกรณ์",
    "net", "ระบบเน็ต", "maintenance", "เมนเทน", "ซ่อมบำรุง", "กู้คืน",
]

# คำที่บอกว่าเป็นอาการ/แจ้งซ่อม (มีน้ำหนักกว่า กันสับสน)
_REPAIR_STRONG = ["แจ้งซ่อม", "ซ่อม", "ช่าง", "พัง", "เสีย", "ไม่ติด", "ไม่ทำงาน", "มีปัญหา",
                  "ไม่เปิด", "ไม่มีภาพ", "ไม่มีเสียง", "ค้าง", "จอดำ", "เข้าไม่ได้", "หลุด",
                  "fehler", "error", "บั๊ก", "bug", "อาการ", "ไม่ขึ้น", "ไม่ได้ยิน", "หน้าจอดำ"]


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def _fuzzy_product_names(query: str) -> set:
    """คืนชื่อสินค้าที่สะกดใกล้เคียงกับคำถาม (รับคำผิด เช่น 'aboard'/'aiboradas' → AiBoard)"""
    t = _norm(query)
    words = [w for w in re.split(r"[^a-z0-9]+", t) if len(w) >= 3]
    if not words:
        return set()
    hits = set()
    for p in ALL_PRODUCTS:
        aliases = set(re.findall(r"[a-z0-9]+", _norm(p["name"])))
        aliases.update(re.findall(r"[a-z0-9]+", _norm(p.get("category", ""))))
        aliases.update(a for a in re.findall(r"[a-z0-9]+", _norm(" ".join(p.get("tags", [])))) if len(a) >= 4)
        for al in aliases:
            if len(al) < 4:
                continue
            for w in words:
                if difflib.SequenceMatcher(None, w, al).ratio() >= 0.6:
                    hits.add(p["name"])
    return hits


def classify(text: str) -> str:
    """จำแนกเจตนา: 'repair' (แจ้งซ่อม/อาการ) | 'business' (สินค้า/บริการ/ติดต่อ) | 'other'
    repair strong ตรวจก่อนเสมอ (คำว่า 'จอ'/'จอไม่ติด' ต้องเป็น repair)"""
    t = _norm(text)
    # 1) อาการ/แจ้งซ่อมชัดเจน → repair (ชนะเสมอ)
    if any(w in t for w in _REPAIR_STRONG):
        return "repair"
    # 2) ไม่มีคำอาการ → ถ้ามีคำ business/สินค้า → business
    if any(k in t for k in BUSINESS_KEYWORDS):
        return "business"
    # 3) พูดถึงชื่อสินค้าจริง (tag ตรง) เช่น 'Smart Quiz คืออะไร' → business
    if any(tag in t for p in ALL_PRODUCTS for tag in p["tags"]):
        return "business"
    # 4) ชื่อสินค้าสะกดผิดเล็กน้อย (aboard/aiboradas → AiBoard) → business
    if _fuzzy_product_names(text):
        return "business"
    return "other"


def search_products(query: str) -> list:
    """ค้นหาสินค้าจากชื่อ/แท็ก/หมวด ตรงตามคำถาม"""
    t = _norm(query)
    q_words = [w for w in re.split(r"[^a-z0-9ก-๙]+", t) if len(w) >= 2]
    results = []
    for p in ALL_PRODUCTS:
        hay = _norm(p["name"] + " " + " ".join(p["tags"]) + " " + p["category"])
        score = sum(1 for w in q_words if w in hay)
        if score or any(tag in t for tag in p["tags"]):
            results.append((score, p))
    results.sort(key=lambda x: -x[0])
    result = [p for _, p in results]
    # ต่อท้ายสินค้าที่สะกดผิดเล็กน้อย แต่ยังไม่ติดในผล (เช่น aboard → AiBoard)
    names = {p["name"] for p in result}
    for p in ALL_PRODUCTS:
        if p["name"] in _fuzzy_product_names(query) and p["name"] not in names:
            result.append(p)
    return result


def find_product(name_query: str):
    """เจอสินค้าตัวเดียวชัดเจน → คืน dict product (หรือ None)"""
    res = search_products(name_query)
    if not res:
        return None
    # ถ้าคำถามระบุชื่อชัดพอ คืนตัวแรกที่เจอ
    return res[0]


def company_summary_text() -> str:
    stats = " · ".join(f"{k} {v}" for k, v in COMPANY["stats"].items())
    return (f"🏢 **{COMPANY['name']}**\n"
            f"{COMPANY['tagline']}\n"
            f"สถิติ: {stats}\n\n"
            f"{COMPANY['about']}\n\n"
            f"ทีมงานของเราครอบคลุม: {' | '.join(COMPANY['values'])}")


def find_service(service_id: str):
    """หาบริการตาม id ('network','software','maintenance','supply','training')"""
    for s in SERVICES:
        if s["id"] == service_id:
            return s
    return None


def contact_text() -> str:
    c = CONTACT
    return (f"ติดต่อ {c['company']}\n"
            f"📞 โทร: {', '.join(c['phones'])}\n"
            f"📍 ที่อยู่: {c['address']}\n"
            f"✉️ อีเมล: {c['email']}\n"
            f"💬 LINE: {c['line_id']}\n"
            f"🕘 เวลาทำการ: {c['hours']}\n"
            f"🌐 เว็บ: {c['website']}")
