-- Run after checking historical overlaps and taking a backup. Existing properties
-- remain NULL/NULL (legacy unrestricted) until their owner sets a period.
ALTER TABLE quintas
  ADD COLUMN rental_start_date DATE NULL,
  ADD COLUMN rental_end_date DATE NULL;

CREATE INDEX ix_bookings_availability
  ON bookings (quinta_id, check_in, check_out);
