CREATE TABLE IF NOT EXISTS request_logs (
    id CHAR(36) NOT NULL PRIMARY KEY,
    method VARCHAR(10) NOT NULL,
    path VARCHAR(1024) NOT NULL,
    query_string VARCHAR(4096) NOT NULL DEFAULT '',
    status_code SMALLINT UNSIGNED NOT NULL,
    duration_ms INT UNSIGNED NOT NULL DEFAULT 0,
    request_bytes INT UNSIGNED NOT NULL DEFAULT 0,
    response_bytes INT UNSIGNED NOT NULL DEFAULT 0,
    request_body LONGTEXT NULL,
    response_body LONGTEXT NULL,
    created_at DATETIME NOT NULL,
    INDEX idx_request_logs_created_at (created_at),
    INDEX idx_request_logs_status (status_code, created_at),
    INDEX idx_request_logs_method (method, created_at),
    INDEX idx_request_logs_path (path(191), created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
