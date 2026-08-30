-- 1. Create a table for high-frequency engine metrics
CREATE TABLE IF NOT EXISTS system_state (
    id INT PRIMARY KEY DEFAULT 1,
    balance NUMERIC,
    today_pnl_abs NUMERIC,
    today_pnl_pct NUMERIC,
    win_rate NUMERIC,
    is_connected BOOLEAN DEFAULT false,
    last_heartbeat TIMESTAMP WITH TIME ZONE DEFAULT now()
);

-- Insert the default row
INSERT INTO system_state (id, balance, today_pnl_abs, today_pnl_pct, win_rate, is_connected)
VALUES (1, 50.00, 0, 0, 0, false)
ON CONFLICT (id) DO NOTHING;

-- 2. Turn on Supabase Realtime for these tables
BEGIN;
  -- Remove them first to avoid errors if they are already in the publication
  ALTER PUBLICATION supabase_realtime DROP TABLE IF EXISTS system_state;
  ALTER PUBLICATION supabase_realtime DROP TABLE IF EXISTS signals;
  
  -- Add them to the realtime publication
  ALTER PUBLICATION supabase_realtime ADD TABLE system_state;
  ALTER PUBLICATION supabase_realtime ADD TABLE signals;
COMMIT;
