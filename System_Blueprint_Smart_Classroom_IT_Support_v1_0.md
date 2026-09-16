## SYSTEM BLUEPRINT

ฉบับเต็ม v1.0

ระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะ

สำหรับห้องเรียน Smart Classroom

Online Repair Request and Intelligent IT Support System

for Smart Classroom

Development-ready System Design Blueprint

จัดทำจากเอกสารโครงการต้นฉบับ และขยายเป็นข้อกำหนดเชิงระบบสำหรับการพัฒนา Prototype / MVP

Version 1.0 | September 2026


## A. ข้อมูลควบคุมเอกสาร

| รายการ | รายละเอียด |
| --- | --- |
| ชื่อเอกสาร | System Blueprint - Smart Classroom IT Support & |
|   | Maintenance Platform |
| เวอร์ชัน | 1.0 |
| ประเภทเอกสาร | System Architecture / Development Blueprint |
| เอกสารต้นทาง | โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน |
|   | IT อัจฉริยะสำหรับ Smart Classroom |
| เป้าหมาย | ใช้เป็นกรอบกลางสำหรับนักศึกษา ผู้พัฒนา ผู้ดูแลระบบ และผู้ |
|   | ตรวจรับงาน |
| สถานะ | Draft for Development / Review |

## ขอบเขตของ Blueprint

เอกสารนี้รักษาขอบเขตหลักจากโครงการต้นฉบับ ได้แก่ ระบบแจ้งซ่อมออนไลน์, Ticket, QR Code, Chatbot/AI

Troubleshooting, Notification, Repair History, Dashboard และ Preventive Maintenance พร้อมเพิ่มราย

ละเอียดเชิงสถาปัตยกรรม ฐานข้อมูล สิทธิ์ผู้ใช้ API ความปลอดภัย การทดสอบ และ Deployment เพื่อให้สามารถนำไป พัฒนาระบบจริงได้


## B. สารบัญย่อ

| หมวด | หัวข้อหลัก |
| --- | --- |
| 1-5 | วิสัยทัศน์ระบบ / Scope / Roles / Architecture / |
|   | Technology Stack |
| 6-13 | Organization, Asset, QR, User Flow, Ticket, State |
|   | Machine, History |
| 14-22 | Assignment, Priority, AI, Knowledge Base, Repair |
|   | Resolution / History |
| 23-30 | LINE OA, Notification, n8n, Sitemap, |
|   | User/Technician/Ticket/Admin UI |
| 31-39 | Database, ERD, API, Dashboard, KPI, Preventive |
|   | Maintenance |
| 40-46 | Security, Audit, Attachments, Deployment, |
|   | Environments, Git, Testing |
| 47-54 | UAT, Acceptance, MVP/Phase 2, 8-week plan, DoD, |
|   | Master Blueprint, Design Rules, Deliverables |


## 1. เป้าหมายและวิสัยทัศน์ของระบบ

ระบบนี้ออกแบบให้เป็น Smart Classroom IT Support & Maintenance Platform ไม่ใช่เพียงแบบฟอร์มรับแจ้งซ่อม โดยเชื่อมวงจร Asset → Problem → AI Self-Service → Ticket → Technician → Repair → History → Knowledge → Analytics → Preventive Maintenance ให้เป็นระบบเดียว

Asset

↓

Problem

↓

AI / Self-Service

↓

Ticket

↓

Technician

↓

Repair

↓

Repair History

↓

Knowledge Base

↓

Analytics

↓

Preventive Maintenance

## หลักคิดกลาง

อุปกรณ์ (Asset) เป็นศูนย์กลาง และ Ticket ทุกใบเป็นส่วนหนึ่งของประวัติอุปกรณ์ ไม่ใช่ข้อมูลแจ้งซ่อมที่แยกขาดจากกัน

## 2. ขอบเขตระบบระดับสูง

| Module | ชื่อโมดูล | หน้าที่หลัก |
| --- | --- | --- |
| M01 | Identity & Access | User / Login / Role / Permission |
| M02 | Organization & School | หน่วยงาน โรงเรียน อาคาร ห้อง |
| M03 | Asset Management | อุปกรณ์ Smart Classroom และ QR |
| M04 | Support & AI | Chatbot / Troubleshooting / Self- |
|   |   | Service |
| M05 | Ticket Management | แจ้งปัญหา / Ticket / Status |
| M06 | Technician Operations | รับงาน / ซ่อม / Resolution |
| M07 | Notification & Automation | LINE OA / n8n / Webhook |
| M08 | Knowledge Base | คู่มือและวิธีแก้ปัญหา |
| M09 | Dashboard & Analytics | รายงาน / KPI / Statistics |
| M10 | Maintenance | Repair History / Preventive |
|   |   | Maintenance |


## 3. User Roles & Permission

เพื่อให้การใช้งานและการรักษาความปลอดภัยชัดเจน Blueprint กำหนด Role เชิงระบบ 6 กลุ่ม โดยใน MVP สามารถเริ่มเพียง

4 Role คือ User, Technician, Supervisor และ Admin

| Role | หน้าที่ |
| --- | --- |
| User / Teacher | แจ้งปัญหา ดู Ticket ใช้ AI Support และยืนยันผลการแก้ไข |
| School Coordinator | ดู Ticket ภายในโรงเรียนและช่วยประสานงาน |
| Technician | รับงาน ซ่อม บันทึกสาเหตุ วิธีแก้ และอัปเดตสถานะ |
| Supervisor | Assign งาน ควบคุม Queue และดูภาพรวม |
| Administrator | จัดการ Master Data, User, Asset, Knowledge Base, |
|   | Settings |
| Management | ดู Dashboard และรายงาน โดยไม่แก้ไขงานปฏิบัติการ |

## 3.1. Permission Matrix

| Function | User | Technician | Supervisor | Admin |
| --- | --- | --- | --- | --- |
| แจ้ง Ticket |   |   |   |   |
| ดู Ticket ตัวเอง |   |   |   |   |
| ดู Ticket ทั้งหมด | - | Assigned |   |   |
| รับงาน | - |   |   |   |
| Assign งาน | - | - |   |   |
| เปลี่ยนสถานะ | - |   |   |   |
| ปิด Ticket | Confirm |   |   |   |
| Asset Management | - | View | View |   |
| Knowledge Base | Read | Read | Edit |   |
| User Management | - | - | - |   |
| Dashboard | My | Assigned |   |   |


## 4. System Architecture

- Frontend A%0 LINE @G
H-2@I2#0

- Backend API @G8#'! Business Logic

- PostgreSQL @GA+%HI-!9%+%1 (System of Record)

- AI Service I--4 Knowledge Base A%042'2!%-

- n8n C
I*3+#11 Integration, Notification A%0 Scheduled Automation

- Dashboard -H2I-!9%22I-!9%+%1 D!H'#*#I22I-!9%A"B"D!H3@G

## 5. Technology Stack

| Layer | Technology / Recommendation |
| --- | --- |
| Frontend | React + TypeScript (Vite) |
| Backend | Python + FastAPI + SQLAlchemy |
| API | REST API |
| Database | PostgreSQL |
| Authentication | Email/Password; รองรับ LINE Login ในระยะต่อไป |
| Automation | n8n |
| LINE | LINE Messaging API |
| AI | Gemini API |
| QR | URL-based QR + Secure Token |
| Dashboard | React Web Dashboard; Prototype อาจใช้ Looker Studio |
| Deployment | Docker |
| Hosting | VPS / Cloud |
| Source Control | GitHub |


## ข้อกำหนดสำคัญ

n8n ไม่ควรเป็น Core Business Logic หรือ Core Database ของระบบ ให้ทำหน้าที่ Automation / Integration /

Notification เท่านั้น

## 6. Organization Structure

Organization

└── School

└── Building

└── Room

└── Asset

โครงสร้างนี้ทำให้ระบบรองรับหลายโรงเรียนตั้งแต่ต้น โดยไม่ต้องเปลี่ยน Data Model ครั้งใหญ่เมื่อขยายผล

## 7. Asset Management

Asset เป็น Core Entity ของระบบ ทุก Ticket ที่สามารถระบุอุปกรณ์ได้ควรผูกกับ Asset เพื่อให้เกิด Repair History

และการวิเคราะห์ Failure รายเครื่อง

| Field | ตัวอย่าง / ความหมาย |
| --- | --- |
| Asset ID | Primary key ภายในระบบ |
| Asset Code | BOARD-001 / BKK01-R401-BOARD-001 |
| Asset Category | Interactive Display / Computer / AP / Speaker |
| Brand / Model | ยี่ห้อและรุ่น |
| Serial Number | Serial จากผู้ผลิต |
| Location | School / Building / Room |
| Install / Purchase Date | วันที่ติดตั้ง / ซื้อ |
| Warranty | Start / End / Vendor |
| Asset Status | Active / Maintenance / Retired |
| QR Token | Token สำหรับ Resolve QR |
| Notes | ข้อมูลเพิ่มเติม |

## 7.1. Asset Coding Convention

แบบสั้น:

BOARD-001

แบบหลายโรงเรียน:

BKK01-R401-BOARD-001

## 8. QR Code Architecture

QR Code ไม่ควรเก็บรายละเอียดอุปกรณ์โดยตรง แต่เก็บ URL/Token เพื่อให้ Server เป็นผู้ Resolve ข้อมูล วิธีนี้ช่วยให้ ย้ายห้อง แก้ชื่อโรงเรียน หรือแก้ข้อมูล Asset ได้โดยไม่ต้องพิมพ์ QR ใหม่


```
https://support.domain.com/q/ABCD1234
│
Resolve QR Token
│
Asset = BOARD-001
School = A School A
Room = 401
```

## 8.1. QR Landing Actions

- AI1
+2

- -3A032 AI

- 9I-!9%-8#L

- 9 Ticket 5H@5H"'I- (@
20
9I!5*44L)

## 9. User Problem Flow

```
Scan QR
↓
Resolve Asset
↓
เลือกประเภทปัญหา + อธิบายอาการ + แนบรูป
↓
AI Troubleshooting
↓
แก้ไขได้? ── YES ──► Self-Service Case
│
NO
↓
Create Ticket
↓
Ticket Number + Notification
```

กรณีผู้ใช้ไม่ได้ Scan QR ต้องอนุญาตให้ค้นหา Asset หรือแจ้งแบบ General Ticket ได้ แต่ระบบควรกระตุ้นให้ระบุ

School/Room/Device ให้ครบที่สุด

## 10. Ticket Data Model

| กลุ่มข้อมูล | Fields หลัก |
| --- | --- |
| Identity | ticket_id, ticket_number |
| Reporter | reporter_id, contact |
| Location | school_id, room_id |
| Asset | asset_id |
| Problem | issue_category_id, problem_title, problem_description |
| Priority | user_priority, system_priority |
| Source | qr / web / line |
| AI Context | ai_session_id, self_service_attempted |
| Assignment | assigned_technician_id |

*หน้า 8 | โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะ*


| กลุ่มข้อมูล | Fields หลัก |
| --- | --- |
| State | status |
| Timestamps | created_at, assigned_at, started_at, completed_at, |
|   | closed_at |

## 11. Ticket Number

SC-YYYY-NNNNNN

ตัวอย่าง:

ฐานข้อมูลสามารถใช้ UUID เป็น Primary Key ภายใน แต่ผู้ใช้เห็น Ticket Number ที่อ่านง่ายและอ้างอิงทาง โทรศัพท์/LINE ได้

SC-2026-000001

## 12. Ticket State Machine

## กฎบังคับ

ไม่ควรให้ผู้ใช้เปลี่ยน Status แบบอิสระจาก Dropdown ทุกค่า แต่ต้องตรวจ Transition ที่ Backend เพื่อป้องกัน OPEN → CLOSED โดยไม่มีขั้นตอนและข้อมูล Resolution

## 12.1. Transition Rules

| From | Allowed To | เงื่อนไขสำคัญ |
| --- | --- | --- |
| OPEN | ASSIGNED / CANCELLED | มีผู้รับผิดชอบหรือเหตุผลยกเลิก |
| ASSIGNED | IN_PROGRESS / CANCELLED | Technician รับงาน |

*หน้า 9 | โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะ*


| From | Allowed To | เงื่อนไขสำคัญ |
| --- | --- | --- |
| IN_PROGRESS | WAITING_FOR_PARTS / | Complete ต้องมี Resolution |
|   | WAITING_FOR_USER / COMPLETED |   |
| WAITING_FOR_PARTS | IN_PROGRESS | อะไหล่พร้อม |
| WAITING_FOR_USER | IN_PROGRESS | ผู้ใช้ตอบกลับ/พร้อมทดสอบ |
| COMPLETED | CLOSED / IN_PROGRESS | ยืนยันแล้ว หรือ Reopen เมื่อยังมีปัญหา |

## 13. Ticket Status History

ticket_status_history

- \- id

- \- ticket_id

- \- from_status

- \- to_status

- \- changed_by

- \- changed_at

- \- comment

ทุกการเปลี่ยนสถานะต้องบันทึก History เพื่อใช้ Audit, Timeline, SLA, MTTR และวิเคราะห์ Bottleneck

## 14. Assignment System

Ticket → Unassigned Queue → Supervisor / Auto Rule → Technician → Accept Job

MVP สามารถใช้ Manual Assignment หรือให้ Technician รับงานเองก่อน เมื่อระบบนิ่งค่อยเพิ่ม Auto Assignment

ตามพื้นที่ ประเภทอุปกรณ์ ภาระงาน หรือ Skill

| Field | รายละเอียด |
| --- | --- |
| ticket_id | Ticket ที่มอบหมาย |
| technician_id | ผู้รับงาน |
| assigned_by | ผู้มอบหมาย |
| assigned_at | เวลามอบหมาย |
| unassigned_at | เวลาถอดงาน (ถ้ามี) |

## 15. Priority Engine

ผู้แจ้งสามารถระบุความเร่งด่วนได้ แต่ควรมี System Priority ที่คำนวณจาก Impact × Urgency เพื่อลดปัญหาทุกงานถูก

เลือกเป็น ด่วน “ ”

| Priority | ความหมาย | ตัวอย่าง |
| --- | --- | --- |
| P1 Critical | กระทบการเรียนการสอนทั้งห้อง / บริการ | Interactive Board เปิดไม่ได้ก่อนเริ่ม |
|   | หลักหยุด | สอน |


| Priority | ความหมาย | ตัวอย่าง |
| --- | --- | --- |
| P2 High |   | อุปกรณ์หลักใช้ไม่ได้ แต่มีทางแก้ชั่วคราว เสียงหลักไม่ออกแต่มีอุปกรณ์สำรอง |
| P3 Medium | กระทบบางส่วน | Touch บางจุดไม่ตอบสนอง |
| P4 Low | ทั่วไป / ขอคำแนะนำ | อุปกรณ์เสริม หรือคำถามการตั้งค่า |

## 16. AI Troubleshooting Architecture

```
User Message
↓
Intent Classification
↓
Identify Asset / Device Type
↓
Identify Issue Category
↓
Retrieve Knowledge Base
↓
Guided Troubleshooting
↓
Ask Result
↓
Resolved / Escalate to Ticket
```

AI ไม่ควรตอบจากความรู้ทั่วไปแบบเปิดทั้งหมด แต่ควร Retrieval จาก Knowledge Base ที่องค์กรอนุมัติ และใช้โมเดล ภาษาเพื่อสรุป/ถามต่อ/จัดลำดับขั้นตอน

## 17. AI Safety Guardrail

| อนุญาต |   | ไม่ควรแนะนำผู้ใช้ทั่วไป |
| --- | --- | --- |
| Restart / ตรวจสาย / ตรวจ Network / ตรวจ Setting / วิธี | เปิดฝาหลังเครื่อง | / งานไฟฟ้าแรงสูง / ถอด Power Supply / |
| ใช้งาน Software | งานที่กระทบ Warranty |   |

เมื่อพบคำเตือนด้านความปลอดภัยหรือขั้นตอนที่เกินขอบเขตผู้ใช้ ระบบต้องหยุด Self-Service และ Escalate เป็น Ticket


## 18. AI Session Model

```
chatbot_sessions
- session_id
- user_id
- asset_id
- ticket_id
- started_at / ended_at
- resolved_by_self_service
chatbot_messages
- session_id
- role
- message
- intent
- knowledge_id
- created_at
```

ข้อมูลนี้ใช้วัด Self-Service Success Rate และตรวจสอบว่า Knowledge Article ใดช่วยแก้ปัญหาได้จริง

## 19. Knowledge Base Structure

```
KB-001
Device Type: Interactive Display
Issue: No Power
Symptoms: เปิดไม่ติด / ไม่มีไฟ / จอดำ
Possible Cause: Power
Troubleshooting:
1. ตรวจสายไฟ
2. ตรวจ Main Power
3. ตรวจ Power LED
4. กด Power
5. Restart
Escalation: ถ้ายังเปิดไม่ได้ → Create Ticket
Safety: ห้ามเปิดฝาหลังเครื่อง
```

| Field | รายละเอียด |
| --- | --- |
| code | รหัส KB |
| title | ชื่อบทความ |
| device_category_id | ประเภทอุปกรณ์ |
| issue_category_id | ประเภทปัญหา |
| symptoms | อาการ |
| cause | สาเหตุที่เป็นไปได้ |
| instructions | ขั้นตอนแก้เบื้องต้น |
| safety_warning | คำเตือน |
| escalation_rule | เงื่อนไขส่งต่อ |
| status/version | Draft / Published / Archived + version |

*หน้า 12 | โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะ*


| Field | รายละเอียด |
| --- | --- |
| created_by / updated_at | Audit |

## 20. Knowledge Learning Loop

```
Ticket Closed
↓
Cause + Solution ถูกบันทึก
↓
ระบบตรวจว่ามี KB ที่เกี่ยวข้องหรือไม่
↓
หากไ →ม่มี เสนอ Draft Knowledge Article
↓
Supervisor Review
↓
Published
```

## เป้าหมาย

ทำให้ประสบการณ์การซ่อมจริงกลับมาเพิ่มคุณภาพของ AI และคู่มือ Self-Service อย่างต่อเนื่อง

## 21. Repair Resolution

เมื่อ Technician กด Complete ระบบต้องบังคับข้อมูลอย่างน้อยดังนี้

- Root Cause

- Repair Action

- Resolution Note

- Parts Used (–I2!5)

- Before/After Photo 2!'2!@+!20*!

- %2#*-+%1
H-!

ห้ามเปลี่ยนเป็น COMPLETED ถ้าไม่มี Resolution ที่จำเป็น เพราะข้อมูลนี้เป็นแกนของ Repair History และ Analytics

## Validation Rule

## 22. Repair History

หน้า Asset ต้องสรุปประวัติการเสียและการซ่อมรายเครื่อง เพื่อใช้ตัดสินใจ PM / Warranty / Replacement

```
BOARD-001 | Interactive Display
Status: Active | Room: 401 | Warranty: Active
Tickets: 12 | Completed: 11 | Open: 1 | Repeat Failure: 3
10 Jun | HDMI ไม่มีภาพ | Cause: HDMI Cable | Solution: Replace Cable
25 Jun | Touch ไม่ทำงาน | Cause: Driver | Solution: Update Driver
03 Aug | เปิดไม่ติด | Cause: Power Supply | Solution: Replace Power Supply
```


## 23. LINE Official Account Architecture

LINE OA เป็นช่องทางบริการและแจ้งเตือนสำหรับผู้ใช้ ไม่ควรนำงาน Administration ทั้งหมดไปทำใน LINE

- AI1
+2

- @4+I2 Scan/QR Web View

- Chat 1 AI

- 9 Ticket -	1

- #1 Notification

- "7"1'H2C
I2DIA%I'

- @4 Web App

## 24. LINE Rich Menu

## 25. Notification Events

| Event | ผู้รับหลัก | ข้อความหลัก |
| --- | --- | --- |
| TICKET_CREATED | User + IT | รับเรื่องแล้ว + Ticket No. |
| TICKET_ASSIGNED | User + Technician | มอบหมายผู้รับผิดชอบแล้ว |
| TICKET_STARTED | User | เริ่มดำเนินการ |
| WAITING_FOR_PARTS | User + Supervisor | รออะไหล่ |
| WAITING_FOR_USER | User | ต้องการข้อมูล/การทดสอบจากผู้ใช้ |
| TICKET_COMPLETED | User | ดำเนินการเสร็จ รอยืนยัน |
| TICKET_CLOSED | User | ปิดงานแล้ว |
| TICKET_CANCELLED | User + Supervisor | ยกเลิกพร้อมเหตุผล |

## 26. n8n Workflow Specification

## 26.1. Workflow A - New Ticket

Ticket Created → Webhook → n8n → Lookup Ticket → LINE User → LINE IT → Log Notification

## 26.2. Workflow B - Status Change

Status Updated → Webhook → Determine Message Template → LINE/Other Channel → Log


## 26.3. Workflow C - Completed Confirmation

COMPLETED → LINE User → [ใช้งานได้แล้ว] / [ยังมีปัญหา]

ใช้งานได้แล้ว → CLOSED

ยังมีปัญหา → Reopen / IN_PROGRESS

## 27. Web Application Sitemap

├── Login ├── QR Landing └── Ticket Tracking

## PUBLIC

## USER

├── Dashboard

├── Report Problem

├── My Tickets

├── Ticket Detail

├── AI Support

- └── Profile

## TECHNICIAN

├── Dashboard

├── New Queue

├── My Jobs

├── Ticket Detail

├── Asset Detail

└── Knowledge Base

## SUPERVISOR

├── Dashboard

├── All Tickets

├── Assignment

- ├── Technicians

├── Reports

└── Knowledge Base

## ADMIN

- ├── Users

- ├── Assets / QR Codes

- ├── Categories

- └── Settings

├── Dashboard

├── Schools / Buildings / Rooms

├── Knowledge Base


## 28. User Dashboard Specification

```
สวัสดี คุณสมชาย
[ แจ้งปัญหาใหม่ ] [ Scan QR ] [ ขอคำแนะนำ AI ]
Ticket ของฉัน
Open 2 | In Progress 1 | Completed 7
รายการล่าสุด
SC-2026-000102 | Interactive Display | กำลังดำเนินการ
SC-2026-000097 | Wi-Fi | เสร็จแล้ว
```

- @I8H! action 5HC
I2H-"

- A*@
20 Ticket 5H
9IC
I!5*44L

- #-#1 Mobile First @
#20 QR/LINE !1@42B#(1
L

## 29. Technician Dashboard Specification

งานใหม่ 7 | งานของฉัน 4 | กำลังดำเนินการ 2 | รออะไหล่ 1 | เกินกำหนด 0

| Ticket | Device | Problem | Priority | Age |
| --- | --- | --- | --- | --- |
| SC-001 | Board | เปิดไม่ติด | P1 | 5m |
| SC-002 | AP | Internet | P2 | 20m |

- Filter —2! Priority / School / Device / Status

- Quick Accept Job

- A*@'%2-2"8 Ticket

- Highlight 2 P1/P2 A%02C%I@4 SLA (Phase 2)

## 30. Ticket Detail Screen Specification

หน้าจอ Ticket Detail เป็นหน้าปฏิบัติงานหลัก ต้องรวมข้อมูล Asset, Problem, AI History, Timeline, Assignment

และ Repair Resolution ไว้ในหน้าเดียว

| Section | ข้อมูล |
| --- | --- |
| Header | Ticket No., Priority, Status |
| Asset | Device, Asset Code, School, Room |
| Issue | Title, Description, Attachments |
| AI History | ขั้นตอน Self-Service ที่ทำไปแล้ว |
| Timeline | Created / Assigned / Started / Waiting / Completed / |
|   | Closed |
| Actions | Assign, Accept, Change State, Add Note, Upload, |
|   | Complete |


## 31. Admin Asset Screen

- Search Asset

- Filter: School / Room / Type / Status / Warranty

- Add/Edit Asset

- Generate/Reprint QR

- 9 Repair History

- Export #2"—2# Asset (Phase 2)

## 32. Database Blueprint

| กลุ่ม | Tables |
| --- | --- |
| Identity | users, roles, user_roles |
| Organization | organizations, schools, buildings, rooms |
| Asset | asset_categories, asset_models, assets, |
|   | asset_qr_codes |
| Issue | issue_categories |
| Ticket | tickets, ticket_status_history, ticket_assignments, |
|   | ticket_comments, ticket_attachments |
| Repair | repair_records, repair_parts |
| Knowledge | knowledge_articles |
| AI | chatbot_sessions, chatbot_messages, |
|   | self_service_cases |
| Notification | notifications |
| Maintenance | maintenance_plans, maintenance_records |
| Audit | audit_logs |

## Data Integrity

ควรใช้ Foreign Key, Unique Constraint, Enum/Lookup และ Transaction กับเหตุการณ์สำคัญ เช่น Ticket Creation + Status History + Notification Event เพื่อป้องกันข้อมูลครึ่งทาง


## 33. ER Relationship แบบย่อ

## 34. API Blueprint

| Domain | Endpoints ตัวอย่าง |
| --- | --- |
| Auth | POST /api/auth/login; POST /api/auth/logout; GET |
|   | /api/auth/me |
| Assets | GET/POST /api/assets; GET/PATCH /api/assets/:id; GET |
|   | /api/assets/:id/history |
| QR | GET /api/q/:token |
| Tickets | GET/POST /api/tickets; GET/PATCH /api/tickets/:id |
| State | POST /api/tickets/:id/status |
| Assignment | POST /api/tickets/:id/assign; POST /api/tickets/:id/accept |
| Repair | POST /api/tickets/:id/repair; /complete; /close |
| AI | POST /api/support/session; /message; /escalate |
| Knowledge | GET/POST /api/knowledge; GET /api/knowledge/:id |
| Dashboard | GET /api/dashboard/summary; /issues; /assets; /schools |


## 35. API Response Standard

```
Success
{
"success": true,
"data": {},
"error": null
}
Error
{
"success": false,
"data": null,
"error": {
"code": "TICKET_NOT_FOUND",
"message": "ไม่พบรายการแจ้งซ่อม"
}
}
```

Production ควรเพิ่ม request_id / trace_id สำหรับ Debug และ Monitoring

## 36. Dashboard Blueprint

Dashboard ต้องดึงจากข้อมูล Ticket/Asset/Repair จริง และรองรับ Filter ตามช่วงเวลา โรงเรียน ประเภทอุปกรณ์ ประเภทปัญหา และ Status

| KPI / Chart | จุดประสงค์ |
| --- | --- |
| Total Tickets | ปริมาณงานทั้งหมด |
| Open / In Progress / Closed | ภาระงานตามสถานะ |
| Ticket Trend | แนวโน้มรายวัน/เดือน |
| Ticket by Issue | ปัญหาที่พบบ่อย |
| Ticket by Device | อุปกรณ์ที่มีปัญหามาก |
| Ticket by School | โรงเรียนที่มีการแจ้งมาก |
| Average Repair Time | ระยะเวลาซ่อมเฉลี่ย |
| Self-Service Rate | อัตราที่ AI/Chatbot แก้ได้ |
| Escalation Rate | อัตราที่ต้องส่งต่อ IT |

## 37. KPI เพิ่มเติมสำหรับระบบจริง

| KPI | คำอธิบาย |
| --- | --- |
| MTTR | Mean Time To Repair |
| MTTA | Mean Time To Assign |
| First Response Time | เวลาจากแจ้งจนเริ่มตอบสนอง |


| KPI | คำอธิบาย |
| --- | --- |
| Repeat Failure Rate | สัดส่วนอุปกรณ์ที่เสียซ้ำ |
| Self-Service Success Rate | สัดส่วนเคสที่ผู้ใช้แก้ได้เอง |
| Technician Workload | ภาระงานต่อเจ้าหน้าที่ |
| Asset Failure Rate | อัตราการเสียรายประเภท/รุ่น |

## 38. Preventive Maintenance Engine

MVP ควรเริ่มจาก Rule Engine ก่อน Predictive AI เพื่อให้ตรวจสอบเหตุผลได้และพัฒนาได้ทันเวลา

```
Rule 1
IF Asset มี Ticket >= 3 ครั้งใน 90 วัน
THEN Flag = REPEATED_FAILURE
Rule 2
IF Warranty จะหมดใน 30 วัน
THEN Notify Admin
Rule 3
IF อายุอุปกรณ์ > 4 ปี AND Repair Frequency สูง
THEN Recommend Replacement Review
```

## 39. Security Blueprint

- Authentication A%0 Role-Based Access Control (RBAC)

- HTTPS 8 Environment 5H!5I-!9%#4

- Password Hashing I'" algorithm !2#2

- Input Validation 1I Frontend A%0 Backend

- Rate Limiting *3+#11 Login, QR, Chatbot A%0 Public API

- Secure File Upload + 31 MIME/2

- Environment Secrets *3+#11 API Key/DB Password/LINE Secret

- Database Backup A%0 Restore Test

- Audit Log *3+#1 Action *31

- Least Privilege *3+#19 DB user A%0 Service Account

## ห้าม

ห้าม commit API Key, Database Password, LINE Channel Secret หรือ Gemini Key ลง Git Repository


## 40. Audit Log

```
audit_logs
- user_id
- action
- entity_type
- entity_id
- old_value
- new_value
- ip_address
- created_at
```

Action ที่ควร Audit ได้แก่ Login ที่สำคัญ, เปลี่ยนสิทธิ์, สร้าง/ แก้ Asset, Assign งาน, เปลี่ยน Status,

Complete/Close, แก้ Knowledge Base และ System Settings

## 41. File Attachment Security

| ข้อกำหนด |   | แนวทาง |
| --- | --- | --- |
| ชนิดไฟล์ | JPG / PNG / PDF ใน MVP |   |
| ขนาด | เ ≤ช่น | 10 MB ต่อไฟล์ ( ปรับตาม Server) |
| Validation | ตรวจ MIME + Extension + Content Signature ตามความ |   |
|   | เหมาะสม |   |
| Storage Name | เปลี่ยนชื่อเป็น UUID / generated key |   |
| Access | ตรวจสิทธิ์ก่อนดาวน์โหลด |   |
| Malware | สแกนเมื่อมีเครื่องมือรองรับ โดยเฉพาะ Phase Production |   |

## 42. Deployment Architecture

## 42.1. Docker Services

```
frontend
backend
postgres
n8n
reverse-proxy
```

*หน้า 21 | โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะ*


## 43. Environment Strategy

Development → Staging → UAT → Production

| Environment | วัตถุประสงค์ |
| --- | --- |
| Development | พัฒนา/ ทดสอบราย Feature |
| Staging | ทดสอบระบบรวมและ Integration ใกล้เคียง Production |
| UAT | ผู้ใช้งาน/ผู้ควบคุมโครงการตรวจรับ |
| Production | ใช้งานจริง |

## 44. Git / Repository Structure

smart-classroom-support/

├── frontend/

├── backend/

├── database/

├── automation/

│ └── n8n/

├── docs/

├── deployment/

├── tests/

└── README.md

- C
I Branch/PR 2!'2!@+!20*!

- 8 Feature I-!5 Issue/Task -I2-4

- Tag Release @
H v0.1.0,

- +I2!@G Secrets C Repo

## 45. Testing Blueprint

| Test Type | สิ่งที่ตรวจ |
| --- | --- |
| Unit Testing | Business logic / validation / utility |
| API Testing | Auth, permission, validation, error contract |
| Functional Testing | User flows ราย Feature |
| Integration Testing | LINE, n8n, Gemini, Database |
| Security Testing | Auth/RBAC, input, upload, rate limit |
| Responsive Testing | Mobile / Tablet / Desktop |
| UAT | สถานการณ์จริงกับผู้ใช้งาน |

## 45.1. Core Test Scenarios

- Interactive Display @4D!HDI / Touch D!H32 / HDMI D!H!5 2 /

- Network: Wi-Fi D!HDI / Internet D!H32 / Access Point Offline


- Software: Login D!HDI / B#A#!@4D!HDI / LMS Error

- Ticket: Create / Assign / Accept / State / Complete / Close

- Notification: New Ticket / Status / Completed / Closed

## 46. UAT Scenario ตัวอย่าง

- UAT-001: Interactive Display เปิดไม่ติด

- 1. Scan QR

- 2. ระบบพบ BOARD-001

- 3. เลือก “เปิดไม่ติด”

- 4. AI แนะนำตรวจ Power

- 5. ผู้ใช้ทำตาม

- 6. ยังไม่สำเร็จ

- 7. Create Ticket

- 8. Ticket Number ถูกสร้าง

- 9. Technician ได้ Notification

- 10. Technician รับงาน

- 11. Repair + Resolution

- 12. Complete

- 13. User ได้ Notification

- 14. User Confirm

- 15. Ticket Closed

- 16. Repair History Updated

ทุก Step สำเร็จ, ข้อมูลไม่สูญหาย, Permission ถูกต้อง, Notification ถูกต้อง, Timeline/History ถูกบันทึก และ Dashboard สะท้อนข้อมูลที่เกิดขึ้น

## Pass Criteria

## 47. MVP Acceptance Criteria

- 1. สร้าง Ticket ได้สำเร็จ

- 2. Ticket มีหมายเลขอ้างอิงไม่ซ้ำ

- 3. บันทึกข้อมูลผู้แจ้ง/อุปกรณ์/ปัญหาได้

- 4. QR ระบุอุปกรณ์ได้

- 5. Ticket State ทำงานตาม Transition

- 6. ผู้ใช้ติดตามสถานะได้

- 7. เจ้าหน้าที่รับ/Assign งานได้

- 8. Notification ทำงานตาม Event หลัก

- 9. Repair Resolution และ History ถูกบันทึก

- 10. Chatbot/AI ให้คำแนะนำปัญหาพื้นฐานและ Escalate ได้

- 11. Dashboard แสดงข้อมูลจากระบบจริงได้

- 12. Workflow หลักผ่าน UAT


## 48. Scope: MVP vs Phase 2

| MVP - ต้องเสร็จในโครงการ | Phase 2 - ต่อขยาย |
| --- | --- |
| User / Role | Spare Parts Inventory |
| School / Room / Asset | Warranty Management ขั้นสูง |
| QR | SLA Engine ขั้นสูง |
| Ticket / Status / Assignment | Mobile Application Native |
| Repair Record / History | Remote Support |
| LINE Notification / n8n | AI Agent |
| Knowledge Base / Basic Chatbot | Predictive Maintenance |
| Dashboard | AI Failure Prediction / Auto Assignment ขั้นสูง |


## 49. Revised 8-Week Development Plan

| Week | งานหลัก | Deliverable / Milestone |
| --- | --- | --- |
|   | ศึกษา Smart Classroom, | Requirement, Inventory, Issue |
| 1 | Hardware/Software, Pain Point, IT | Classification, Current Workflow |
|   | Support Flow |   |
| 2 | Architecture, Database, Role, | SRS, ERD, Flowchart, UI Wireframe, API |
|   | Wireframe, Ticket/QR/AI Flow | Draft |
| 3 | Authentication, User, School, Building, | Scan QR แล้วระบุ Asset ถูกต้อง |
|   | Room, Asset, QR |   |
| 4 | Create Ticket, Number, List, Status, | Ticket Core Open → Closed ใช้งานได้ |
|   | Assignment, Attachment, Timeline |   |
| 5 | LINE OA, Messaging API, n8n, | Ticket Event แจ้ง LINE ได้ |
|   | Webhook, Notification |   |
| 6 | Knowledge Base, Issue Classification, | AI Guide + Escalate เป็น Ticket ได้ |
|   | Chatbot, Gemini, Self-Service |   |
| 7 | Dashboard, Repair History, Analytics, | Dashboard ใช้ข้อมูลจริง |
|   | Integration Test |   |
| 8 | UAT, Bug Fix, Security Review, Docs, | Release Candidate + เอกสารส่งมอบ |
|   | Deployment, Presentation |   |

## 50. Definition of Done

Requirement ✓

Development ✓

Validation ✓

Permission ✓

Error Handling ✓

Responsive ✓

Testing ✓

Documentation ✓

“ หน้าเปิดได้ หรือ กดแล้วมีผล ยังไม่ถือว่า ” “ ” Feature เสร็จ หากยังไม่มี Validation, Permission, Error Handling,

Test และ Documentation ตามระดับที่กำหนด

## DoD Rule


## 51. Master Blueprint - End-to-End

## 52. System Design Rules ที่ควรล็อก

- 1. Asset First - ทุก Ticket ที่เป็นไปได้ต้องผูกกับ Asset

- 2. QR identifies Asset - QR ไม่ใช่เพียงลิงก์เปิด Form

- 3. AI Before Ticket - ปัญหาพื้นฐานเข้าสู่ Self-Service ก่อนเมื่อเหมาะสม

- 4. AI ต้องอิง Knowledge Base และ Safety Guardrail

- 5. Ticket Status ต้องเป็น State Machine

- 6. ทุก Status Change ต้องมี History


- 7. ทุก Completed Ticket ต้องมี Resolution

- 8. Repair History ต้องผูกกับ Asset

- 9. n8n ใช้ Automation ไม่ใช่ Core Database/Logic

- 10. Ticket ทุกใบต้องสามารถนำข้อมูลกลับมาใช้สร้าง Knowledge และ Analytics

## 53. Development Document Package

| ลำดับ | เอกสาร | วัตถุประสงค์ |
| --- | --- | --- |
| 01 | SRS | Requirement ทั้งระบบ |
| 02 | System Architecture | สถาปัตยกรรมและ Component |
| 03 | User Role Matrix | สิทธิ์ผู้ใช้ |
| 04 | UI/UX Specification | หน้าจอ / State / Validation |
| 05 | Database ERD + Data Dictionary | ตาราง ความสัมพันธ์ ชนิดข้อมูล |
| 06 | API Specification | Endpoint / Request / Response / Error |
| 07 | Ticket State Machine | State + Transition + Guard |
| 08 | AI Troubleshooting Specification | Intent / Retrieval / Guardrail / |
|   |   | Escalation |
| 09 | Knowledge Base Schema | โครงสร้างบทความและ Versioning |
| 10 | n8n Workflow Specification | Trigger / Flow / Retry / Notification |
| 11 | Test Plan | Functional / Integration / Security / |
|   |   | Responsive |
| 12 | UAT | สถานการณ์ตรวจรับ |
| 13 | Deployment Guide | ติดตั้ง Environment / Docker / Backup |
| 14 | User Manual | คู่มือผู้ใช้ |
| 15 | Admin Manual | คู่มือผู้ดูแลระบบ |

## 54. สรุปและลำดับการดำเนินงานต่อ

Blueprint นี้เปลี่ยนแนวคิดโครงการให้เป็นโครงสร้างระบบที่พร้อมแตกงานพัฒนา โดยยังคงเป้าหมายเดิมของโครงการ Smart Classroom IT Support และเพิ่มรายละเอียดที่จำเป็นต่อการสร้างระบบจริง

ลำดับงานที่แนะนำก่อนเริ่ม Coding คือ 1) Database ER Diagram + Data Dictionary 2) Ticket State Machine 3) Role/Permission 4) UI Wireframe 5) API Contract 6) AI/Knowledge Flow 7) n8n/Notification Flow 8) Test & UAT

## จุดเริ่มต้นที่สำคัญที่สุด

ล็อก Database ERD + Ticket State Machine ก่อนพัฒนา UI/AI เพื่อให้ Frontend, Backend, LINE, n8n และ

Dashboard ใช้ข้อมูลและกติกาชุดเดียวกัน


## ภาคผนวก A. รายการ Master Data ที่ควรเตรียม

| Master Data | ตัวอย่าง |
| --- | --- |
| Asset Category | Interactive Display, Computer, Router, Access Point, |
|   | Speaker, Camera |
| Issue Category | Power, Display, Touch, Audio, Network, Login, LMS, |
|   | Software |
| Ticket Status | Open, Assigned, In Progress, Waiting for Parts, |
|   | Waiting for User, Completed, Closed, Cancelled |
| Priority | P1, P2, P3, P4 |
| Source | QR, Web, LINE |
| Asset Status | Active, Maintenance, Inactive, Retired |
| KB Status | Draft, Published, Archived |

## ภาคผนวก B. แหล่งอ้างอิงขอบเขตโครงการ

เอกสารต้นทาง: “ โครงการพัฒนาระบบแจ้งซ่อมออนไลน์และระบบสนับสนุนงาน IT อัจฉริยะสำหรับห้องเรียน Smart

Classroom (Online Repair Request and Intelligent IT Support System for Smart Classroom)” จำนวน 15 หน้า ซึ่งกำหนดวัตถุประสงค์ ขอบเขต Ticket/QR/Chatbot/Notification/Repair History/Dashboard

เทคโนโลยี แผนงาน 8 สัปดาห์ ตัวชี้วัด การทดสอบ และแนวทางต่อยอดในอนาคต

ส่วนที่เป็น Role Matrix, State Transition Rules, Database Detail, API Contract, Security, Audit, Environment Strategy, Priority Engine และ Development DoD เป็นรายละเอียดเชิงออกแบบที่เพิ่มขึ้นใน

Blueprint เพื่อให้พร้อมสำหรับการพัฒนาและตรวจรับระบบ
