CREATE TABLE IF NOT EXISTS mtf_analysis (
    id INT PRIMARY KEY DEFAULT 1,
    macro_bias TEXT,
    macro_trend TEXT,
    structure_1h TEXT,
    structure_15m TEXT,
    execution_5m TEXT,
    execution_1m TEXT,
    confluence_score NUMERIC,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);

INSERT INTO mtf_analysis (id, macro_bias, macro_trend, structure_1h, structure_15m, execution_5m, execution_1m, confluence_score)
VALUES (1, 'NEUTRAL', 'RANGING', 'NEUTRAL', 'NEUTRAL', 'NEUTRAL', 'NEUTRAL', 0)
ON CONFLICT (id) DO NOTHING;

BEGIN;
  ALTER PUBLICATION supabase_realtime ADD TABLE mtf_analysis;
COMMIT;

-- Ensure trades table exists and is published
CREATE TABLE IF NOT EXISTS trades (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    entry_price NUMERIC NOT NULL,
    exit_price NUMERIC,
    pnl_usd NUMERIC,
    r_multiple NUMERIC,
    strategy TEXT,
    status TEXT DEFAULT 'CLOSED',
    opened_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL,
    closed_at TIMESTAMP WITH TIME ZONE
);

BEGIN;
  ALTER PUBLICATION supabase_realtime ADD TABLE trades;
COMMIT;
