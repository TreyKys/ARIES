import React, { useEffect, useRef, useState } from 'react';
import { createChart, CandlestickSeries } from 'lightweight-charts';
import { Terminal } from 'lucide-react';

export default function Dashboard({ data, supabase }) {
  const chartContainerRef = useRef();
  const [logs, setLogs] = useState([]);
  const logsEndRef = useRef(null);
  
  // Realtime Logs Subscription
  useEffect(() => {
    if (!supabase) return;
    
    // Fetch initial logs
    supabase.from('council_feed').select('*').order('timestamp', { ascending: false }).limit(50).then(({ data }) => {
      if (data) setLogs(data.reverse());
    });

    const feedSub = supabase.channel('feed')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'council_feed' }, (p) => {
        setLogs(prev => [...prev, p.new].slice(-50));
      }).subscribe();

    return () => supabase.removeChannel(feedSub);
  }, [supabase]);

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // Chart setup
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#9ca3af' },
      grid: { vertLines: { color: '#1f2937' }, horzLines: { color: '#1f2937' } },
      width: chartContainerRef.current.clientWidth,
      height: 300,
      timeScale: { timeVisible: true, secondsVisible: false },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: '#10b981', downColor: '#ef4444', borderVisible: false,
      wickUpColor: '#10b981', wickDownColor: '#ef4444',
    });

    // Dummy data for now until we wire CCXT directly to the frontend or via Supabase
    // In production, you'd fetch the OHLCV from Binance API directly here in the frontend to save DB costs
    const generateDummyData = () => {
      let currentPrice = 64000;
      let time = Math.floor(Date.now() / 1000) - 86400;
      const data = [];
      for (let i = 0; i < 100; i++) {
        const open = currentPrice;
        const close = open + (Math.random() - 0.5) * 100;
        const high = Math.max(open, close) + Math.random() * 50;
        const low = Math.min(open, close) - Math.random() * 50;
        data.push({ time: time + i * 900, open, high, low, close });
        currentPrice = close;
      }
      return data;
    };

    candlestickSeries.setData(generateDummyData());

    const handleResize = () => chart.applyOptions({ width: chartContainerRef.current.clientWidth });
    window.addEventListener('resize', handleResize);
    
    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  const getLogColor = (severity) => {
    switch (severity) {
      case 'WARN': return 'text-amber-500';
      case 'SUCCESS': return 'text-emerald-500';
      case 'DEBUG': return 'text-slate-500';
      default: return 'text-sky-400';
    }
  };

  return (
    <div className="flex flex-col gap-4 h-full">
      
      {/* Top Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 shrink-0">
        <div className="card p-4">
          <div className="text-xs text-fg-muted uppercase font-bold mb-1">Account Balance</div>
          <div className="text-2xl font-bold">${Number(data?.balance || 0).toFixed(2) || '0.00'}</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-fg-muted uppercase font-bold mb-1">Today's P&L</div>
          <div className={`text-2xl font-bold ${data?.todayPnl?.abs > 0 ? 'text-green' : data?.todayPnl?.abs < 0 ? 'text-red' : ''}`}>
            {data?.todayPnl?.abs > 0 ? '+' : ''}{Number(data?.todayPnl?.abs || 0).toFixed(2) || '0.00'} 
            <span className="text-sm ml-2">({Number(data?.todayPnl?.pct || 0).toFixed(2) || '0.00'}%)</span>
          </div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-fg-muted uppercase font-bold mb-1">Win Rate</div>
          <div className="text-2xl font-bold text-blue">{Number(data?.winRate || 0).toFixed(1) || '0.0'}%</div>
        </div>
        <div className="card p-4">
          <div className="text-xs text-fg-muted uppercase font-bold mb-1">System Status</div>
          <div className="text-2xl font-bold text-purple flex items-center gap-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-purple"></span>
            </span>
            PAPER
          </div>
        </div>
      </div>

      {/* Main Chart Area */}
      <div className="card flex-1 min-h-[300px] flex flex-col overflow-hidden relative">
        <div className="p-3 border-b border-border font-bold flex justify-between items-center bg-muted/30 absolute w-full z-10">
          <span>BTC/USDT - Live Execution Chart</span>
          <span className="badge badge-blue">BINANCE FUTURES</span>
        </div>
        <div ref={chartContainerRef} className="flex-1 w-full h-full mt-12" />
      </div>

      {/* Live Council Feed (Terminal) */}
      <div className="card h-64 shrink-0 flex flex-col overflow-hidden bg-[#0d1117] border-gray-800">
        <div className="p-2 border-b border-gray-800 font-mono text-xs text-gray-400 flex items-center gap-2 bg-[#161b22]">
          <Terminal size={14} /> THE COUNCIL - LIVE REASONING FEED
        </div>
        <div className="flex-1 overflow-y-auto p-4 font-mono text-xs leading-relaxed">
          {logs.length === 0 ? (
            <div className="text-gray-500 italic">Awaiting Council initialization...</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="mb-1 flex gap-3 hover:bg-gray-800/50 px-1 rounded">
                <span className="text-gray-600 shrink-0">[{new Date(log.timestamp).toLocaleTimeString()}]</span>
                <span className="text-purple-400 font-bold shrink-0 w-24">@{log.agent_name}</span>
                <span className={`${getLogColor(log.severity)} break-all`}>{log.message}</span>
              </div>
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

    </div>
  );
}
