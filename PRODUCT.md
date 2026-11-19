# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Customers (reporters):** teachers and school staff whose classroom device (projector, interactive board, PC, speaker, network) has a problem. They use a phone, usually by scanning the QR sticker on the device, with no account. Job: report the problem in under a minute, then check progress later by ticket number or device code.
- **Technicians (`it_support`):** field staff who move between schools and rooms. They work on a phone at the device. Job: get offered or assigned jobs, accept, see who reported and where, contact them, update the status, and close the job.
- **Admins (`owner`, `super_admin`, `admin`, `admin_school`):** office staff on a desktop computer. Job: watch incoming tickets, assign or reassign work, manage devices, schools, users, PM plans, knowledge base, and reports.

## Product Purpose

Smart Classroom Support is an online repair-request and maintenance system for classroom devices across several schools. It turns a QR scan into a tracked repair ticket, routes it to a free technician automatically, and gives the school a record of every device's issues and maintenance. Success: a reporter can file a request in seconds without help, a technician always knows the next job, and an admin can see the state of all work at a glance.

## Positioning

Each device carries its own QR code, so a report arrives already tied to the exact device, room and school, and dispatch offers it straight to the least-busy reachable technician (LINE or staff app). Reporters need no account and no app.

## Operating Context

- Reporters stand in a classroom, often mid-lesson, on a phone, with poor patience and sometimes poor signal.
- Technicians work standing at the device, one-handed, moving between rooms; LINE OA notifications bring them into the staff app.
- Admins work at a desk with many tickets and devices; multi-school data, super_admin sees all schools.
- Thai is the interface language. Ticket statuses: new, assigned, in_progress, resolved, closed, cancelled.

## Capabilities and Constraints

- React 18 + Vite + TypeScript frontend (Vercel), FastAPI backend (Render), Postgres (Neon), n8n + LINE OA, Gemini AI troubleshooting grounded in the KB.
- No router: staff pages live in the URL hash (`#/tickets`); public pages are chosen by query parameters (`?home=1`, `?device=`, `?t=`).
- Features: public QR repair form, ticket tracking by number or device code, warranty lookup, auto-dispatch with accept/skip offers, tickets workflow, devices, schools, users, PM plans, KB, reports, audit log, sales/registrations.
- Menus and pages stay as they are (owner did not approve hiding or merging menus, 2026-11-19).

## Brand Commitments

- Name: Smart Classroom Support (live site iwasmart-service.vercel.app).
- The dark purple colour theme is binding. Owner rejected a white/orange redesign on 2026-11-19. Layout, spacing, information order, fonts, type sizes, icons and button/menu wording may change; colours may not.

## Evidence on Hand

- Demo data from `scripts/seed_mockup_5_schools.py` (5 schools, 100 devices) is synthetic. No real customer testimonials, metrics or school names may be invented for public pages.

## Product Principles

1. Easy to read: one clear thing per screen region, Thai labels people understand without training.
2. Convenient: fewest taps to report, accept, update or find something; the next action is always obvious.
3. Fast: pages feel instant on a mid-range phone and slow school networks.
4. Clean: remove visual noise, keep what helps the task.
5. Each audience gets its own fit: phone-first for customers and technicians, dense and scannable desktop for admins.

## Accessibility & Inclusion

Thai text must stay legible on small phones; touch targets sized for one-handed use; respect reduced motion.
