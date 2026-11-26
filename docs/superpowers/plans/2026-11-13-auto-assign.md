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
- Accept timeout: `DISPATCH_OFFER_MINUTES`, default **5** (owner first chose 30; changed when the owner asked for Grab-style "pop up and tap to accept" - set 30 in Render env to restore). Sweep every 30 seconds. Only tickets with `auto_assigned = true` are passed on; an admin's manual assignment is never moved.
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

---

## As built (2026-11-13)

- Owner refined the request mid-build: "simple, always ready to send, like Grab - the job pops up for whoever has the fewest jobs or is free, they tap accept". Built exactly that: pop-up with countdown + Accept/Skip, LINE push, team page.
- **Reachable only:** a technician is offered work only when on duty AND (LINE linked OR the staff web app polled in the last 10 minutes). Without this, every dormant/demo it_support account would sit in front of the real technician for 5 minutes each.
- Offers go to the school's own technician first only by the ranking rule (fewest open, fewest done today, free longest, lowest id) - no special preference.
- After everyone eligible has been offered a ticket once, it returns to `new` and appears under "ยังไม่มีคนรับ" on the team page; no more pushes.
- LINE push link is `/?job=<ticket>` (staff app). `/?ticket=` stays the public tracking page.
- Row locks use `populate_existing` so accept/assign/skip re-read the row after locking.
- Customer side (same branch): track by ticket number or device code, "my repair requests" list with live status, step times, technician name after accept, auto refresh every minute.
- Tests: backend 184 passed / 15 skipped; vitest 27 passed.

### Deploy notes
- `init_db()` adds the new columns on the next deploy (users: on_duty, line_push_id, line_link_code, line_link_code_expires_at, last_seen_at; repair_tickets: assigned_user_id, assigned_at, auto_assigned, offer_tried). No manual migration.
- The sweeper starts with the app and immediately offers every `new` ticket from the last 3 days to reachable technicians. On a fresh deploy nobody is reachable yet, so nothing moves until technicians open the app or link LINE.
- Env: `AUTO_ASSIGN_ENABLED` (default 1), `DISPATCH_OFFER_MINUTES` (default 5), `STAFF_APP_URL` (default https://iwasmart-service.vercel.app), `DISPATCH_SWEEP_DISABLED=1` to stop the background sweep.
- Linking LINE needs the OA webhook to reach the backend (`wf_line_forward.json` -> `/api/line/webhook`, or `/api/line/bot`). If the LINE console points at `wf_allinone.json`, which replies by itself, "ผูก 123456" never reaches the backend.
- Render free tier sleeps: the sweep only runs while awake (`wf_keepalive.json` pings `/health`).
