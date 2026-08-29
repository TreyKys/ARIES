import React from 'react';

export default function TradeJournal({ trades }) {
  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-xl font-bold border-b border-border pb-2">Execution Journal</h2>
      
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-fg-muted">
            <tr>
              <th className="p-3 font-bold">Date</th>
              <th className="p-3 font-bold">Pair</th>
              <th className="p-3 font-bold">Side</th>
              <th className="p-3 font-bold">Entry</th>
              <th className="p-3 font-bold">Exit</th>
              <th className="p-3 font-bold">P&L ($)</th>
              <th className="p-3 font-bold">R-Multiple</th>
              <th className="p-3 font-bold">Strategy</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan="8" className="p-8 text-center text-fg-muted font-mono">Awaiting first execution...</td>
              </tr>
            ) : (
              trades.map((t, i) => (
                <tr key={i} className="border-t border-border hover:bg-muted/50 transition-colors">
                  <td className="p-3 font-mono text-xs">{new Date(t.opened_at).toLocaleDateString()}</td>
                  <td className="p-3 font-bold">{t.symbol}</td>
                  <td className="p-3"><span className={`badge ${t.side === 'LONG' ? 'badge-green' : 'badge-red'}`}>{t.side}</span></td>
                  <td className="p-3 font-mono">{t.entry_price}</td>
                  <td className="p-3 font-mono">{t.exit_price || 'OPEN'}</td>
                  <td className={`p-3 font-mono font-bold ${t.pnl_usd > 0 ? 'text-green' : (t.pnl_usd < 0 ? 'text-red' : '')}`}>
                    {t.pnl_usd ? (t.pnl_usd > 0 ? `+$${t.pnl_usd}` : `-$${Math.abs(t.pnl_usd)}`) : '--'}
                  </td>
                  <td className="p-3 font-mono">{t.r_multiple ? `${t.r_multiple}R` : '--'}</td>
                  <td className="p-3 text-xs text-fg-muted">{t.strategy}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
