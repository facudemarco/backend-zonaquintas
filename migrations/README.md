# Rental-period migration

Run `000_availability_preflight.sql` and inspect engine, status inventory, and
historical overlaps before changing the target database. Then run
`001_rental_period.up.sql` on a backed-up MySQL test database first, then
production during a planned deployment. Confirm both tables use InnoDB so the
per-quinta `FOR UPDATE` lock serializes booking creation. Inspect historical
overlaps before setting periods; NULL/NULL keeps existing properties bookable
under their prior unrestricted policy, while still preventing new overlaps.
Configure each legacy property's range with the authenticated update endpoint.
The `down` script removes only the new index and columns, never bookings or payments.

## Reviews

`003_drop_legacy_users_opinions.sql` removes the unused legacy free-text opinions table and its two historical rows. It is destructive and has no down migration; apply it only after deciding those texts do not need archival retention.

`002_reviews_preflight.sql` is read-only. Check its results immediately before migration, make a backup, and run `002_reviews.up.sql` on an isolated MariaDB copy first. The local backend `.env` currently points to production: never run test imports or migrations with it. This migration expands `reviews` for two evaluations per booking, adds delayed revelation and moderation, and creates report/reminder tables. Deploy the corresponding backend before accepting new reviews. There is intentionally no destructive down script: rolling back code after new reviews have been stored requires a forward compatibility fix that preserves both directions and the moderation audit.

After deploying both applications, set `REVIEW_LAUNCH_DATE` to the rollout date (YYYY-MM-DD) so older bookings receive no reminder. Configure a shared `REVIEW_INTERNAL_TOKEN` in both applications, `REVIEW_MAILER_URL` as the frontend internal reminder route, and the frontend's `REVIEW_BACKEND_URL` and `REVIEW_PUBLIC_URL`. The frontend needs its usual Resend credentials. Run `python -m services.review_reminders` first to count eligible jobs without writing or emailing. Schedule `python -m services.review_reminders --send` hourly only after setting `REVIEW_REMINDERS_ENABLED=1`. The worker sends at or after 10:00 Argentina time on D+1 and again seven days after the first delivered reminder if still eligible. It also refreshes visible host averages after blind-review deadlines. Do not enable the worker before the migration and frontend mail endpoint are deployed.
