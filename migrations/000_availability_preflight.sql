-- Run read-only on the target environment before 001_rental_period.up.sql.
SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('quintas', 'bookings');

SELECT status, COUNT(*) AS total FROM bookings GROUP BY status ORDER BY total DESC;

SELECT a.quinta_id, a.id AS first_booking, b.id AS second_booking
FROM bookings a JOIN bookings b
  ON a.quinta_id = b.quinta_id AND a.id < b.id
 AND a.check_in < b.check_out AND a.check_out > b.check_in
WHERE (a.status IS NULL OR LOWER(a.status) NOT IN ('rejected', 'cancelled', 'rechazado', 'cancelado'))
  AND (b.status IS NULL OR LOWER(b.status) NOT IN ('rejected', 'cancelled', 'rechazado', 'cancelado'))
LIMIT 100;
