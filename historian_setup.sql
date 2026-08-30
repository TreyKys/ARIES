-- Create the vector similarity matching function for The Historian
CREATE OR REPLACE FUNCTION match_trades(
  query_embedding vector(10),
  match_threshold float,
  match_count int
)
RETURNS TABLE (
  id UUID,
  symbol TEXT,
  pnl_usd NUMERIC,
  similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    trades.id,
    trades.symbol,
    trades.pnl_usd,
    1 - (trades.setup_vector <=> query_embedding) AS similarity
  FROM trades
  WHERE trades.setup_vector IS NOT NULL
    AND 1 - (trades.setup_vector <=> query_embedding) > match_threshold
  ORDER BY trades.setup_vector <=> query_embedding
  LIMIT match_count;
END;
$$;
