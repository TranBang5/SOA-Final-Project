CREATE TABLE IF NOT EXISTS analytics (
    id SERIAL PRIMARY KEY,
    paste_id INTEGER NOT NULL,
    view_count INTEGER DEFAULT 0,
    unique_visitors INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS visitor_logs (
    id SERIAL PRIMARY KEY,
    paste_id INTEGER NOT NULL,
    visitor_ip VARCHAR(45),
    user_agent TEXT,
    viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_analytics_paste_id ON analytics(paste_id);
CREATE INDEX IF NOT EXISTS idx_visitor_logs_paste_id ON visitor_logs(paste_id); 