"""เทสต์ชั้น NLU ของแชทบอท — ล็อกพฤติกรรมที่เคยตอบผิดเรื่องไม่ให้กลับมาอีก

ทุกเคสในไฟล์นี้คือข้อความแนวที่ผู้ใช้พิมพ์เข้ามาจริง และเคยถูกตอบผิดประเด็น
เพราะการเทียบคำแบบ substring ในภาษาไทย (คำสั้นไปโผล่กลางคำอื่น)

หมายเหตุ: ชื่อฟังก์ชันเป็นภาษาไทยได้ แต่ห้ามมีช่องว่าง — ใช้ _ แทน
"""

from app import chatbot_nlu as nlu


class TestNormalize:
    def test_ตัดคำลงท้ายสุภาพและอักษรซ้ำ(self):
        assert nlu.normalize("ไม่ติดดดดค่ะ") == "ไม่ติด"
        assert nlu.normalize("จอดำครับผม").startswith("จอดำ")

    def test_แก้พิมพ์ผิดสระแอ(self):
        assert "แจ้งซ่อม" in nlu.compact("เเจ้งซ่อม")

    def test_ตัดวรรคตอนและอีโมจิ(self):
        assert nlu.compact("แจ้งซ่อม!! 🔧") == "แจ้งซ่อม"


class TestOutOfScope:
    def test_คำถามนอกขอบเขตจริง(self):
        assert nlu.is_out_of_scope("วันนี้ฝนตกไหม")
        assert nlu.is_out_of_scope("ขอสูตรอาหารหน่อย")
        assert nlu.is_out_of_scope("เลขหวยงวดนี้ออกอะไร")
        assert nlu.is_out_of_scope("ช่วยดูดวงให้หน่อย")

    def test_งานของระบบต้องไม่ถูกตีเป็นนอกขอบเขต(self):
        # "อากาศ" ซ่อนใน "เครื่องปรับอากาศ"
        assert not nlu.is_out_of_scope("เครื่องปรับอากาศห้อง 301 ไม่เย็น")
        # "หนัง" ซ่อนใน "หนังสือ"
        assert not nlu.is_out_of_scope("มีหนังสือเรียนขายไหม")
        # "เกม" ซ่อนใน "เกมการศึกษา"
        assert not nlu.is_out_of_scope("มีเกมการศึกษาสำหรับอนุบาลไหม")
        # "เพลง" ซ่อนใน "เพลงเด็ก"
        assert not nlu.is_out_of_scope("อยากได้สื่อเพลงเด็กปฐมวัย")
        # แอร์เสีย = งานซ่อม ไม่ใช่เรื่องพยากรณ์อากาศ
        assert not nlu.is_out_of_scope("แอร์ห้องประชุมเสีย")


class TestAdminContact:
    def test_ขอคุยกับคนจริง(self):
        assert nlu.is_admin_contact("ขอคุยกับแอดมิน")
        assert nlu.is_admin_contact("ขอเบอร์ติดต่อ")
        assert nlu.is_admin_contact("ขอไลน์ทีมงาน")

    def test_ประโยคเล่าความต้องไม่ถูกตอบเป็นช่องทางติดต่อ(self):
        assert not nlu.is_admin_contact("รอทีมงานติดต่อกลับอยู่")
        assert not nlu.is_admin_contact("เจ้าหน้าที่จะมาวันไหน")

    def test_ถามสถานะงานต้องให้flow_ติดตามงานชนะ(self):
        assert not nlu.is_admin_contact("งานซ่อม T0001 ถึงไหนแล้ว ติดต่อไม่ได้เลย")
        assert not nlu.is_admin_contact("ขอทราบสถานะ ticket 20450")


class TestAmbiguity:
    def test_สัญญาณสองเรื่องเท่ากันคือกำกวมจริง(self):
        tied = nlu.ambiguous_intents("แอร์เสีย อยากซื้อใหม่")
        assert tied == ["product", "repair"]
        prompt = nlu.clarify_prompt("แอร์เสีย อยากซื้อใหม่")
        assert prompt is not None
        assert "แจ้งซ่อม" in prompt["quick_replies"]
        assert "สินค้า" in prompt["quick_replies"]

    def test_ข้อความชัดเจนไม่ต้องถามกลับ(self):
        assert nlu.clarify_prompt("จอโปรเจคเตอร์ห้อง 202 ไม่ติด") is None
        assert nlu.clarify_prompt("Iwa AiBoard 86 นิ้ว ราคาเท่าไหร่") is None

    def test_ข้อความสั้นไม่มีสัญญาณให้ถามกลับแบบเจาะจง(self):
        prompt = nlu.clarify_prompt("ช่วยด้วย")
        assert prompt is not None
        assert len(prompt["quick_replies"]) >= 3

    def test_ประโยคยาวที่มีอาการชัดไม่ถือว่าคลุมเครือ(self):
        assert not nlu.is_vague("ทีวีห้องเรียน 205 เปิดไม่ได้ตั้งแต่เช้า")


class TestCorrectCommand:
    def test_คำสั่งสะกดเพี้ยน(self):
        assert nlu.correct_command("เเจ้วซ่อม") == "แจ้งซ่อม"
        assert nlu.correct_command("สถาน") == "สถานะ"
        assert nlu.correct_command("ตืดต่อ") == "ติดต่อ"

    def test_คำสั่งตรงตัว(self):
        assert nlu.correct_command("ติดตามงาน") == "สถานะ"
        assert nlu.correct_command("ยกเลิก") == "ยกเลิก"

    def test_ประโยคเล่าอาการต้องไม่ถูกบิดเป็นคำสั่ง(self):
        assert nlu.correct_command("จอโปรเจคเตอร์ห้อง 202 ไม่ติดเลยครับ") is None
        assert nlu.correct_command("") is None


class TestUnderstand:
    def test_คืนโครงสร้างครบสำหรับcore(self):
        info = nlu.understand("แอร์ห้อง 301 ไม่เย็น")
        assert info["out_of_scope"] is False
        assert "repair" in info["scores"]
        assert info["compact"]