-- Run this file directly against PostgreSQL (outside an explicit transaction).
-- These indexes target the most common message + notification read paths.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_messages_conversation_created
ON messages(conversation_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_team_messages_team_created
ON team_channel_messages(team_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_dm_messages_conversation_created
ON internal_dm_messages(conversation_id, created_at DESC);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_notifications_agent_read
ON notifications(agent_id, read, created_at DESC);
