-- Migration: Add playtime tracking and Discord ID locking
-- Run this on your existing database to add the new features

-- Add discord_id_locked column to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS discord_id_locked BOOLEAN DEFAULT FALSE;

-- Add fivem_license column to users
ALTER TABLE users ADD COLUMN IF NOT EXISTS fivem_license VARCHAR(128);

-- Create playtime_sessions table
CREATE TABLE IF NOT EXISTS playtime_sessions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    discord_id VARCHAR(64),
    fivem_license VARCHAR(128),
    connect_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    disconnect_time DATETIME DEFAULT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX idx_user_id (user_id),
    INDEX idx_discord_id (discord_id),
    INDEX idx_disconnect_time (disconnect_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Add index on users.discord_id if not exists
-- (MySQL doesn't have IF NOT EXISTS for indexes, so wrap in a procedure)
DROP PROCEDURE IF EXISTS add_discord_index;
DELIMITER //
CREATE PROCEDURE add_discord_index()
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.statistics 
        WHERE table_schema = DATABASE() 
        AND table_name = 'users' 
        AND index_name = 'idx_users_discord_id'
    ) THEN
        CREATE INDEX idx_users_discord_id ON users(discord_id);
    END IF;
END //
DELIMITER ;
CALL add_discord_index();
DROP PROCEDURE IF EXISTS add_discord_index;
