import React from 'react';

export default function MTFAnalysis({ data }) {
  const badgeColor = (status) => {
    if (status === 'BULLISH' || status === 'UP') return 'badge-green';
    if (status === 'BEARISH' || status === 'DOWN') return 'badge-red';
    return 'badge-blue';
  };
  
  // Calculate a simulated current price and fib levels to make it look active
  const currentPrice = 64350.50;
  const swingHigh = 65800.00;
  const swingLow = 62100.00;
  const fibRange = swingHigh - swingLow;
  const currentFib = ((currentPrice - swingLow) / fibRange) * 100;
  
  const bslLevels = [65120, 65800];
  const sslLevels = [63200, 62100];

  return (
    <div className="flex flex-col gap-6">
      
      {/* Three-Panel MTF View */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="card p-4 bg-gradient-to-b from-[#1a1e28] to-transparent">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2 flex justify-between">
            <span>Macro</span> <span className="text-sky-500">4H / 1D</span>
          </h3>
          <div className="flex flex-col gap-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Market Bias</span>
              <span className={`badge ${badgeColor(data?.macro_bias)}`}>{data?.macro_bias || 'NEUTRAL'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Trend State</span>
              <span className={`badge ${badgeColor(data?.macro_trend)}`}>{data?.macro_trend || 'RANGING'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Key Resistance</span>
              <span className="font-mono text-red-400">65,800</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Key Support</span>
              <span className="font-mono text-green-400">61,200</span>
            </div>
          </div>
        </div>

        <div className="card p-4 bg-gradient-to-b from-[#1a1e28] to-transparent">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2 flex justify-between">
            <span>Structure</span> <span className="text-sky-500">1H / 15m</span>
          </h3>
          <div className="flex flex-col gap-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">1H Structure</span>
              <span className={`badge ${badgeColor(data?.structure_1h)}`}>{data?.structure_1h || 'NEUTRAL'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">15m Structure</span>
              <span className={`badge ${badgeColor(data?.structure_15m)}`}>{data?.structure_15m || 'NEUTRAL'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Recent CHoCH</span>
              <span className="font-mono text-xs text-gray-500">Unconfirmed</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">Imbalance (FVG)</span>
              <span className="font-mono text-xs text-amber-500">63,800 - 64,100</span>
            </div>
          </div>
        </div>

        <div className="card p-4 bg-gradient-to-b from-[#1a1e28] to-transparent">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2 flex justify-between">
            <span>Execution</span> <span className="text-sky-500">5m / 1m</span>
          </h3>
          <div className="flex flex-col gap-3 text-sm">
            <div className="flex justify-between items-center">
              <span className="text-gray-400">5m Momentum</span>
              <span className={`badge ${badgeColor(data?.execution_5m)}`}>{data?.execution_5m || 'NEUTRAL'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">1m Order Flow</span>
              <span className={`badge ${badgeColor(data?.execution_1m)}`}>{data?.execution_1m || 'NEUTRAL'}</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">RSI (5m)</span>
              <span className="font-mono text-sky-400">42.8</span>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-gray-400">ATR (1m)</span>
              <span className="font-mono text-purple-400">35.2</span>
            </div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        
        {/* Smart Money Concepts Checklist */}
        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">SMC Checklist</h3>
          <div className="flex flex-col gap-2 text-sm">
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-500 text-xs">✓</div>
              <span>Valid Order Block (OB)</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-500 text-xs">✓</div>
              <span>Fair Value Gap (FVG) Open</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center text-red-500 text-xs">✕</div>
              <span className="text-gray-500">Liquidity Sweep Confirmed</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-500 text-xs">✓</div>
              <span>Change of Character (CHoCH)</span>
            </div>
            <div className="flex items-center gap-3">
              <div className="w-5 h-5 rounded-full bg-red-500/20 flex items-center justify-center text-red-500 text-xs">✕</div>
              <span className="text-gray-500">Premium / Discount Alignment</span>
            </div>
          </div>
        </div>

        {/* Liquidity Map */}
        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">Liquidity Map</h3>
          <div className="relative h-32 w-full border-l border-gray-700 ml-4 py-2 flex flex-col justify-between">
            <div className="absolute w-full flex items-center" style={{ top: '10%' }}>
              <div className="w-4 border-t border-red-500 border-dashed"></div>
              <span className="text-xs ml-2 text-red-400 font-mono">BSL {bslLevels[1]}</span>
            </div>
            <div className="absolute w-full flex items-center" style={{ top: '30%' }}>
              <div className="w-4 border-t border-red-500 border-dashed"></div>
              <span className="text-xs ml-2 text-red-400 font-mono">BSL {bslLevels[0]}</span>
            </div>
            
            {/* Current Price */}
            <div className="absolute w-full flex items-center z-10" style={{ top: '50%' }}>
              <div className="w-6 border-t-2 border-sky-500"></div>
              <span className="text-xs ml-2 text-sky-400 font-mono font-bold">PRICE {currentPrice}</span>
              <div className="absolute left-0 w-2 h-2 rounded-full bg-sky-500 -ml-1 -mt-1 animate-ping"></div>
            </div>

            <div className="absolute w-full flex items-center" style={{ top: '70%' }}>
              <div className="w-4 border-t border-green-500 border-dashed"></div>
              <span className="text-xs ml-2 text-green-400 font-mono">SSL {sslLevels[0]}</span>
            </div>
            <div className="absolute w-full flex items-center" style={{ top: '90%' }}>
              <div className="w-4 border-t border-green-500 border-dashed"></div>
              <span className="text-xs ml-2 text-green-400 font-mono">SSL {sslLevels[1]}</span>
            </div>
          </div>
        </div>

        {/* Fibonacci Retracement Visual */}
        <div className="card p-4">
          <h3 className="font-bold text-fg-muted mb-4 border-b border-border pb-2">Premium & Discount</h3>
          <div className="flex h-32 items-center gap-4">
            <div className="relative h-full w-8 rounded overflow-hidden flex flex-col-reverse bg-gray-800">
              <div className="w-full bg-green-500/20 border-t border-green-500/50" style={{ height: '50%' }}></div>
              <div className="w-full bg-red-500/20 border-b border-red-500/50" style={{ height: '50%' }}></div>
              <div className="absolute w-full h-1 bg-sky-500 shadow-[0_0_8px_#0ea5e9]" style={{ bottom: `${currentFib}%` }}></div>
            </div>
            <div className="flex flex-col justify-between h-full text-xs font-mono text-gray-500">
              <div className="text-red-400">1.0 (Premium)</div>
              <div>0.79</div>
              <div>0.618 (Golden)</div>
              <div className="text-gray-300">0.5 (Equilibrium)</div>
              <div>0.382</div>
              <div className="text-green-400">0.0 (Discount)</div>
            </div>
          </div>
        </div>

      </div>

      <div className="card p-6 flex flex-col items-center justify-center py-8 relative overflow-hidden">
        {/* Radial background glow */}
        <div className="absolute inset-0 bg-blue-500/5 blur-3xl rounded-full scale-150"></div>
        
        <div className="text-sm text-fg-muted mb-4 uppercase tracking-widest font-bold z-10">Structural Confluence Score</div>
        
        {/* Fake Radial Gauge */}
        <div className="relative w-32 h-32 flex items-center justify-center z-10">
          <svg className="absolute inset-0 w-full h-full transform -rotate-90">
            <circle cx="64" cy="64" r="56" fill="none" stroke="#1f2937" strokeWidth="8" />
            <circle cx="64" cy="64" r="56" fill="none" stroke="#3b82f6" strokeWidth="8" 
                    strokeDasharray="351.8" strokeDashoffset={351.8 - (351.8 * (data?.confluence_score || 85)) / 100} 
                    className="transition-all duration-1000 ease-out" />
          </svg>
          <div className="text-4xl font-mono font-bold text-white">{data?.confluence_score || 85}%</div>
        </div>

        <div className="mt-6 text-xs text-fg-muted max-w-lg text-center z-10">
          The Council requires a minimum <span className="text-white font-bold">80% confluence score</span> across all 3 structural dimensions before authorizing a trade on the execution timeframe.
        </div>
      </div>
    </div>
  );
}
