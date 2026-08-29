import React, { useState, useEffect } from 'react';
import { Activity, Settings, TrendingUp, BarChart2, BookOpen, Layers } from 'lucide-react';
import { createClient } from '@supabase/supabase-js';
import Dashboard from './Dashboard';
import SettingsPanel from './SettingsPanel';
import MTFAnalysis from './MTFAnalysis';
import TradeSignals from './TradeSignals';
import TradeJournal from './TradeJournal';

export default function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  
  const [supabaseUrl, setSupabaseUrl] = useState(localStorage.getItem('ares_supabase_url') || '');
  const [supabaseKey, setSupabaseKey] = useState(localStorage.getItem('ares_supabase_key') || '');
  
  const [connected, setConnected] = useState(false);
  
  // Data States
  const [engineData, setEngineData] = useState({
    balance: null, todayPnl: { abs: 0, pct: 0 }, winRate: { pct: 0 }, signal: null
  });
  const [mtfData, setMtfData] = useState(null);
  const [signalsList, setSignalsList] = useState([]);
  const [tradesList, setTradesList] = useState([]);

    useEffect(() => {
    if (!supabaseUrl || !supabaseKey) return;
    
    let interval;
    try {
      const supabase = createClient(supabaseUrl, supabaseKey);
      setConnected(true);

      const fetchState = async () => {
        try {
          const { data: s } = await supabase.from('system_state').select('*').eq('id', 1).single();
          if (s) setEngineData(p => ({ ...p, balance: s.balance, todayPnl: { abs: s.today_pnl_abs, pct: s.today_pnl_pct } }));
          
          const { data: m } = await supabase.from('mtf_analysis').select('*').eq('id', 1).single();
          if (m) setMtfData(m);
          
          const { data: sig } = await supabase.from('signals').select('*').order('created_at', { ascending: false }).limit(20);
          if (sig) {
            setSignalsList(sig);
            if (sig.length > 0) setEngineData(prev => ({ ...prev, signal: sig[0] }));
          }
          
          const { data: tr } = await supabase.from('trades').select('*').order('opened_at', { ascending: false }).limit(20);
          if (tr) setTradesList(tr);
        } catch(e) {}
      };

      // Initial Fetch
      fetchState();

      // Robust HTTP Polling Fallback (1-second intervals) guaranteed to bypass WS blockers
      interval = setInterval(fetchState, 1500);

      // Attempt Realtime (if it fails, polling covers it)
      supabase.channel('state')
        .on('postgres_changes', { event: 'UPDATE', schema: 'public', table: 'system_state' }, fetchState)
        .subscribe((s) => { if (s === 'SUBSCRIBED') setConnected(true); });

    } catch (err) {
      console.error(err);
      setConnected(false);
    }
    
    return () => clearInterval(interval);
  }, [supabaseUrl, supabaseKey]);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: Activity },
    { id: 'mtf', label: 'MTF Analysis', icon: Layers },
    { id: 'signals', label: 'Trade Signals', icon: TrendingUp },
    { id: 'journal', label: 'Trade Journal', icon: BookOpen },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  const hasCredentials = supabaseUrl && supabaseKey;

  return (
    <div className="flex flex-col h-screen">
      <header className="h-14 border-b border-border flex items-center justify-between px-4 shrink-0">
        <div className="flex items-center gap-3">
          <div className="text-primary font-bold tracking-widest flex items-center gap-2 text-xl">
            ARES-1 <span className="text-xs text-fg-muted font-normal uppercase tracking-normal">Terminal v2.0 (Supabase Realtime)</span>
          </div>
          <div className={`badge ${connected ? 'badge-green' : 'badge-amber'}`}>
            ● {connected ? 'CONNECTED TO SUPABASE' : 'WAITING FOR CREDENTIALS'}
          </div>
        </div>
      </header>

      <nav className="border-b border-border px-4 py-3 flex gap-6 shrink-0 text-sm overflow-x-auto">
        {navItems.map(item => (
          <button key={item.id} onClick={() => setActiveTab(item.id)}
            className={`flex items-center gap-2 pb-1 font-semibold whitespace-nowrap border-b-2 transition-colors ${
              activeTab === item.id ? 'border-primary text-primary' : 'border-transparent text-fg-muted hover:text-fg'
            }`}>
            <item.icon size={16} />{item.label}
          </button>
        ))}
      </nav>

      <main className="flex-1 overflow-auto p-4 relative">
        {!hasCredentials && (
          <div className="absolute inset-0 bg-background/80 flex items-center justify-center z-50">
            <div className="card p-6 max-w-md w-full">
              <h2 className="text-lg font-bold mb-4 text-center">Supabase Connection Required</h2>
              <SettingsPanel supabaseUrl={supabaseUrl} setSupabaseUrl={setSupabaseUrl} supabaseKey={supabaseKey} setSupabaseKey={setSupabaseKey} />
            </div>
          </div>
        )}
        
        {activeTab === 'dashboard' && <Dashboard data={engineData} supabase={hasCredentials ? createClient(supabaseUrl, supabaseKey) : null} />}
        {activeTab === 'mtf' && <MTFAnalysis data={mtfData} />}
        {activeTab === 'signals' && <TradeSignals signals={signalsList} />}
        {activeTab === 'journal' && <TradeJournal trades={tradesList} />}
        {activeTab === 'settings' && <SettingsPanel supabaseUrl={supabaseUrl} setSupabaseUrl={setSupabaseUrl} supabaseKey={supabaseKey} setSupabaseKey={setSupabaseKey} />}
      </main>
    </div>
  );
}
