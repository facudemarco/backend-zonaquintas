-- Only after a backup and explicit decision to discard configured rental periods.
DROP INDEX ix_bookings_availability ON bookings;
ALTER TABLE quintas
  DROP COLUMN rental_start_date,
  DROP COLUMN rental_end_date;
