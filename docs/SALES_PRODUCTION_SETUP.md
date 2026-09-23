# Sales/customer rollout checklist

The customer form stores contact requests in PostgreSQL. A "payment request" is
only a staff review item; this application does **not** take or verify payment.

## Render backend

Deploy the backend commit first. Startup creates `sales_records` and
`customer_signup_invites` through `init_db()`; confirm `/health` returns 200.
Keep the existing `DATABASE_URL`, `JWT_SECRET`, and `N8N_SHARED_SECRET` values.

For Google Sheets mirroring, set these Render environment variables in the
Dashboard, not in Git:

- `GOOGLE_SHEET_ID`: ID between `/d/` and `/edit` in the spreadsheet URL.
- `GOOGLE_SERVICE_ACCOUNT_JSON`: complete service-account JSON. Share that
  spreadsheet with its `client_email` as Editor. Never paste the JSON in chat.
- `GOOGLE_SHEET_RANGE=Members!A1`, `GOOGLE_SHEET_LEAD_RANGE=Leads!A1`,
  `GOOGLE_SHEET_SALES_RANGE=Sales!A1`. `Leads` and `Sales` tabs are created on
  their first sync when missing.
- `CUSTOMER_SIGNUP_URL=https://iwasmart-service.vercel.app/?customer=1`.

For LINE group notifications, keep valid `LINE_CHANNEL_TOKEN` and
`LINE_GROUP_ID`; add the bot to the staff group. A missing integration is shown
on the sales page. The database remains authoritative, and an administrator
can request a Sheet retry from the sales page.

## Promote the five local demo schools

This copies only `SCH-M01` through `SCH-M05`: schools, rooms, devices, repair
tickets/history, PM plans/tasks and health flags. It does **not** copy test
users/passwords, audit logs, LINE IDs or the separate sales demo leads.
Production will visibly contain example schools, as requested. The import is
additive/idempotent; it does not overwrite existing records. The selected local
rows are mechanically exported to `backend/scripts/demo_schools.json` with QR
tokens removed. Render imports the pack using its existing private DATABASE_URL
on startup. A database marker makes the operation **one-time**, including
future service restarts. No database credential is read out of Render.

Verify the Render deploy log contains `Committed demo pack:` with counts, or
`Demo pack already applied; no changes`. After import, sign in to production
as staff and check the five schools and their device/ticket counts. If import
fails, the deployment fails rather than starting with partially copied data;
the prior live deploy remains available.

### Manual fallback only

If the internal Render import cannot be used, open **your own PowerShell** in
the repository and run:

```powershell
cd C:\Users\nonam\smart-classroom-support
backend\.venv\Scripts\python.exe backend\scripts\promote_local_mockup.py
backend\.venv\Scripts\python.exe backend\scripts\promote_local_mockup.py --apply
```

The second command prompts for the production `DATABASE_URL` with hidden input,
shows only its host/database, then requires the exact confirmation text
`COPY FIVE DEMO SCHOOLS`. Obtain the URL from Render → backend → Environment.
Do not use the public `https://…onrender.com` web address. Do not put the URL
in a command argument, file, screenshot or chat. Keep Docker PostgreSQL running
so the script can read local data. The script requires TLS to the remote DB and
commits all selected records in one transaction; an error rolls them all back.

Then check customer signup, separate deals/payment requests, and the integration
indicators. Do not enter real card/account credentials in payment-request notes.
