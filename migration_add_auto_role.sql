-- Migration: Add auto_role_id to application_types table
-- This enables automatic Discord role assignment when applications are accepted

ALTER TABLE application_types 
ADD COLUMN auto_role_id VARCHAR(64) NULL 
AFTER discord_channel_id;

-- Optional: Add index for better query performance
CREATE INDEX idx_auto_role_id ON application_types(auto_role_id);
