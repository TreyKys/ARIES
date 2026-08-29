import React from 'react';

export default function MTFAnalysis({ data }) {
  const badgeColor = (status) => {
    if (status === 'BULLISH' || status === 'UP') return 'badge-green';
    if (status === 'BEARISH' || status === 'DOWN') return 'badge-red';
    return 'badge-blue';
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-bold border-b border-border pb-2">Multi-Timeframe Analysis</h2>
      
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">Macro (4H / 1D)</h3>
          <div className="flex justify-between items-center mb-3">
            <span>Market Bias</span>
            <span className={`badge ${badgeColor(data?.macro_bias)}`}>{data?.macro_bias || 'NEUTRAL'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>Trend State</span>
            <span className={`badge ${badgeColor(data?.macro_trend)}`}>{data?.macro_trend || 'RANGING'}</span>
          </div>
        </div>

        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">Structure (1H / 15m)</h3>
          <div className="flex justify-between items-center mb-3">
            <span>1H Structure</span>
            <span className={`badge ${badgeColor(data?.structure_1h)}`}>{data?.structure_1h || 'NEUTRAL'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>15m Structure</span>
            <span className={`badge ${badgeColor(data?.structure_15m)}`}>{data?.structure_15m || 'NEUTRAL'}</span>
          </div>
        </div>

        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">Execution (5m / 1m)</h3>
          <div className="flex justify-between items-center mb-3">
            <span>5m Momentum</span>
            <span className={`badge ${badgeColor(data?.execution_5m)}`}>{data?.execution_5m || 'NEUTRAL'}</span>
          </div>
          <div className="flex justify-between items-center">
            <span>1m Order Flow</span>
            <span className={`badge ${badgeColor(data?.execution_1m)}`}>{data?.execution_1m || 'NEUTRAL'}</span>
          </div>
        </div>
      </div>

      <div className="card p-6 flex flex-col items-center justify-center py-12 mt-4">
        <div className="text-sm text-fg-muted mb-2 uppercase tracking-widest font-bold">Structural Confluence Score</div>
        <div className="text-6xl font-mono font-bold text-primary">{data?.confluence_score || 0}%</div>
        <div className="mt-4 text-xs text-fg-muted max-w-md text-center">
          The Council requires a minimum 80% confluence score across all 3 structural dimensions before authorizing a trade on the execution timeframe.
        </div>
      </div>
    </div>
  );
}
