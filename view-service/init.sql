CREATE DATABASE IF NOT EXISTS view_db;
USE view_db;

-- Drop the old pastes table if it exists (to reset)
DROP TABLE IF EXISTS paste;

CREATE TABLE IF NOT EXISTS paste (
    paste_id INT NOT NULL PRIMARY KEY,  -- Make paste_id the primary key
    short_url VARCHAR(10) NOT NULL,
    content TEXT NOT NULL,
    expires_at DATETIME,
    view_count INT DEFAULT 0,
    INDEX idx_short_url (short_url)
);

-- Drop the old views table if it exists (to reset)
DROP TABLE IF EXISTS views;

CREATE TABLE IF NOT EXISTS views (
    id INT AUTO_INCREMENT PRIMARY KEY,
    paste_id INT NOT NULL,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_paste_id (paste_id),
    FOREIGN KEY (paste_id) REFERENCES pastes(paste_id)
);

