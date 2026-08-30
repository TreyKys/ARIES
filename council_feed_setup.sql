CREATE TABLE IF NOT EXISTS council_feed (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT now(),
    agent_name TEXT,
    message TEXT,
    severity TEXT DEFAULT 'INFO'
);

BEGIN;
  ALTER PUBLICATION supabase_realtime ADD TABLE council_feed;
COMMIT;
