# Auto-assign + private LINE alerts + "My work" Implementation Plan

> **For agentic workers:** executed natively in the owner session. Steps use checkbox syntax.

**Goal:** New tickets go to the least-busy on-duty technician automatically, that person gets a private LINE message, admins see and steer the team's workload, and staff find their own tickets in one tab.

**Architecture:** A new `backend/app/auto_assign.py` owns the picking rule, the assignment write and the stale-assignment sweep. Assignment runs on its own single-worker pool after the ticket is committed, so two tickets created at once never both read the same "least busy" snapshot and the report request never waits. Staff link LINE by sending a one-time 6-digit code to the existing OA; the webhook stores their real LINE userId. Frontend: a "My work" tab plus holder badges on the Tickets page, a duty/LINE card for staff, a Team workload page for admins.

**Tech Stack:** FastAPI, SQLAlchemy 2, Postgres; React 18 + TS; Vitest; pytest.

**Spec:** owner decisions 2026-11-13 (chat): link by code sent to OA; rule = fewest open jobs; staff must accept, 30 min without accept = pass to next person; keep status tabs, add "My work", show holder on each ticket.

## Global Constraints

- Eligible staff: `role == "it_support"`, `is_active`, `on_duty`, and (`organization_id is None` or equal to the ticket's organization).
- Open statuses (count as load): `assigned, in_progress, pending, waiting_parts, waiting_user`.
- Pick order: fewest open tickets, then fewest tickets resolved today (Asia/Bangkok day), then oldest `last assigned_at` (free longest; never-assigned first), then lowest user id.
- Accept timeout: 30 minutes (`AUTO_ASSIGN_ACCEPT_MINUTES`, default 30). Sweep every 5 minutes. Only tickets with `auto_assigned = true` are passed on; an admin's manual assignment is never moved.
- Kill switch: env `AUTO_ASSIGN_ENABLED` (default `1`).
- Link code: 6 digits, valid 15 minutes, single use. LINE message `ผูก 123456` or `link 123456`.
- Notifications never fail or slow the request (same rule as `_notify_n8n`).
- Schema changes are applied by `init_db()` with `ADD COLUMN IF NOT EXISTS`, so Neon needs no manual step.

## Review Focus

1. No eligible staff (all off duty / none in that school) - ticket stays `new`, sweep retries; no crash, no LINE spam.
2. Two tickets created at the same instant - must go to two different people when two are free (serialized pool).
3. Staff without linked LINE - assignment still happens; admin board shows "LINE not linked".
4. A different technician accepts someone else's assigned ticket - acceptor becomes the holder; sweep must not move it afterwards.
5. Wrong / expired / reused link code in LINE - polite reply, nothing linked, chatbot not triggered.

---

### Task 1: Schema + picking rule
Files: `backend/app/models.py` (User: `line_push_id`, `on_duty`, `line_link_code`, `line_link_code_expires_at`; RepairTicket: `assigned_user_id` FK users.id SET NULL, `assigned_at`, `auto_assigned`), `backend/app/auto_assign.py`, `backend/tests/test_auto_assign.py`.
Produces: `pick_staff(db, org_id, exclude_ids=()) -> Optional[User]`, `assign_ticket(db, ticket, staff, *, auto, actor_name, actor_role) -> None`, `auto_assign_ticket_id(ticket_pk) -> Optional[int]`, `sweep_stale_assignments(now=None) -> int`, `enqueue_auto_assign(ticket_pk)`, `flush_assignments()`.
Tests: least-open wins; done-today breaks tie; off-duty / other-school / inactive excluded; none eligible returns None; two simultaneous enqueues go to two people; sweep passes a 31-min-old auto assignment to another person and leaves a manual one alone.

### Task 2: Wire into ticket creation, accept, manual assign
Files: `backend/app/main.py` (4 creation paths incl. `chatbot_core._create_ticket_from_fields`), accept sets holder to acceptor, `/assign` accepts `assignee_user_id` and pushes LINE, list/counts gain `mine=1`, ticket JSON gains `assigned_user_id`, sweep thread on startup.
Tests: public report ends `assigned` to the free person; accept by other tech moves holder; `mine=1` filter + count.

### Task 3: LINE link + duty + workload API
Endpoints: `POST /api/me/line-link-code`, `DELETE /api/me/line-link`, `PATCH /api/me/duty`, `GET /api/staff/workload` (admin roles, scoped), `PATCH /api/staff/{id}/duty` (admin). Webhook intercepts `ผูก/link NNNNNN` before the chatbot.
Tests: code links once, expired/reused rejected; workload numbers; school admin sees only own school.

### Task 4: Frontend
"งานของฉัน" tab (first tab for it_support), holder badge on card and row ("ยังไม่มีคนรับ" when empty), `MyDutyCard` (on-duty switch + LINE link code) on Tickets page for staff, `TeamWorkloadPage` (menu "ทีมช่าง") for admins with duty toggles and open/today counts.
Tests: vitest for tab params; browser check of the whole flow.
