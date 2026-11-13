# Tickets: Fast and Usable — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Tickets page loads 20 rows at a time from the server, works on a phone, and lets staff move a ticket through its workflow from the detail sheet.

**Architecture:** `GET /api/tickets` gains search, multi-status filtering and an `X-Total-Count` header; a new `GET /api/tickets/counts` feeds status tabs. The Tickets page moves out of `App.tsx` into `frontend/src/components/tickets/` and fetches its own page of data instead of filtering an in-memory array. Pure logic (query building, paging maths, allowed actions) lives in plain `.ts` files with unit tests.

**Tech Stack:** FastAPI + SQLAlchemy 2 + PostgreSQL 16; React 18 + TypeScript + Vite 5; pytest 8.3.4; Vitest 2 (new dev dependency).

**Spec:** `docs/superpowers/specs/2026-11-13-ux-speed-revamp-design.md`

## Global Constraints

- Work on branch `feat/tickets-fast-usable` created from `main`. Never push, never deploy; production (Render, Neon, Vercel, Railway) is out of bounds.
- API changes are additive: the response body of `GET /api/tickets` stays `list[TicketOut]`; existing query parameters keep their meaning.
- No table or column changes. Indexes only, created with `IF NOT EXISTS`.
- No new runtime dependency in the frontend. One new dev dependency: `vitest@^2`.
- Page size is 20. Search input debounce is 300 ms.
- UI copy is Thai. New CSS goes in `frontend/src/styles/tickets.css` using existing tokens (`--color-*`, `--status-*`, `--radius-*`, `--spacing-*`); no hex colours, no inline `style={{}}` in new components.
- Every interactive element is reachable by keyboard and has an accessible name; touch targets are at least 44 px high at widths ≤ 640 px.
- Commit after each task; end commit messages with `Co-Authored-By: Claude Fable 5.2 <noreply@anthropic.com>`.

**Commands used throughout** (run from the repo root in Git Bash, stack up via `docker compose up -d postgres redis backend frontend`):

```bash
# backend tests (image has no pytest; throwaway container, source mounted)
MSYS_NO_PATHCONV=1 docker run --rm --network smart-classroom-support_default \
  -e DATABASE_URL=postgresql+psycopg2://postgres:postgres@postgres:5432/smart_classroom \
  -e JWT_SECRET=test -v "$(pwd -W)/backend:/src" -w /src smart-classroom-support-backend \
  sh -c "pip install -q pytest==8.3.4 && python -m pytest -q -p no:cacheprovider <ARGS>"

# pick up backend code changes in the running app
docker compose up -d --build backend

# frontend
docker exec smart_classroom_frontend npx vitest run
docker exec smart_classroom_frontend npx tsc --noEmit
```

Backend tests follow the convention in `backend/tests/test_recovery.py`: create uniquely tagged rows with `SessionLocal`, authenticate with `create_token(user)`, clean up in `finally`.

## Review Focus

1. **Search text containing `%`, `_` or `\`** — must match literally, not as wildcards. Test in Task 1.
2. **A school-scoped user asking for another school's tickets or counts** — must get only their own school; `X-Total-Count` and `/counts` must not leak other schools' totals. Tests in Tasks 1 and 2.
3. **The current page no longer exists** (a filter change or a status change empties page 3) — the page must fall back to the last page that has rows, never show an empty table with a non-zero total. Test in Task 4.
4. **Slow responses arriving out of order** while the user types or switches tabs — only the latest request may update the list. Covered by a request-generation guard specified in Task 5; verified manually in Task 8.
5. **An action the server refuses** (ticket already accepted by someone else → 409) — the sheet shows the server's message inline and reloads the ticket; no `alert()`. Test of the pure rules in Task 7; behaviour verified in Task 8.

---

### Task 1: Search, multi-status filter and total count on `GET /api/tickets`

**Files:**
- Modify: `backend/app/main.py` — `list_tickets` (starts at the `@app.get("/api/tickets", ...)` decorator, ~line 3509) and the `CORSMiddleware` block (~line 1354)
- Test: `backend/tests/test_ticket_list_paging.py` (create)

**Interfaces:**
- Produces: `GET /api/tickets?q=<text>&status=<a,b,c>&...&limit=&offset=` → body unchanged (`list[TicketOut]`), response header `X-Total-Count: <int>` = rows matching the filters before `limit/offset`.
- Produces: `_ticket_filter_conditions(db, user, *, q, status, priority, device_id, device_type, device_category, organization_id) -> list | None` in `main.py` — the SQLAlchemy conditions for the joined `RepairTicket`/`Device`/`Organization` query, or `None` when the result is known to be empty (unknown category, empty role scope). Task 2 reuses it.

- [ ] **Step 1: Write the failing tests**

Fixtures go in `backend/tests/conftest.py` (Tasks 2 and 3 reuse them): `client` (a `TestClient(app)`), `tag` (unique per test), `admin_headers` (a `super_admin`), `school_admin_headers` (an `admin_school` in a second organization), `ticket_ids`. Data: one device per organization; in the first organization tickets titled `"จอดับ 100%_x {tag}"` (status `new`), `"จอดับ 100AAx {tag}"` (status `pending`), `"ลำโพงไม่ดัง {tag}"` (status `waiting_parts`); one ticket `"เปิดไม่ติด {tag}"` in the second organization. Every test filters on `tag` so existing rows do not interfere; the fixture deletes its rows on teardown.

```python
def test_total_count_header_ignores_limit(client, admin_headers, tag):
    r = client.get(f"/api/tickets?q={tag}&limit=1", headers=admin_headers)
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.headers["X-Total-Count"] == "4"

def test_search_matches_title_and_ticket_id(client, admin_headers, tag, ticket_ids):
    by_title = client.get("/api/tickets", params={"q": f"ลำโพงไม่ดัง {tag}"}, headers=admin_headers).json()
    assert [t["status"] for t in by_title] == ["waiting_parts"]
    # ticket numbers are matched case-insensitively
    by_id = client.get("/api/tickets", params={"q": ticket_ids[0].lower()}, headers=admin_headers).json()
    assert [t["ticket_id"] for t in by_id] == [ticket_ids[0]]

def test_search_treats_wildcards_literally(client, admin_headers, tag):
    titles = [t["title"] for t in client.get("/api/tickets", params={"q": "100%_x"}, headers=admin_headers).json()]
    assert any("100%_x" in t for t in titles)
    assert not any("100AAx" in t for t in titles)

def test_status_accepts_comma_separated_list(client, admin_headers, tag):
    r = client.get("/api/tickets", params={"q": tag, "status": "pending,waiting_parts"}, headers=admin_headers)
    assert sorted(t["status"] for t in r.json()) == ["pending", "waiting_parts"]
    assert r.headers["X-Total-Count"] == "2"

def test_school_scoped_user_sees_only_own_school(client, school_admin_headers, tag):
    r = client.get("/api/tickets", params={"q": tag}, headers=school_admin_headers)
    assert r.headers["X-Total-Count"] == "1"
    assert len(r.json()) == 1

def test_total_count_header_is_exposed_to_browsers(client, admin_headers):
    r = client.get("/api/tickets?limit=1", headers={**admin_headers, "Origin": "http://localhost:5173"})
    assert "x-total-count" in r.headers["access-control-expose-headers"].lower()
```

- [ ] **Step 2: Run to verify they fail**

Run the backend test command with `<ARGS>` = `tests/test_ticket_list_paging.py`.
Expected: failures on `KeyError: 'x-total-count'` and on the comma-separated status test.

- [ ] **Step 3: Implement**

- Extract the existing filter/visibility logic of `list_tickets` into `_ticket_filter_conditions(...)` (signature above), unchanged in behaviour.
- `status`: split on `,`, strip, drop empties; one value → `==`, several → `.in_()`.
- `q: Optional[str] = Query(None, max_length=100)`: strip; when non-empty, escape `\`, `%`, `_` with a backslash and apply `ILIKE '%…%' ESCAPE '\'` across `RepairTicket.ticket_id`, `title`, `description`, `reporter_name`, `device_id`, `Organization.name`, `Organization.short_name`, `Organization.code`, OR-ed.
- Add `response: Response` to `list_tickets`; set `X-Total-Count` from a `select(func.count())` over the same joins and conditions; on the early-return-empty paths set it to `"0"`.
- Add `expose_headers=["X-Total-Count"]` to `CORSMiddleware`.

- [ ] **Step 4: Run to verify they pass**

Same command. Expected: 6 passed. Then run the whole suite (`<ARGS>` empty): expected 146 passed, 17 skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_ticket_list_paging.py
git commit -m "feat(api): ticket search, multi-status filter and X-Total-Count"
```

---

### Task 2: `GET /api/tickets/counts`

**Files:**
- Modify: `backend/app/main.py` — add the route **above** `@app.get("/api/tickets/{ticket_id}", ...)` (~line 3608), otherwise `counts` is captured as a ticket id
- Test: `backend/tests/test_ticket_list_paging.py`

**Interfaces:**
- Consumes: `_ticket_filter_conditions` from Task 1 (called with `status=None`).
- Produces: `GET /api/tickets/counts?q=&priority=&device_id=&device_type=&device_category=&organization_id=` → `{"total": int, "by_status": {"new": int, ...}}`; `by_status` contains only statuses that have rows. Requires login (`get_current_user`).

- [ ] **Step 1: Write the failing tests**

```python
def test_counts_groups_by_status_for_the_same_filters(client, admin_headers, tag):
    body = client.get("/api/tickets/counts", params={"q": tag}, headers=admin_headers).json()
    assert body["total"] == 4
    assert body["by_status"]["pending"] == 1 and body["by_status"]["waiting_parts"] == 1
    assert sum(body["by_status"].values()) == body["total"]

def test_counts_respects_school_scope(client, school_admin_headers, tag):
    assert client.get("/api/tickets/counts", params={"q": tag}, headers=school_admin_headers).json()["total"] == 1

def test_counts_requires_login(client):
    assert client.get("/api/tickets/counts").status_code == 401

def test_counts_route_is_not_swallowed_by_ticket_id_route(client, admin_headers):
    assert "by_status" in client.get("/api/tickets/counts", headers=admin_headers).json()
```

- [ ] **Step 2: Run to verify they fail** — expected: 404 "Ticket not found" for the authenticated calls.

- [ ] **Step 3: Implement `ticket_counts(...)`** — one `GROUP BY RepairTicket.status` query over the same joins; `None` from `_ticket_filter_conditions` → `{"total": 0, "by_status": {}}`.

- [ ] **Step 4: Run to verify they pass** — file: 10 passed; full suite: 150 passed, 17 skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_ticket_list_paging.py
git commit -m "feat(api): ticket counts by status for list tabs"
```

---

### Task 3: Compress responses and index the list ordering

**Files:**
- Modify: `backend/app/main.py` — add `GZipMiddleware` next to the CORS block
- Modify: `backend/app/models.py` — `RepairTicket.__table_args__`
- Create: `backend/scripts/migrate_ticket_indexes.py`
- Test: `backend/tests/test_response_compression.py` (create)

**Interfaces:**
- Produces: index `ix_repair_tickets_created_at_id` on `repair_tickets (created_at DESC, ticket_id DESC)` — matches the `ORDER BY` of `list_tickets`.

- [ ] **Step 1: Write the failing tests**

```python
def test_large_json_is_gzipped(client, admin_headers):
    r = client.get("/api/tickets?limit=200", headers={**admin_headers, "Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"

def test_small_json_is_not_gzipped(client):
    r = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") is None

def test_ticket_ordering_index_exists():
    from sqlalchemy import text
    from app.models import SessionLocal
    with SessionLocal() as db:
        names = {r[0] for r in db.execute(text("select indexname from pg_indexes where tablename='repair_tickets'"))}
    assert "ix_repair_tickets_created_at_id" in names
```

The first test needs at least ~1 kB of ticket JSON: create three tickets in the fixture as in Task 1.

- [ ] **Step 2: Run to verify they fail** — expected: `content-encoding` is `None`; index missing.

- [ ] **Step 3: Implement**

- `app.add_middleware(GZipMiddleware, minimum_size=1024)` (from `fastapi.middleware.gzip`).
- Declare the index in `RepairTicket.__table_args__` so fresh databases get it from `create_all()`.
- `migrate_ticket_indexes.py`: same header/CLI style as `backend/scripts/migrate_pm.py`; runs `CREATE INDEX IF NOT EXISTS ix_repair_tickets_created_at_id ON repair_tickets (created_at DESC, ticket_id DESC)` and prints the result. Idempotent. (`create_all()` does not add indexes to existing tables — HANDOFF.md §4.5.)

- [ ] **Step 4: Apply and verify**

```bash
docker compose up -d --build backend
MSYS_NO_PATHCONV=1 docker exec -w /app smart_classroom_backend python scripts/migrate_ticket_indexes.py
```
Then the test file: 3 passed; full suite: 153 passed, 17 skipped.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/models.py backend/scripts/migrate_ticket_indexes.py backend/tests/test_response_compression.py
git commit -m "perf(api): gzip responses and index ticket list ordering"
```

---

### Task 4: Frontend test runner, ticket query helpers, API client

**Files:**
- Modify: `frontend/package.json` (`"test": "vitest run"`, devDependency `vitest`)
- Create: `frontend/src/components/tickets/ticketQuery.ts`
- Create: `frontend/src/components/tickets/ticketQuery.test.ts`
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Produces, in `ticketQuery.ts`:

```ts
export const PAGE_SIZE = 20;
export type TicketTabId = 'all' | 'new' | 'assigned' | 'in_progress' | 'waiting' | 'resolved' | 'done';
export const TICKET_TABS: { id: TicketTabId; label: string; statuses: string[] }[];
//  all ทั้งหมด [] · new รอรับเรื่อง [new] · assigned มอบหมายแล้ว [assigned] · in_progress กำลังซ่อม [in_progress]
//  waiting รออะไหล่/ผู้ใช้ [pending, waiting_parts, waiting_user] · resolved ซ่อมเสร็จ [resolved] · done ปิดแล้ว [closed, cancelled]
export interface TicketFilters { q: string; tab: TicketTabId; priority: string; deviceType: string; deviceCategory: string; organizationId: string; }
export const EMPTY_FILTERS: TicketFilters;                     // tab 'all', everything else ''
export function buildTicketParams(f: TicketFilters, page: number): Record<string, string>;  // omits empty values; q trimmed; status joined with ','; limit '20'; offset (page-1)*20
export function pageCount(total: number): number;               // at least 1
export function clampPage(page: number, total: number): number; // into 1..pageCount(total)
export function tabCount(tab: TicketTabId, byStatus: Record<string, number>, total: number): number;
export function activeFilterCount(f: TicketFilters): number;    // counts priority, deviceType, deviceCategory, organizationId (not q, not tab)
```

- Produces, in `api` (client.ts):

```ts
listTicketsPage: (params: Record<string, string>) => Promise<{ items: Ticket[]; total: number }>;  // total from X-Total-Count; falls back to items.length if the header is absent
ticketCounts: (params: Record<string, string>) => Promise<{ total: number; by_status: Record<string, number> }>;  // sends params minus status/limit/offset
```

- [ ] **Step 1: Install the runner**

```bash
docker exec smart_classroom_frontend npm install -D vitest@^2
```
Add the `test` script. Vitest reads `vite.config.ts`; no separate config.

- [ ] **Step 2: Write the failing tests** (`ticketQuery.test.ts`)

```ts
it('builds params for a plain first page', () => {
  expect(buildTicketParams(EMPTY_FILTERS, 1)).toEqual({ limit: '20', offset: '0' });
});
it('joins the statuses of a tab and trims the search text', () => {
  expect(buildTicketParams({ ...EMPTY_FILTERS, tab: 'waiting', q: '  จอ  ' }, 3))
    .toEqual({ q: 'จอ', status: 'pending,waiting_parts,waiting_user', limit: '20', offset: '40' });
});
it('maps filter fields to API parameter names', () => {
  expect(buildTicketParams({ ...EMPTY_FILTERS, priority: 'high', deviceType: 'Projector', deviceCategory: 'จอภาพ', organizationId: '7' }, 1))
    .toMatchObject({ priority: 'high', device_type: 'Projector', device_category: 'จอภาพ', organization_id: '7' });
});
it('never reports zero pages', () => { expect(pageCount(0)).toBe(1); expect(pageCount(20)).toBe(1); expect(pageCount(21)).toBe(2); });
it('falls back to the last page that has rows', () => {
  expect(clampPage(3, 40)).toBe(2); expect(clampPage(0, 40)).toBe(1); expect(clampPage(5, 0)).toBe(1);
});
it('sums tab counts across the statuses of the tab', () => {
  const by = { new: 4, pending: 1, waiting_user: 2, closed: 5, cancelled: 1 };
  expect(tabCount('waiting', by, 13)).toBe(3); expect(tabCount('done', by, 13)).toBe(6);
  expect(tabCount('all', by, 13)).toBe(13); expect(tabCount('resolved', by, 13)).toBe(0);
});
it('counts only the dropdown filters as active', () => {
  expect(activeFilterCount({ ...EMPTY_FILTERS, q: 'x', tab: 'new', priority: 'high', organizationId: '7' })).toBe(2);
});
```

- [ ] **Step 3: Run to verify they fail** — `docker exec smart_classroom_frontend npx vitest run`; expected: cannot resolve `./ticketQuery`.

- [ ] **Step 4: Implement `ticketQuery.ts` and the two client methods**

`listTicketsPage` cannot use the shared `request<T>()` (it discards headers): add `requestWithHeaders<T>(path): Promise<{ data: T; headers: Headers }>` beside it, sharing the same error handling, and build on that.

- [ ] **Step 5: Run to verify** — vitest: 7 passed; `npx tsc --noEmit`: no output.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/components/tickets frontend/src/api/client.ts
git commit -m "feat(web): ticket query helpers, paged client calls, vitest"
```

---

### Task 5: Tickets page as its own module with server paging and status tabs

**Files:**
- Create: `frontend/src/components/tickets/ticketLabels.ts` — move `STATUS_LABELS_TICKET`, `ALL_STATUSES`, `ticketDetailStatus`, `ticketDetailPriority`, `ticketDetailChannel`, `ticketDetailDate` out of `App.tsx` (~lines 1230–1245) unchanged, exported
- Create: `frontend/src/components/tickets/TicketDetailSheet.tsx` — the `detailTicket && <div className="panel-overlay">…` block of `App.tsx` (~lines 1575–1645) with its loading logic
- Create: `frontend/src/components/tickets/TicketsPage.tsx`
- Create: `frontend/src/components/tickets/Pagination.tsx`
- Create: `frontend/src/styles/tickets.css`
- Modify: `frontend/src/App.tsx` — delete the `TicketsPage` function (~lines 1247–1649) and the moved constants; import them; update the `<TicketsPage … />` call site (~line 3140)

**Interfaces:**
- Consumes: everything Task 4 produces.
- Produces:

```ts
// TicketsPage.tsx — default export
interface TicketsPageProps { onBack: () => void; onTicketsChanged: () => void; canManage: boolean; focusId?: string; onFocusHandled?: () => void; }
// TicketDetailSheet.tsx — default export
interface TicketDetailSheetProps { ticketId: string; initial?: Ticket; canManage: boolean; onClose: () => void; onChanged: () => void; }
// Pagination.tsx — default export
interface PaginationProps { page: number; total: number; pageSize: number; onPage: (page: number) => void; }
```

`TicketsPage` no longer receives `tickets`. `App.tsx` keeps its own `tickets` state for the Dashboard and header search (plan 2 removes that).

**Behaviour to build:**
- State: `filters: TicketFilters`, `page`, `items`, `total`, `counts`, `loading`, `error`. On any change of `filters` or `page`, fetch `api.listTicketsPage(buildTicketParams(filters, page))` and `api.ticketCounts(...)` in parallel.
- Search text is debounced 300 ms before it enters `filters.q`; changing any filter or tab resets `page` to 1.
- Request-generation guard (same pattern as `loadGeneration` in `AppInner`): a response is applied only if it belongs to the latest request.
- After a fetch, if `page !== clampPage(page, total)`, set the page to the clamped value (which refetches).
- Tabs: a `role="tablist"` row built from `TICKET_TABS`, each showing `tabCount(...)`; arrow keys move between tabs.
- Row status `<select>` (existing behaviour, `api.updateStatus` with `force: true`) and the "รายละเอียด" button stay as they are; after a successful change refetch the current page and call `onTicketsChanged()`.
- Filter dropdown options: priority fixed list with Thai labels from `ticketDetailPriority`; schools from `api.listOrganizations()`; device type and category from the existing `/device-types` and `/device-categories` client methods (client.ts ~lines 430–436). Load once on mount; a failed load leaves that dropdown disabled.
- `focusId`: open `<TicketDetailSheet ticketId={focusId} />` directly (it loads by id), then call `onFocusHandled()`. Do not search the current page for it.
- Loading: keep the previous rows visible at reduced opacity with `aria-busy="true"`; first load shows 5 skeleton rows. Error: inline `role="alert"` with a "ลองใหม่" button. Empty: existing `empty-state` markup, text "ไม่พบใบงานที่ตรงกับตัวกรอง" when any filter is set, otherwise "ยังไม่มีใบงาน".
- `Pagination`: "ก่อนหน้า" / "ถัดไป" buttons, text `หน้า {page} จาก {pageCount}` and `แสดง {from}–{to} จาก {total} รายการ`; hidden when `total <= pageSize`; `<nav aria-label="เปลี่ยนหน้า">`.
- Page heading becomes "ใบงานซ่อม" with subtitle `{total} รายการ`.
- Replace the inline styles of the moved markup with classes in `tickets.css`.

- [ ] **Step 1: Move labels and the detail sheet, wire `App.tsx`, keep behaviour identical**

Run: `docker exec smart_classroom_frontend npx tsc --noEmit` → no output. Open `http://localhost:5173`, log in, open Tickets, open a row: same content as before.

- [ ] **Step 2: Commit the pure move**

```bash
git add frontend/src
git commit -m "refactor(web): move tickets page and detail sheet out of App.tsx"
```

- [ ] **Step 3: Replace client-side filtering with server paging, tabs and `Pagination`** as specified above.

- [ ] **Step 4: Verify**

`npx tsc --noEmit` → no output; `npx vitest run` → 7 passed.
In the browser with the seeded data (66 tickets): the list shows 20 rows and "หน้า 1 จาก 4"; tab counts add up to 66; typing `SCHM03` narrows the list after a short pause and resets to page 1; the Network panel shows `tickets?limit=20…` with `content-encoding: gzip`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat(web): server-paged ticket list with status tabs and search"
```

---

### Task 6: Phone layout — ticket cards and collapsed filters

**Files:**
- Create: `frontend/src/components/tickets/TicketCard.tsx`
- Modify: `frontend/src/components/tickets/TicketsPage.tsx`, `frontend/src/styles/tickets.css`

**Interfaces:**
- Produces: `TicketCard` default export, props `{ ticket: Ticket; onOpen: (t: Ticket) => void }`.

**Behaviour to build:**
- At `max-width: 640px` the table is hidden and a `<ul>` of `TicketCard` is shown; above it, the reverse. Both render from the same `items` (CSS switch, no JS width detection).
- Card content, top to bottom: status badge + priority badge (priority text in Thai) on one line with the created date right-aligned; title (2-line clamp); device label (1-line clamp); school name · reporter; ticket ID in the mono style of `.table-id`. The whole card is one `<button>` with `aria-label="ดูรายละเอียดใบงาน {ticket_id}"`. No status `<select>` on cards — status changes happen in the detail sheet (Task 7).
- Filters at `max-width: 640px`: the search box and the tab row stay visible (tab row scrolls horizontally, `scroll-snap-type: x proximity`, no visible scrollbar); the four dropdowns collapse behind a "ตัวกรอง" button that shows `activeFilterCount(filters)` as a badge when non-zero and toggles them with `aria-expanded` / `aria-controls`.
- Pagination buttons span the full width, 44 px high.

- [ ] **Step 1: Build `TicketCard` and the responsive rules.**

- [ ] **Step 2: Verify**

`npx tsc --noEmit` → no output.
Chrome DevTools device mode at 390 × 844 on the Tickets page: no horizontal page scroll (`document.documentElement.scrollWidth === 390`); first card fully visible without scrolling past filters; every card shows ID, title, status and device; "ตัวกรอง" reveals four dropdowns. At 1440 px the table is unchanged from Task 5.

- [ ] **Step 3: Commit**

```bash
git add frontend/src
git commit -m "feat(web): ticket cards and collapsible filters on phones"
```

---

### Task 7: Workflow actions in the detail sheet

**Files:**
- Create: `frontend/src/components/tickets/ticketActions.ts`
- Create: `frontend/src/components/tickets/ticketActions.test.ts`
- Create: `frontend/src/components/ConfirmDialog.tsx`
- Modify: `frontend/src/components/tickets/TicketDetailSheet.tsx`, `frontend/src/styles/tickets.css`

**Interfaces:**
- Produces:

```ts
// ticketActions.ts
export type TicketActionId = 'accept' | 'resolve' | 'close' | 'reopen' | 'cancel';
export interface TicketAction { id: TicketActionId; label: string; kind: 'primary' | 'secondary'; needs: 'none' | 'solution' | 'note'; }
export function actionsFor(status: string, canManage: boolean): TicketAction[];
export function validateActionInput(action: TicketAction, input: { solution?: string; note?: string }): string | null;  // Thai error text or null

// ConfirmDialog.tsx — default export; reused by plan 3 to replace native confirm()
interface ConfirmDialogProps { title: string; message: string; confirmLabel: string; danger?: boolean; busy?: boolean; onConfirm: () => void; onCancel: () => void; }
```

Rules for `actionsFor` (empty list when `canManage` is false):

| status | primary | secondary |
|---|---|---|
| `new`, `assigned` | accept "รับงาน" (`none`) | cancel "ยกเลิกงาน" (`note`) |
| `in_progress`, `pending`, `waiting_parts`, `waiting_user` | resolve "บันทึกผลซ่อม" (`solution`) | cancel "ยกเลิกงาน" (`note`) |
| `resolved` | close "ปิดงาน" (`none`) | reopen "เปิดงานใหม่" (`note`) |
| `closed`, `cancelled` | — | reopen "เปิดงานใหม่" (`note`) |

`validateActionInput`: `solution` trimmed shorter than 3 characters → `'กรุณากรอกวิธีแก้ไขอย่างน้อย 3 ตัวอักษร'`; `note` trimmed empty → `'กรุณาระบุเหตุผล'`; both capped at 2000 characters → `'ข้อความยาวเกิน 2000 ตัวอักษร'` (limits from `TicketResolveReq` / `TicketCommentReq`).

- [ ] **Step 1: Write the failing tests**

```ts
it('offers nothing to read-only users', () => { expect(actionsFor('new', false)).toEqual([]); });
it('offers accept first on a new ticket', () => {
  expect(actionsFor('new', true).map(a => a.id)).toEqual(['accept', 'cancel']);
  expect(actionsFor('assigned', true)[0]).toMatchObject({ id: 'accept', kind: 'primary', needs: 'none' });
});
it('offers resolve while work is under way or waiting', () => {
  for (const s of ['in_progress', 'pending', 'waiting_parts', 'waiting_user'])
    expect(actionsFor(s, true).map(a => a.id)).toEqual(['resolve', 'cancel']);
});
it('offers close then reopen on a resolved ticket', () => { expect(actionsFor('resolved', true).map(a => a.id)).toEqual(['close', 'reopen']); });
it('offers only reopen on finished tickets', () => {
  expect(actionsFor('closed', true).map(a => a.id)).toEqual(['reopen']);
  expect(actionsFor('cancelled', true).map(a => a.id)).toEqual(['reopen']);
});
it('offers nothing for an unknown status', () => { expect(actionsFor('weird', true)).toEqual([]); });
it('requires a solution of three characters', () => {
  const resolve = actionsFor('in_progress', true)[0];
  expect(validateActionInput(resolve, { solution: ' ก ' })).toBe('กรุณากรอกวิธีแก้ไขอย่างน้อย 3 ตัวอักษร');
  expect(validateActionInput(resolve, { solution: 'เปลี่ยนสาย HDMI' })).toBeNull();
});
it('requires a reason to cancel or reopen', () => {
  const cancel = actionsFor('new', true)[1];
  expect(validateActionInput(cancel, { note: '   ' })).toBe('กรุณาระบุเหตุผล');
  expect(validateActionInput(cancel, { note: 'x'.repeat(2001) })).toBe('ข้อความยาวเกิน 2000 ตัวอักษร');
});
```

- [ ] **Step 2: Run to verify they fail** — cannot resolve `./ticketActions`.

- [ ] **Step 3: Implement `ticketActions.ts`** — vitest: 15 passed in total.

- [ ] **Step 4: Build the sheet footer and `ConfirmDialog`**

- Footer, left to right: primary action button, secondary action button, spacer, "ปิด". Delete leaves the footer: it becomes a text-style button "ย้ายไปถังกู้คืน" at the bottom of the sheet body under a divider, opening `ConfirmDialog` (`danger`, message `ย้ายใบงาน {ticket_id} ไปถังข้อมูลที่กู้คืนได้?`).
- Actions with `needs: 'solution'` expand an inline form in the sheet: "วิธีแก้ไข" (required textarea) and "สาเหตุ" (optional), submitting `{ solution, root_cause }`. Actions with `needs: 'note'` expand one required textarea "เหตุผล". `needs: 'none'` runs immediately.
- Calls: `api.acceptTicket`, `api.resolveTicket`, `api.closeTicket(id, {})`, `api.reopenTicket(id, note)`, `api.cancelTicket(id, note)` (all exist in `client.ts` ~lines 372–383).
- While a call runs, all action buttons are disabled and the pressed one shows "กำลังบันทึก…". On success: reload the ticket in the sheet, call `onChanged()`. On failure: show `error.message` in a `role="alert"` line above the footer and reload the ticket (it may have changed under the user). No `alert()` / `window.confirm()` anywhere in `components/tickets/`.
- `ConfirmDialog`: `role="alertdialog"`, `aria-modal="true"`, focus moves to the cancel button on open and returns to the opener on close, Escape cancels, Tab stays inside.

- [ ] **Step 5: Verify**

`npx tsc --noEmit` → no output; `npx vitest run` → 15 passed; `grep -rnE "\b(alert|confirm|prompt)\(" frontend/src/components/tickets` → no matches.
In the browser as `admin`: a `new` ticket → "รับงาน" → status shows กำลังดำเนินการ and the list row updates; "บันทึกผลซ่อม" with an empty field shows the validation text and sends nothing; with text it becomes ซ่อมเสร็จ; "ปิดงาน" → ปิดงาน. In a second tab accept another `new` ticket, then press "รับงาน" on it in the first tab: the server's message appears in the sheet and the status refreshes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src
git commit -m "feat(web): accept, resolve, close, reopen and cancel from ticket detail"
```

---

### Task 8: Whole-feature verification

**Files:** none changed unless a check fails.

- [ ] **Step 1: Automated checks**

Backend full suite → 153 passed, 17 skipped. `npx vitest run` → 15 passed. `npx tsc --noEmit` → no output. `docker exec smart_classroom_frontend npm run build` → succeeds.

- [ ] **Step 2: Measure against the spec's success measures** (seeded data, logged in as `admin`)

| Measure | How | Pass |
|---|---|---|
| Page height at 1440 px | DevTools console on Tickets: `document.documentElement.scrollHeight` | < 1800 |
| First request size | Network panel, `tickets?limit=20…` | 20 rows, `content-encoding: gzip` |
| Phone readability | device mode 390 × 844 | `document.documentElement.scrollWidth === 390` |
| Workflow from the sheet | accept → resolve → close on one ticket | each step updates sheet and list |

- [ ] **Step 3: Review Focus items 4 and 5 by hand**

Throttle the network to "Slow 3G", type `SCH`, then quickly switch tabs twice: the list ends on the last tab chosen. Repeat the two-tab accept conflict from Task 7.

- [ ] **Step 4: Regression pass on what `App.tsx` still owns**

Dashboard loads with charts; header search finds a ticket by ID and opens its sheet; Devices page "open ticket" link opens the sheet; public pages `/?publicreport=1` and `/?ticket=` render.

- [ ] **Step 5: Commit any fixes, then stop.** Do not merge or push; report results to the owner.
