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
    account_name VARCHAR(100) UNIQUE,
    li_at_cookie TEXT NOT NULL,
    proxy_url TEXT,
    status VARCHAR(20) DEFAULT 'ACTIVE',
    last_used_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS outreach_log (
    id SERIAL PRIMARY KEY,
    alumni_id UUID NOT NULL REFERENCES alumni(id) ON DELETE CASCADE,
    linkedin_account_id INT NOT NULL REFERENCES linkedin_accounts(id),
    profile_url TEXT NOT NULL,
    message_text TEXT,
    status VARCHAR(50) DEFAULT 'SENT',
    sent_at TIMESTAMPTZ DEFAULT NOW(),
    reply_received_at TIMESTAMPTZ
);

-- Performance indexes
CREATE INDEX IF NOT EXISTS idx_alumni_verification_status ON alumni(verification_status);
CREATE INDEX IF NOT EXISTS idx_alumni_last_verified ON alumni(last_verified_at);
CREATE INDEX IF NOT EXISTS idx_alumni_linkedin_url ON alumni(linkedin_url);
CREATE INDEX IF NOT EXISTS idx_outreach_profile_url ON outreach_log(profile_url);
CREATE INDEX IF NOT EXISTS idx_outreach_alumni_id ON outreach_log(alumni_id);
CREATE INDEX IF NOT EXISTS idx_linkedin_accounts_status ON linkedin_accounts(status);
