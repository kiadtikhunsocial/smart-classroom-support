# UX + Speed Revamp — Design

Date: 2026-11-13. Source: live audit of the local build with seeded data
(5 schools, 100 devices, 66 tickets), screenshots at 1440 px and 390 px.

## Goal

Make the staff side of Smart Classroom Support quicker to use and quicker to
load, without changing what it does. Technicians on phones come first.

## Decisions

- **Priority user:** technician (`it_support`) on a phone, then admins on desktop.
- **Look:** keep the current theme system (`data-mode` + `data-accent`, default
  dark + purple). The problems are page structure, not colour.
- **Scope rule:** no schema changes beyond adding indexes; no change to LINE,
  n8n, chatbot or public pages; API changes are additive and backward compatible
  (n8n and the public pages call the same endpoints).
- **Delivery:** four independent plans, each shippable on its own branch.

## Findings the plans answer

| # | Finding | Evidence |
|---|---|---|
| 1 | No pagination | Tickets page 9,919 px for 66 rows; Devices 9,031 px for 100 |
| 2 | Client loads everything | `App.tsx` `reloadData` fetches all tickets (101 kB) and all devices (160 kB) uncompressed on every Dashboard visit |
| 3 | Mobile tickets unusable | wide table in 390 px, five stacked filters before any row |
| 4 | Ticket detail has no workflow actions | footer holds only "ปิดรายละเอียด" and "ลบใบงาน"; accept/resolve/close endpoints exist but are not wired here |
| 5 | Dashboard lists every device | 8,416 px desktop, about 26,600 px on a phone |
| 6 | No URLs | page is React state; refresh returns to Dashboard, Back does nothing |
| 7 | Inconsistent UI | English/Thai menu mix, 33 native `alert/confirm/prompt` calls, clipped Devices actions column |
| 8 | Hard to change | `App.tsx` 3,243 lines, 196 inline styles, 20 layered CSS files, no frontend tests |

## Plans

1. **Tickets: fast and usable** (findings 1–4 for tickets, starts 8).
   Server-side search, paging and counts; gzip; `created_at` index. Tickets page
   moved out of `App.tsx` with status tabs, 20 per page, cards on phones, and
   accept / resolve / close / reopen / cancel in the detail sheet.
   Plan: `docs/superpowers/plans/2026-11-13-tickets-fast-usable.md`.
2. **Dashboard + navigation** (5, 6, rest of 2). Replace the device list with a
   "my work today" queue fed by a small summary endpoint; stop loading all
   tickets and devices into `App` state; give every page a URL.
3. **Consistency** (7). Devices page paging and mobile cards; all-Thai menu;
   in-app confirm dialog and toast replacing the 33 native dialogs; shared
   Button / Table / EmptyState / Skeleton.
4. **Technician mobile + cleanup** (8). Bottom tab bar on phones; PM and QR
   print pages; merge the layered CSS files; move inline styles to classes.

## Success measures for plan 1

- Tickets page height at 1440 px with 66 tickets: under 1,800 px (was 9,919).
- First Tickets request: 20 rows, gzip-encoded (was 66 rows, 101 kB plain).
- On a 390 px screen a ticket's ID, title, status and device are readable
  without horizontal scrolling.
- A technician can accept and resolve a ticket from the detail sheet.
- Backend suite stays green (baseline 140 passed, 17 skipped); `tsc --noEmit` clean.
