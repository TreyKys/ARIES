import React from 'react';

export default function TradeSignals({ signals }) {

  const mockSignals = [
    { created_at: new Date().toISOString(), symbol: 'BTC/USDT', action: 'LONG', confidence: 88, risk_tier: 'T1' },
    { created_at: new Date(Date.now() - 3600000).toISOString(), symbol: 'SOL/USDT', action: 'SHORT', confidence: 75, risk_tier: 'T2' },
    { created_at: new Date(Date.now() - 7200000).toISOString(), symbol: 'ETH/USDT', action: 'LONG', confidence: 82, risk_tier: 'T1' }
  ];
  const displaySignals = signals.length > 0 ? signals : mockSignals;
  
  return (

    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-bold border-b border-border pb-2">Signal Intelligence Log</h2>
      
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-fg-muted">
            <tr>
              <th className="p-3 font-bold">Time (UTC)</th>
              <th className="p-3 font-bold">Symbol</th>
              <th className="p-3 font-bold">Action</th>
              <th className="p-3 font-bold">Confidence</th>
              <th className="p-3 font-bold">Risk Tier</th>
            </tr>
          </thead>
          <tbody>
            {displaySignals.length === 0 ? (
              <tr>
                <td colSpan="5" className="p-8 text-center text-fg-muted font-mono">No signals intercepted yet. Council is analyzing...</td>
              </tr>
            ) : (
              displaySignals.map((sig, i) => (
                <tr key={i} className="border-t border-border hover:bg-muted/50 transition-colors">
                  <td className="p-3 font-mono text-xs">{new Date(sig.created_at).toLocaleTimeString()}</td>
                  <td className="p-3 font-bold">{sig.symbol}</td>
                  <td className="p-3">
                    <span className={`badge ${sig.action === 'LONG' ? 'badge-green' : 'badge-red'}`}>
                      {sig.action}
                    </span>
                  </td>
                  <td className="p-3 font-mono">{sig.confidence}%</td>
                  <td className="p-3">{sig.risk_tier}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
