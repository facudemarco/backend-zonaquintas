-- Run against a backup/test copy first. This file is read-only.
SELECT COUNT(*) AS review_count FROM reviews;
SELECT booking_id, COUNT(*) AS total FROM reviews GROUP BY booking_id HAVING COUNT(*) > 1;
SELECT COUNT(*) AS orphan_reviews FROM reviews r LEFT JOIN bookings b ON b.id = r.booking_id WHERE b.id IS NULL;
SELECT COUNT(*) AS invalid_stars FROM reviews WHERE stars IS NULL OR stars NOT BETWEEN 1 AND 5;
SELECT COUNT(*) AS invalid_participants FROM reviews r JOIN bookings b ON b.id = r.booking_id WHERE b.guest_id = b.owner_id;
SELECT COUNT(*) AS overlong_comments FROM reviews WHERE CHAR_LENGTH(review_text) > 2000;
SELECT COUNT(*) AS legacy_opinions FROM users_opinions;
SELECT TABLE_NAME, ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME IN ('reviews', 'bookings', 'users');
SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND (TABLE_NAME, COLUMN_NAME) IN
  (('reviews','id'), ('reviews','booking_id'), ('bookings','id'), ('bookings','guest_id'),
   ('bookings','owner_id'), ('users','id'), ('users','average_opinions'));
SELECT CONSTRAINT_NAME, TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
FROM information_schema.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reviews';
SELECT b.status, COUNT(*) AS count FROM bookings b JOIN reviews r ON r.booking_id = b.id GROUP BY b.status;
