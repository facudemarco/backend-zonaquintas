-- ZonaQuintas Admin CRM - Verificaciones y auditoría de moderación
-- Ejecutar una vez sobre la base de datos del backend.

CREATE TABLE IF NOT EXISTS quinta_verifications (
    quinta_id CHAR(36) NOT NULL PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDIENTE',
    rejection_reason VARCHAR(500) NULL,
    admin_notes TEXT NULL,
    verified_by CHAR(36) NULL,
    verified_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_quinta_verifications_status (status),
    INDEX idx_quinta_verifications_verified_by (verified_by)
);

CREATE TABLE IF NOT EXISTS admin_moderation_events (
    id CHAR(36) NOT NULL PRIMARY KEY,
    entity_type VARCHAR(30) NOT NULL,
    entity_id CHAR(36) NOT NULL,
    action VARCHAR(50) NOT NULL,
    previous_status VARCHAR(50) NULL,
    new_status VARCHAR(50) NULL,
    reason VARCHAR(500) NULL,
    admin_id CHAR(36) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_moderation_entity (entity_type, entity_id),
    INDEX idx_moderation_admin (admin_id),
    INDEX idx_moderation_created_at (created_at)
);


CREATE TABLE IF NOT EXISTS admin_payouts (
    id CHAR(36) NOT NULL PRIMARY KEY,
    owner_id CHAR(36) NOT NULL,
    currency VARCHAR(10) NOT NULL,
    amount DECIMAL(15,2) NOT NULL DEFAULT 0,
    transaction_count INT NOT NULL DEFAULT 0,
    admin_id CHAR(36) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_admin_payouts_owner (owner_id),
    INDEX idx_admin_payouts_admin (admin_id),
    INDEX idx_admin_payouts_created_at (created_at)
);
