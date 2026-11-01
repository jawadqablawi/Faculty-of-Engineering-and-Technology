# ETCS — نظام تنسيق كلية الهندسة والتكنولوجيا

Arabic-first, database-backed coordination application for Palestine Technical University – Kadoorie. Built with Django 5.2 LTS. See [architecture and permissions](docs/ARCHITECTURE.md).

## Local setup

```bash
cd /workspace/Faculty-of-Engineering-and-Technology
python3 -m venv /workspace/etcs-venv
/workspace/etcs-venv/bin/pip install -r requirements.lock.txt
export ETCS_DEBUG=1
/workspace/etcs-venv/bin/python manage.py migrate
/workspace/etcs-venv/bin/python manage.py bootstrap
/workspace/etcs-venv/bin/python manage.py bootstrap --email coordinator@example.edu
/workspace/etcs-venv/bin/python manage.py runserver 127.0.0.1:8000 --noreload
```

The bootstrap command prompts for a unique password; none is hardcoded. The five initial clubs are seeded idempotently. Invite each president from the coordinator account. Invitations verify the email when accepted. There are no preconfigured club passwords. For automated tests, accounts use isolated synthetic test data.

Deputy/reviewer/auditor access starts empty. Auditors must receive explicit activity record grants in addition to the reports module. The coordinator can assign modules on the in-app user permissions page; the initial superuser can also use the advanced administration interface. Assign modules (`requests`, `letters`, `cases`, `operations`, `reports`) and explicit club scopes at `/admin/coordination/profile/`. Do not give deputies Django staff/superuser permissions. Account activation is available in the app. President handover: disable the outgoing user, invite the replacement into the same club; history remains intact.

## Configuration and deployment

Production: unset `ETCS_DEBUG`, set a random `ETCS_SECRET_KEY`, `ETCS_ALLOWED_HOSTS`, persistent `ETCS_DB` and `ETCS_PRIVATE_MEDIA`, and configure HTTPS termination with trusted forwarded protocol headers. Never expose the Django development server publicly. Run `gunicorn config.wsgi:application --bind 127.0.0.1:8000 --workers 1` behind an HTTPS reverse proxy that strips client-supplied forwarding headers. Install OS libraries required by WeasyPrint (Pango/Harfbuzz/fonts); DejaVu Sans supplies Arabic glyphs. Gunicorn is included. Keep one worker with the current SQLite/process-local rate limiter; configure PostgreSQL and a shared cache before scaling.

Email defaults to **console output for development**. Configure `ETCS_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `ETCS_EMAIL_HOST`, `ETCS_EMAIL_PORT`, `ETCS_EMAIL_USER`, `ETCS_EMAIL_PASSWORD`, `ETCS_FROM_EMAIL` for actual delivery. Keep console invitation/reset links private: they contain bearer tokens. No outbound mail delivery has been verified without an SMTP provider.

Run `ETCS_DEBUG=1 /workspace/etcs-venv/bin/python manage.py test`. Schedule `manage.py reminders` daily using cron with the same settings/database; repeated daily runs do not duplicate reminders. The command is implemented; a scheduler must be configured in deployment.

Backups: pause uploads, run `manage.py backup /secure/new-backup-directory` (SQLite online backup plus private media), and securely retain the secret key/configuration separately. Test restoration into a separate instance with database migrations and authorized attachment downloads. Protect backups like the original data. No backup service is configured by this repository.

## Implemented scope and practical limits

Implemented: invite-based login/reset, activation, club isolation, editable drafts/autosave, four-step physical requests, independent online workshop/session forms, structured requirements and budget totals, approval history and revisions, private validated files, council/university stages, letters and Arabic PDF, calendar month/week/day and ICS export, student cases, ideas, tasks, meetings, reports and real-data Excel/PDF exports, notifications, reminder command, final reports, club management and audit records.

Program, speaker, partner, requirement and session rows are structured editors stored in validated activity JSON; optional media details use expandable text sections. The calendar does not reserve venues. Workshop publication scheduling records dates and generates in-app due reminders; it does not post to social networks. File validation checks extensions/signatures and Office ZIP structure; antivirus scanning is not configured. History preserves submitted snapshots; uploaded files are individual immutable records rather than a full version-comparison UI. Cases support search, status history, resolution/closure and coordinator-only anonymization after a one-year retention period. Reports include weekly/monthly/yearly presets, per-club totals, recorded attendance, pending/completed/online views, academic-year/semester archives and restricted case/letter/task exports. Coordinated multiworker rate limiting remains future work. PostgreSQL RLS is not enabled in the SQLite implementation. This is a runnable implementation, not a claim that every master-prompt acceptance criterion is production-complete.

## Browser validation

`/workspace/etcs-venv/bin/python scripts/browser_smoke.py` creates a temporary database with a synthetic account, starts a local server and checks the real four-step form, budget totals, saving/submission, mobile overflow and calendar views with Chromium. Requires Node.js, Playwright and Chromium (available in this cloud environment). Screenshots go to `/tmp/etcs-browser-artifacts`. It does not modify the development database.
