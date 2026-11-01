# ETCS architecture and permissions

Django 5.2 LTS, server-rendered Arabic RTL UI, SQLite relational database for single-instance operation, private filesystem storage. Django ORM migrations enforce foreign keys. UUID primary keys and unique human-readable tracking IDs prevent collisions. PostgreSQL RLS is not implemented: authorization is enforced on every application query. Multi-instance PostgreSQL deployment requires a separate tested database configuration.

## Navigation
Club: physical request, online request, own requests, calendar. Coordinator: requests, activities/calendar, letters linked to requests, student affairs, clubs. Secondary navigation exposes tasks, meetings, ideas, reports, accounts.

## Matrix
| Role | Requests/files | Approvals | Cases | Operations | Reports | Accounts |
|---|---|---|---|---|---|---|
| Coordinator | All | All recorded stages | All | All | All | Invite/deactivate/delegate |
| Deputy | Explicit club scope + requests module | Same scope + requests module | cases module, assigned only | operations module, assigned tasks only; meetings coordinator only | reports module, explicit club scope | None |
| Club | Own active membership only | Submit/withdraw only | None | Own ideas | Own request history | None |
| Reviewer | Explicit clubs, requests module, read only | None | None | None | None | None |
| Auditor | Explicit activity record grants, reports module, read only | None | None | None | Authorized reports | None |

There is no implicit all-club access for an empty deputy scope. Partner mentions confer no permissions. Calendar exposes only approved title, club, kind, date and times across clubs. Files are never served via public media routes. Disabled users lose authenticated access immediately.

## Data model
Club → Profile (current membership) → Activity (physical/online) → History snapshots, Attachment, Letter, Report. Other entities: Idea, Case, Meeting, Task, Notification, Audit, Invitation, Setting. Structured dynamic requirements and online sessions are stored as validated JSON within the activity; other optional detail sections are text. Every activity foreign key preserves ownership, with protected deletion. Historical records survive president replacement.

## Workflow
Draft/changes → review → preliminary → council → approvals → approved → completed. Forwarding requires a letter and evidence reference. Council and university acceptance each require a recorded reference. Completion requires a final report. Changes/rejection require reasons. Every transition is atomic, recorded with actor/time/snapshot and notifies relevant users. Approval evidence references are operator attestations, not verification by the university.

## Authentication
Django password hashing/validation, CSRF, expiring HttpOnly sessions, invite-only accounts, one-time expiring invitation links that verify possession of the email, Django password-reset tokens. No public registration. Initial coordinator uses a local interactive command. Production must use HTTPS and a real SMTP provider. Login rate limiting uses Django's process-local cache; use a shared rate-limit/cache service before multiworker production.
