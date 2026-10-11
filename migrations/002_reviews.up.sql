-- MariaDB 11.8. Apply explicitly after 002_reviews_preflight.sql on a backup/test copy.
-- Keep the old API stopped between this migration and deploying the new review API.
ALTER TABLE reviews
    MODIFY review_text VARCHAR(2000) NULL,
    ADD COLUMN author_id CHAR(36) NULL,
    ADD COLUMN recipient_id CHAR(36) NULL,
    ADD COLUMN direction VARCHAR(20) NULL,
    ADD COLUMN reveal_at DATETIME NULL,
    ADD COLUMN moderation_status VARCHAR(16) NOT NULL DEFAULT 'visible';

-- Existing reviews came only from the guest review endpoint. Preserve their visibility.
UPDATE reviews r JOIN bookings b ON b.id = r.booking_id
SET r.author_id = b.guest_id,
    r.recipient_id = b.owner_id,
    r.direction = 'guest_to_owner',
    r.reveal_at = COALESCE(r.created_at, UTC_TIMESTAMP()),
    r.created_at = COALESCE(r.created_at, UTC_TIMESTAMP());

ALTER TABLE reviews
    MODIFY stars INT NOT NULL,
    MODIFY created_at DATETIME NOT NULL,
    MODIFY author_id CHAR(36) NOT NULL,
    MODIFY recipient_id CHAR(36) NOT NULL,
    MODIFY direction VARCHAR(20) NOT NULL,
    MODIFY reveal_at DATETIME NOT NULL,
    ADD CONSTRAINT fk_reviews_author FOREIGN KEY (author_id) REFERENCES users(id),
    ADD CONSTRAINT fk_reviews_recipient FOREIGN KEY (recipient_id) REFERENCES users(id),
    ADD CONSTRAINT uq_reviews_booking_author UNIQUE (booking_id, author_id),
    ADD CONSTRAINT ck_reviews_stars CHECK (stars BETWEEN 1 AND 5),
    ADD CONSTRAINT ck_reviews_direction CHECK (direction IN ('guest_to_owner', 'owner_to_guest')),
    ADD CONSTRAINT ck_reviews_participants CHECK (author_id <> recipient_id),
    ADD CONSTRAINT ck_reviews_moderation CHECK (moderation_status IN ('visible', 'hidden')),
    ADD INDEX ix_reviews_recipient_visibility (recipient_id, direction, moderation_status, reveal_at),
    ADD INDEX ix_reviews_reveal (reveal_at, moderation_status);

CREATE TABLE review_reports (
    id CHAR(36) PRIMARY KEY,
    review_id CHAR(36) NOT NULL,
    reporter_id CHAR(36) NOT NULL,
    reason VARCHAR(32) NOT NULL,
    detail VARCHAR(1000) NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'open',
    created_at DATETIME NOT NULL,
    resolved_at DATETIME NULL,
    CONSTRAINT fk_review_reports_review FOREIGN KEY (review_id) REFERENCES reviews(id),
    CONSTRAINT fk_review_reports_reporter FOREIGN KEY (reporter_id) REFERENCES users(id),
    CONSTRAINT uq_review_reports_reporter UNIQUE (review_id, reporter_id),
    CONSTRAINT ck_review_reports_status CHECK (status IN ('open', 'resolved', 'dismissed')),
    INDEX ix_review_reports_status (status, created_at)
) ENGINE=InnoDB;

CREATE TABLE review_moderation_events (
    id CHAR(36) PRIMARY KEY,
    review_id CHAR(36) NOT NULL,
    admin_id CHAR(36) NOT NULL,
    action VARCHAR(16) NOT NULL,
    old_status VARCHAR(16) NOT NULL,
    new_status VARCHAR(16) NOT NULL,
    reason VARCHAR(1000) NOT NULL,
    created_at DATETIME NOT NULL,
    CONSTRAINT fk_review_events_review FOREIGN KEY (review_id) REFERENCES reviews(id),
    CONSTRAINT fk_review_events_admin FOREIGN KEY (admin_id) REFERENCES users(id),
    CONSTRAINT ck_review_events_action CHECK (action IN ('hide', 'restore')),
    INDEX ix_review_events_review (review_id, created_at)
) ENGINE=InnoDB;

ALTER TABLE users ADD COLUMN review_reminders_enabled BOOLEAN NOT NULL DEFAULT TRUE;

CREATE TABLE review_reminders (
    id CHAR(36) PRIMARY KEY,
    booking_id CHAR(36) NOT NULL,
    user_id CHAR(36) NOT NULL,
    stage TINYINT NOT NULL,
    scheduled_at DATETIME NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',
    attempts INT NOT NULL DEFAULT 0,
    lease_until DATETIME NULL,
    sent_at DATETIME NULL,
    provider_message_id VARCHAR(255) NULL,
    last_error VARCHAR(255) NULL,
    CONSTRAINT fk_review_reminders_booking FOREIGN KEY (booking_id) REFERENCES bookings(id),
    CONSTRAINT fk_review_reminders_user FOREIGN KEY (user_id) REFERENCES users(id),
    CONSTRAINT uq_review_reminders_stage UNIQUE (booking_id, user_id, stage),
    CONSTRAINT ck_review_reminders_stage CHECK (stage IN (1, 2)),
    CONSTRAINT ck_review_reminders_status CHECK (status IN ('pending', 'leased', 'sent', 'cancelled', 'failed')),
    INDEX ix_review_reminders_claim (status, scheduled_at, lease_until)
) ENGINE=InnoDB;

-- Recalculate host averages from visible, verified reviews; old users_opinions rows
-- have neither stars nor booking references and are intentionally excluded.
UPDATE users u LEFT JOIN (
    SELECT recipient_id, AVG(stars) AS average_stars
    FROM reviews
    WHERE direction = 'guest_to_owner' AND moderation_status = 'visible' AND reveal_at <= UTC_TIMESTAMP()
    GROUP BY recipient_id
) a ON a.recipient_id = u.id
SET u.average_opinions = a.average_stars;
