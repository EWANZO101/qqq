-- =====================================================
-- CFRP Migration: Discord ID Lock + FiveM Playtime
-- Run this on your MySQL database
-- =====================================================

-- 1. Add discord_id_locked column to users table
ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_id_locked BOOLEAN DEFAULT FALSE;

-- 2. Create the FiveM playtime tracking table
-- (This table is used by the cfrp_playtime FiveM resource)
CREATE TABLE IF NOT EXISTS cfrp_playtime (
    id INT AUTO_INCREMENT PRIMARY KEY,
    discord_id VARCHAR(64) NOT NULL,
    session_start DATETIME NOT NULL,
    session_end DATETIME DEFAULT NULL,
    minutes INT DEFAULT 0,
    date DATE NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_discord_id (discord_id),
    INDEX idx_date (date),
    INDEX idx_discord_date (discord_id, date)
);
