# Requirements — ticket_service

Status: locked. The implementation follows this specification.

## Decisions already locked in

- Roles: `agent`, `admin`. No public signup — admins create/manage all user accounts.
- Tickets have an `assigned_agent_id`. An agent may only edit tickets assigned to them; an admin may edit or reassign any ticket.
- `tickets.id` is a surrogate primary key (DB-generated). `ticket_id` (the 9-digit business identifier from csv_extractor) is a separate unique, indexed column.
- CSV bulk import: a row whose `ticket_id` already exists is reported as a row-level conflict/error and skipped; the existing row is not overwritten.
- Ticket fields carried over from csv_extractor: `ticket_id`, `customer`, `priority`, `status`, `hours` — same validation rules as `csv_extractor/src/processing/rules.py` (9-digit ticket_id, customer up to 30 chars, priority in low/medium/high, status in open/closed/in_progress, hours 0.5–40 in steps of 0.5).
- Create/update responses return the full ticket object (not just an id).
- CSV import is admin-only.
- A ticket can be created unassigned (`assigned_agent_id = null`); assignment can happen later via an admin update.
- An admin sets a new user's initial password directly on creation — no email/invite flow (none in scope).
- Once a ticket is `closed`, it is 100% immutable — no field, including `assigned_agent_id`, can change again, for anyone, including admins.
- Bearer tokens expire after a fixed 60-minute TTL; there is no refresh-token flow in v1 — re-login on expiry.
- CSV import file size cap is 5 MB.
- Users (agents and admins) can never be deleted, only deactivated/reactivated — no delete endpoint exists for users in v1.
- A deactivated agent's tickets stay assigned to them (frozen, not auto-reassigned) until an admin manually reassigns them.

## 1. Users

### Agent
- **See:** All tickets (locked decision). All other agent accounts' names for assignment purposes, but not their credentials.
- **Do:** Edit (status, priority, customer, hours) only tickets where `assigned_agent_id` is their own id. Create a new ticket, assigned or unassigned. List/filter/sort/paginate all tickets. Call the summary endpoint. View their own user profile.
- **NOT do:**
  - Edit or reassign a ticket assigned to another agent, or an unassigned ticket, until an admin assigns it to them.
  - Edit any field of a `closed` ticket, ever.
  - Create, edit, deactivate, or delete any user account, including their own.
  - Change their own role.
  - Bulk-import CSVs (admin-only, confirmed).
  - Reassign a ticket to a different agent (reassignment is an admin action).
  - See other agents' auth data (password hash, tokens).

### Admin
- **See:** All tickets, all user accounts (including deactivated ones).
- **Do:** Edit or reassign any ticket regardless of assignment. Create, update, deactivate user accounts (agent or admin). Bulk-import CSVs. Everything an agent can do.
- **NOT do:**
  - Hard-delete a ticket or a user account (no delete endpoint at all in v1 — see Non-goals).
  - Edit any field of a `closed` ticket, or reassign one — closed is terminal for everyone, no admin override.
  - Bypass field-level validation rules (9-digit `ticket_id`, enum values, etc.) even as admin — validation is not a permission, it's data integrity.
  - Impersonate another user (log in *as* them) — out of scope for v1.

## 2. Use cases

1. **Login.** A user submits credentials (username/email + password); on success they receive a bearer token; on failure they get a generic 401 (no "user not found" vs "wrong password" distinction, to avoid leaking which accounts exist).
2. **Agent creates a ticket.** An agent submits `ticket_id, customer, priority, status, hours`. The ticket is validated against the shared rules, created with `status=open` (or as given, if open/in_progress), and returned in full.
3. **Agent updates their own ticket.** An agent moves a ticket they're assigned to from `in_progress` to `closed`. The update succeeds and the closed ticket is returned.
4. **Agent tries to touch someone else's ticket.** An agent attempts to update a ticket assigned to a different agent. Request is rejected with 403, ticket is unchanged.
5. **Agent tries to reopen a closed ticket.** An agent attempts to move a `closed` ticket back to `open` or `in_progress`. Request is rejected with 409 (conflict with current state), ticket is unchanged.
6. **Admin creates a user.** An admin submits a new username, role (`agent`/`admin`), and initial password. The account is created and can log in immediately.
7. **Admin deactivates an agent.** An admin deactivates an agent who has 12 assigned tickets. The agent can no longer log in; their existing tickets remain assigned to them (read-only via that agent) until an admin reassigns them (see FR21).
8. **Admin reassigns a ticket.** An admin moves a ticket from one agent to another; the new agent can now edit it, the old agent can no longer.
9. **Admin bulk-imports a CSV.** An admin uploads a CSV of tickets. Rows are validated; valid, non-duplicate rows are inserted; rows with a duplicate `ticket_id` or a validation failure are skipped and reported individually. The response includes counts and a per-row reason for every skipped row.
10. **Anyone gets a summary.** A logged-in user (agent or admin) requests ticket counts grouped by status, priority, and customer, for all tickets they can see.
11. **Agent lists/filters their queue.** An agent requests page 1 of tickets filtered to `status=open`, sorted by `priority` descending, to triage their day.
12. **Ops health check.** An unauthenticated monitoring probe hits a health endpoint and gets a fast 200 confirming the API and DB connection are alive.

## 3. Functional requirements

### Ticket lifecycle
- Status values: `open`, `in_progress`, `closed`.
- Allowed transitions: `open -> in_progress`, `in_progress -> open`, `open -> closed`, `in_progress -> closed`.
- Disallowed: any transition *out of* `closed`. Once closed, status is terminal for everyone, including admins — if a ticket was closed by mistake, that's a data-correction problem, not a workflow one, and it's out of scope for v1 (see Non-goals). This keeps "closed" an honest audit signal.
- Once `closed`, the ticket is 100% immutable — no field, including `assigned_agent_id`, can change again, for anyone, including admins. There is no admin override.
- `priority`, `customer`, `hours`, and `assigned_agent_id` remain editable while a ticket is `open` or `in_progress`, by whoever is authorized to edit it (the assigned agent for their own fields, an admin for anything including reassignment).

### Auth
1. `POST /auth/login` accepts username + password; returns a bearer token on success, `401` on any failure (bad username or bad password — same response either way).
2. Every non-health endpoint requires a valid bearer token; a missing/invalid/expired token returns `401`.
3. An authenticated request to an endpoint the caller's role doesn't permit returns `403`.
4. Tokens expire after a fixed 60-minute TTL; there is no refresh-token flow in v1 (re-login on expiry).

### Tickets
5. `POST /tickets` creates a ticket; request fails `422` with field-level errors if any field violates the shared validation rules (9-digit `ticket_id`, `customer` ≤30 chars, `priority` in low/medium/high, `status` in open/closed/in_progress, `hours` 0.5–40 in 0.5 steps).
6. `POST /tickets` with a `ticket_id` that already exists fails `409`.
7. `PATCH /tickets/{id}` by an agent whose id ≠ `assigned_agent_id` fails `403`.
8. `PATCH /tickets/{id}` attempting a disallowed status transition (see lifecycle) fails `409`.
9. `PATCH /tickets/{id}` on a `closed` ticket, by anyone, for any field, fails `409` — closed tickets have no admin override.
10. Successful `POST`/`PATCH` returns the full ticket object, `200`/`201`.
11. `GET /tickets` supports filtering and sorting on every column except `id` (`ticket_id`, `customer`, `priority`, `status`, `hours`, `assigned_agent_id`, timestamps).
12. `GET /tickets` pagination defaults to page size 30, accepts a `page_size` up to 100; a `page_size` above 100 fails `422` (not silently clamped, so a caller's bug is visible).

### Import
13. `POST /tickets/import` (admin-only) accepts a CSV, max size 5 MB — large enough for tens of thousands of rows, small enough to validate synchronously without a background job.
14. Each row is validated with the same rules as ticket creation; a row whose `ticket_id` already exists in the DB, or duplicates a `ticket_id` earlier in the same file, is skipped as a conflict.
15. The import response is a single JSON body, HTTP status `200`, reporting: total rows read, count inserted, count skipped, and a list of `{row_number, ticket_id, reason}` for every skipped row — never a bare pass/fail for the whole file, since partial success is the normal case.
16. An import file that fails to parse as CSV at all (bad structure, wrong headers) fails the whole request `422` before any rows are inserted.

### Summaries
17. `GET /tickets/summary` (both roles — §1 confirms both see all tickets) returns counts grouped by `status`, by `priority`, and by `customer`, computed over every ticket the caller can see. Since both roles currently see all tickets, agent and admin summaries are identical in v1; add a `?scope=mine` param later if agent-scoped summaries become a real need.

### Users
18. `POST /users` (admin-only) creates a user with username, password, role; fails `409` on duplicate username.
19. `PATCH /users/{id}` (admin-only) can change role or deactivate/reactivate a user. There is no `DELETE /users/{id}` endpoint — accounts are deactivated, never removed, so ticket history always resolves to a real (if inactive) account.
20. A deactivated user's login attempt fails `401` (same generic message as bad credentials, not "account disabled" — avoid confirming account existence/state to a caller who may not still be authorized).
21. A deactivated agent's existing tickets are **not** reassigned automatically; they remain assigned to that agent (queryable, visible in summaries) but are effectively frozen since the agent can no longer log in to edit them — an admin can still reassign or edit them (see §2 use case 7).

### Health/ops
22. `GET /health` requires no auth, returns `200` with a body confirming API liveness and DB connectivity (e.g. a trivial `SELECT 1`), and fails `503` if the DB is unreachable.

## 4. Non-functional requirements

- **Performance:** `GET /tickets` (paginated, filtered) returns in under 200ms at p95 against a 100,000-row table on local dev hardware, measured with a small `pytest` benchmark or a scripted `httpx` loop timing N requests — not a guess, an actual number captured once the schema and indexes exist. CSV import of 10,000 rows completes in under 10 seconds synchronously.
- **Reliability/error handling:** every error response uses one consistent JSON shape (`{"detail": ..., "errors": [...]}` for validation, else `{"detail": ...}`). CSV import is transactional per batch — either all validated rows for that request are committed, or none are, on an unexpected failure mid-import (a DB error, not a row-validation failure, which is expected and reported per-row per FR15). No endpoint should be able to leave the DB in a state where a ticket exists without a valid `assigned_agent_id` reference or an invalid enum value — enforced by DB constraints, not just app-level validation, since app bugs shouldn't be able to corrupt data.
- **Security (headline; full detail in `docs/security.md` later):** passwords hashed with a modern algorithm (bcrypt or argon2), never logged or returned in any response. All DB access through parameterized queries/ORM — no string-built SQL. Role checks enforced server-side on every protected endpoint, not just hidden in UI (n/a here, but stated for the record). Bearer tokens only over HTTPS in any real deployment (local dev over HTTP is acceptable and should be called out as a documented gap, not a silent one).
- **Observability:** structured (JSON) logs per request capturing timestamp, request id, method+path, caller user id and role (never password/token), status code, and latency. Import requests additionally log row counts (inserted/skipped) so an admin can audit an import after the fact without re-parsing the response body.
- **Maintainability:** layered structure mirroring `csv_extractor`'s split (routers/services/repositories or equivalent), type hints throughout, the shared validation rules kept in one module rather than duplicated between the ticket-create path and the CSV-import path (same reasoning as `csv_extractor`'s `rules.py`).

## 5. Acceptance criteria

1. **Agent cannot edit another agent's ticket (FR7).**
   *Given* agent A is authenticated and ticket 100 has `assigned_agent_id = B`,
   *when* A sends `PATCH /tickets/100` with any field change,
   *then* the response is `403` and ticket 100 is unchanged in the DB.

2. **Closed ticket cannot be reopened (FR8/FR9, locked decision).**
   *Given* ticket 100 has `status=closed`,
   *when* any agent or admin sends `PATCH /tickets/100` with `status=open` or `status=in_progress`,
   *then* the response is `409` and the ticket's status is still `closed`.

3. **CSV import skips a duplicate `ticket_id` without touching the existing row (locked decision).**
   *Given* ticket `123456789` already exists in the DB with `customer="Acme"`,
   *when* an admin imports a CSV containing a row with `ticket_id=123456789, customer="Other Co"`,
   *then* the response reports that row as skipped with reason `"duplicate ticket_id"`, no new row is inserted, and the existing ticket's `customer` is still `"Acme"`.

4. **Ticket listing pagination defaults and caps (FR12, locked decision).**
   *Given* 250 tickets exist in the DB,
   *when* a caller requests `GET /tickets` with no `page_size`,
   *then* exactly 30 tickets are returned; *and when* they request `page_size=150`, the response is `422`.

5. **Login does not distinguish bad username from bad password (FR1).**
   *Given* no account exists with username `ghost`, and account `agent1` exists with a different password than submitted,
   *when* each logs in with a wrong credential,
   *then* both requests return `401` with the same response body.

6. **Field validation rejects an out-of-range ticket on create (FR5).**
   *Given* a `POST /tickets` payload with `hours=41`,
   *when* the request is submitted,
   *then* the response is `422` and includes a field-level error naming `hours`, and no ticket is created.

## 6. Non-goals (explicit)

- Frontend UI (API only).
- Cloud deployment (local/Docker only for this project).
- Self-service password reset (admins set/change passwords directly — see §2 use case 6).
- Rate limiting / brute-force lockout on login (documented gap, not solved here).
- Real-time notifications (websockets, push, email).
- Multi-tenancy (single organization/dataset).
- Ticket comments or full change-history/audit trail (only current state is stored; "what changed and when" is not tracked in v1).
- Soft delete: there is no delete endpoint for tickets or hard-delete for users at all in v1 — users are deactivated, never removed (FR19-21); tickets are permanent once created. Revisit only if a real need shows up.
- Refresh tokens / "remember me" (re-login on token expiry, FR4).
- Bulk CSV *export* (out of scope here — that's `csv_extractor`'s job; this project is the API/DB side).
- File attachments on tickets, full-text search beyond the listed filters, i18n/l10n.
