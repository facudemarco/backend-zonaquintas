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
