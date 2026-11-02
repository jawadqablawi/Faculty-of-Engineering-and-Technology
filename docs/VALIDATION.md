# Validation evidence — 2026-11-02

- 36 automated Django tests passed on SQLite.
- The same 36 tests passed against PostgreSQL inside the production Docker image.
- A separate fresh-database PostgreSQL test used a non-superuser web role with RLS enabled: unfiltered cross-club reads were denied, anonymous reads returned no private activities, transaction identity did not leak, file access was denied across clubs, invitations were accepted once, and submission/council/university approval completed. The test also ran with the optional email queue enabled and verified the web role cannot delete audit history.
- Chromium exercised the four-step physical form, cost calculation, real draft persistence, request submission, desktop RTL layout, mobile overflow checks at 390px, and week/day calendar switching without JavaScript errors.
- The Docker image built successfully. PostgreSQL/migrations, two-worker Gunicorn and the reminder service started through Compose. HTTP readiness and Arabic login/CSRF checks passed. The runtime is non-root and Arabic PDF generation succeeded inside the image.
- The production backup command generated a PostgreSQL custom-format archive; pg_restore read its catalog successfully. Earlier SQLite backup passed its integrity check with all five clubs present.
- Migration drift checks, Python error checks and JavaScript syntax checks passed. Secret-setting generation was tested for 0600 permissions and refusal to overwrite an existing file.

These are local results, not evidence of public deployment, a domain certificate, actual SMTP delivery, external backup storage, or a GitHub Actions run. Production setup must verify those services on the chosen host. Test records use synthetic names and addresses only. Club accounts in the real installation are created by invitation after the owner creates the initial coordinator.
