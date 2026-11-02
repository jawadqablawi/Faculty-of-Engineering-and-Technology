# Architecture and permissions

Django 5.2 LTS renders Arabic RTL HTML. Relational tables persist users/profiles, clubs, activities, physical dates, workshop sessions, attachments and immutable versions, approval requirements, snapshots, comments, letters/history, cases/documents, plans, meetings/participants, tasks, reports, notifications, email queue, audit records, counters and settings. Optional descriptive program/speaker/partner/requirements rows are validated formsets stored as structured activity JSON; primary dates/sessions and operational entities have relational constraints.

## Authorization matrix

| Role | Requests/files | Approvals | Cases | Operations | Reports | Accounts |
|---|---|---|---|---|---|---|
| Coordinator | All | All recorded stages | All | All | All | Invite/deactivate/delegate |
| Deputy | Explicit club scope and module | requests module and scope | cases module, assigned only | operations module; assigned tasks and scoped meetings | reports module, explicit scope | None |
| Club | Own active membership only | Submit/withdraw | None | Own ideas/plans/meetings and assigned tasks | Own request history | None |
| Reviewer | Explicit clubs, requests module, read only | None | None | None | None | None |
| Auditor | Explicit activity grants, reports module, read only | None | None | None | Granted records only | None |

Server queries derive club ownership from the authenticated membership, never a submitted arbitrary club ID. All UUID URL/file lookups are scoped. A partner mention grants no access. Calendar projections expose only approved titles, dates, times, kind and club, without budgets, private notes, links or documents. Account/club deactivation is checked on every request.

## PostgreSQL RLS

SQLite development uses the same server-side authorization but has no RLS. PostgreSQL migrations enable and FORCE RLS on private activity/child rows, cases/documents, letters/history, plans, ideas, meetings, tasks, notifications, email queue and audit records. The web login must be a non-superuser without BYPASSRLS and cannot own tables. Middleware rejects bypass roles, wraps the request in a transaction and sets `etcs.user_id` transaction-locally, preventing pool identity leakage. Without identity, private activity reads return no rows.

SECURITY DEFINER helper functions have a fixed search path and trusted migration owner. A narrow security-barrier calendar view projects only approved public-safe fields; the conflict function returns a boolean. The maintenance credential is used for migrations, backup and trusted scheduled jobs, never by HTTP workers. RLS supplements trusted application authorization and parameterized queries; web credentials and request context must remain server-side. It is not a defense against a fully compromised trusted application server. `grant_web_role` revokes update/delete on audit, approval snapshots and correspondence history. No ordinary application endpoint modifies or deletes audit history.

## Workflow and evidence

Draft/changes → review → preliminary → council → approvals → approved → completed. The system uses atomic transitions, a locked annual sequence for identifiers, immutable submitted snapshots (including file checksums/versions), reasons and actor/time. Forwarding requires a letter and recorded reference. Council/university decisions are separate. Required additional approvals must all be accepted before final approval; a failure rolls back the whole transition. Completion requires a final report without outstanding corrections. Letters preserve successive bodies, status, dates and evidence. Recorded references are authorized operator attestations, not university verification or electronic signatures.

## Authentication and documents

Django password validation/hashing, invitation-only creation, expiring one-time email links, password reset, HttpOnly expiring sessions, CSRF and persistent database rate limits. Production requires a strong secret and explicit allowed hosts; HTTPS cookies and redirect are enabled. Caddy owns public ports and sanitizes protocol headers; web/database have no public host ports.

Private files have random storage names, size/type/signature checks and Office archive limits. Authorized endpoints stream files; no media root is published. Each replacement links to a prior immutable file, with version and SHA-256 checksum. Draft deletion is a soft deletion; physical case documents are removed during approved retention anonymization. Optional email delivery is queued and retried without rolling back activity changes; console output is never recorded as actual notification delivery.

## Operations

Gunicorn runs multiple workers. Login/reset limits are in the database rather than process memory. Reminder keys deduplicate each recipient/item/day; queues skip inactive recipients. Private media and PostgreSQL are persistent volumes. The backup command uses SQLite online backup or pg_dump plus media copying; pause writes/uploads for cross-resource consistency. Production deployment requires tested recovery, a real SMTP provider and correct domain DNS/HTTPS; these external services are not provisioned by repository files.
