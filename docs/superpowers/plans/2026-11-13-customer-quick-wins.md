# Customer Side: Quick Wins — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A teacher who reports a broken device or checks a ticket on a phone sees their ticket number, sees the result of what they tapped, and is not kept waiting on the staff notification.

**Architecture:** Two CSS overrides stop resetting `background-clip`; the public home page moves focus to tracking and warranty results; `_notify_n8n` hands the webhook call to a single background worker so all seven call sites return immediately. No API contract, route or form field changes.

**Tech Stack:** React 18 + Vite 5 (frontend), FastAPI (backend), pytest 8.3.4, puppeteer-core for browser checks (scratchpad only, not a project dependency).

**Spec:** `docs/superpowers/specs/2026-11-13-ux-speed-revamp-design.md` (plan 5, customer side — findings below were measured 2026-11-13 on a 390 × 844 phone viewport with seeded data).

## Findings this plan answers

| # | Finding | Evidence |
|---|---|---|
| C1 | Ticket number invisible on the new form's success screen | `.pr-ticket-no` computed `background-clip: border-box`, `color: transparent`; `public-theme.css:594` |
| C2 | Ticket number invisible on the tracking result | `.ph-result-no strong`, same cause; `public-theme.css:356` |
| C3 | Tracking and warranty results render below the fold; `scrollY` stays 0 after tapping, so nothing appears to happen | home page, phone |
| C4 | Every ticket create and status change waits for the n8n webhook | `_notify_n8n` calls `httpx.post(..., timeout=2.0)` inline; locally 7.9 s because DNS for `n8n` fails outside the timeout; in production it costs the Railway round trip, capped near 2 s |

## Global Constraints

- Branch `feat/customer-quick-wins` from `main`. No push, no deploy.
- Printed QR URLs `/scan?t=<token>` and `/scan?device=<id>` must keep working unchanged.
- No change to API paths, request or response bodies, status codes or rate limits. A 404 for an unknown ticket number stays a 404.
- Notification events must still reach n8n in the order they were raised (created before status_changed).
- Commit after each task, ending with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Review Focus

1. **Light mode** — the CSS fix must hold in both `data-mode="light"` and `"dark"`. Checked in Task 1.
2. **n8n down or slow** — requests must stay fast and the worker must not pile up threads. Tested in Task 3.
3. **Process exit with queued events** — losing the last in-flight notification on shutdown is acceptable (same as today's "fire-and-forget" intent); crashing is not.
4. **Searching the same ticket twice** — focus must still move to the result. Checked in Task 2.
5. **Screen readers** — the result must be announced, not only scrolled to. Checked in Task 2.

---

### Task 1: Make gradient ticket numbers visible

**Files:** Modify `frontend/src/styles/public-theme.css` lines 356–358 and 594–596.

- [ ] **Step 1: Reproduce** — browser check: on `/?ticket=TK.SCHM05.26.0003-0` read `getComputedStyle(document.querySelector('.ph-result-no strong')).backgroundClip`. Expected now: `border-box` (bug).
- [ ] **Step 2: Fix** — in both rules replace the `background:` shorthand with `background-image:`; leave the gradient values as they are.
- [ ] **Step 3: Verify** — the same check returns `text` for `.ph-result-no strong` and for `.pr-ticket-no` on the new-form success screen, in light and dark mode; the number is readable in screenshots. `grep -nE "^\s*background:" ` inside any rule that targets `.ph-result-no strong`, `.pr-ticket-no` or `.ph-hero-accent` → no matches.
- [ ] **Step 4: Commit** — `fix(public): show ticket numbers rendered as gradient text`

### Task 2: Bring tracking and warranty results into view

**Files:** Modify `frontend/src/components/PublicHomeView.tsx` (tracking result block ~line 660, warranty result block), `frontend/src/styles/public-home.css` if a focus style is needed.

**Behaviour:**
- When a tracking search or a warranty check finishes — found, not found, or error — scroll the result container into view (`block: 'start'`, `behavior: 'smooth'` unless `prefers-reduced-motion: reduce`, then `'auto'`) and move focus to it. Give the container `tabIndex={-1}` and a visible `:focus-visible` outline using existing tokens.
- Wrap each result area in a region with `aria-live="polite"` so the outcome is announced.
- Runs on every completed search, including a repeat of the same number.
- Account for the fixed header: `scroll-margin-top` equal to the header height.

- [ ] **Step 1: Reproduce** — browser check: search a ticket on the phone viewport; `window.scrollY` stays `0`.
- [ ] **Step 2: Implement** as above.
- [ ] **Step 3: Verify** — tracking search: result heading visible inside the viewport, `document.activeElement` is the result container; same for a not-found number and for a warranty check; repeat the same search and focus moves again. `npx tsc --noEmit` clean.
- [ ] **Step 4: Commit** — `feat(public): scroll and focus tracking and warranty results`

### Task 3: Send n8n notifications off the request path

**Files:** Modify `backend/app/main.py` (`_notify_n8n`, ~line 6605). Test: `backend/tests/test_notify_async.py` (create).

**Interfaces:**
- `_notify_n8n(event: str, payload: dict) -> None` keeps its signature and stays safe to call anywhere.
- New module-level `_NOTIFY_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="n8n-notify")`; one worker keeps event order and caps threads at one.
- New `_flush_notifications(timeout: float = 5.0) -> None` that waits for queued sends; tests use it, application code does not.

- [ ] **Step 1: Write the failing tests**

```python
def test_notify_returns_before_the_webhook_finishes(monkeypatch):
    calls = []
    def slow_post(url, json, timeout):
        time.sleep(1.0); calls.append(json["event"])
    monkeypatch.setattr(main.httpx, "post", slow_post)   # see Step 3: httpx imported at module level
    t = time.perf_counter()
    main._notify_n8n("ticket.created", {"ticket_id": "X"})
    assert time.perf_counter() - t < 0.2
    main._flush_notifications()
    assert calls == ["ticket.created"]

def test_notify_preserves_event_order(monkeypatch):
    seen = []
    monkeypatch.setattr(main.httpx, "post", lambda url, json, timeout: seen.append(json["event"]))
    for e in ["ticket.created", "ticket.status_changed", "ticket.status_changed"]:
        main._notify_n8n(e, {"ticket_id": "X"})
    main._flush_notifications()
    assert seen == ["ticket.created", "ticket.status_changed", "ticket.status_changed"]

def test_notify_swallows_webhook_errors(monkeypatch):
    def boom(*a, **k): raise RuntimeError("n8n down")
    monkeypatch.setattr(main.httpx, "post", boom)
    main._notify_n8n("ticket.created", {"ticket_id": "X"})
    main._flush_notifications()   # no exception escapes
```

- [ ] **Step 2: Run to verify they fail** — first test fails on elapsed time (~1.0 s), `_flush_notifications` missing.
- [ ] **Step 3: Implement** — import `httpx` at module level (so tests can patch `main.httpx.post`); `_notify_n8n` builds the URL and body, then `_NOTIFY_POOL.submit(_send_notification, url, body)`; `_send_notification` does the `httpx.post(..., timeout=2.0)` inside `try/except Exception`. `_flush_notifications` submits a no-op and waits on its future with the timeout. Keep the existing `tests/test_line_report_bridge.py` monkeypatch of `_notify_n8n` working.
- [ ] **Step 4: Verify** — new file: 3 passed. Full suite: previous totals + 3, no new failures. `curl` timing of `POST /api/tickets` locally: under 0.5 s (was 7.9 s). Browser: sticker form success screen appears within 1 s of tapping send.
- [ ] **Step 5: Commit** — `perf(api): send n8n notifications on a background worker`

---

## Decisions for the owner (no code until answered)

1. **One repair form.** The QR sticker opens the older form inside `App.tsx` (posts to `POST /api/tickets`); the home page opens the newer 3-step form (`POST /api/public/report`, which also binds LINE report links). Only the older form has AI self-diagnosis, the "fixed it myself" record behind `self_service_total`, and an email field; only the newer one requires name and phone. Recommendation: keep the newer form, port AI diagnosis and the self-service record into it, and route `/scan?t=` and `/scan?device=` to it.
2. **Who sets priority.** Teachers currently pick Low/Normal/High/Critical (English labels on the sticker form), and that choice sets the SLA deadline. Options: keep it with Thai labels; or remove it and let staff set priority.
3. **Public pages in dark mode by default.** Teachers often report in bright classrooms. Option: default public pages to light, keep the toggle.
4. **Report rate limit.** `POST /api/tickets` and `POST /api/public/report` allow 10 per minute per client IP, but the server is started without trusting proxy headers, so on Render every request may appear to come from the proxy address — 10 reports per minute for the whole system. Check: Render logs show `ip=` on every request; if they all show the same few addresses, the limit is shared. Fix then is a start-command change (`--proxy-headers --forwarded-allow-ips`), which needs the owner's go-ahead because it touches production config.
