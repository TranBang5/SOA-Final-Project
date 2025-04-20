-- Initialize the analytics_db

-- Create database if not exists
CREATE DATABASE IF NOT EXISTS analytics_db;
USE analytics_db;

-- Grant privileges
GRANT ALL PRIVILEGES ON analytics_db.* TO 'analytics_user'@'%';
FLUSH PRIVILEGES;