CREATE TABLE IF NOT EXISTS alumni (
    id UUID PRIMARY KEY,
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    graduation_year INT,
    current_company VARCHAR(255),
    current_designation VARCHAR(255),
    current_location VARCHAR(255),
    linkedin_url TEXT UNIQUE,
    last_verified_at TIMESTAMPTZ DEFAULT NOW() - INTERVAL '200 days',
    verification_status VARCHAR(50) DEFAULT 'STALE',
    raw_reply_text TEXT
);

CREATE TABLE IF NOT EXISTS linkedin_accounts (
    id SERIAL PRIMARY KEY,
    account_name VARCHAR(100),
    li_at_cookie TEXT NOT NULL,
    proxy_url TEXT,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    last_used_at TIMESTAMPTZ DEFAULT NOW()
);