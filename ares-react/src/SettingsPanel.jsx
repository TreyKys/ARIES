import React, { useState } from 'react';

export default function SettingsPanel({ supabaseUrl, setSupabaseUrl, supabaseKey, setSupabaseKey }) {
  const [inputUrl, setInputUrl] = useState(supabaseUrl || '');
  const [inputKey, setInputKey] = useState(supabaseKey || '');
  const [saved, setSaved] = useState(false);

  const handleSave = () => {
    localStorage.setItem('ares_supabase_url', inputUrl.trim());
    localStorage.setItem('ares_supabase_key', inputKey.trim());
    setSupabaseUrl(inputUrl.trim());
    setSupabaseKey(inputKey.trim());
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6 max-w-4xl grid grid-cols-1 md:grid-cols-2 gap-6">
      
      {/* DB Config */}
      <div className="card p-5 h-fit">
        <h3 className="font-bold text-lg border-b border-border pb-2 mb-4 text-sky-500">Database Connection</h3>
        <label className="label block mb-2">Supabase URL</label>
        <input type="text" value={inputUrl} onChange={(e) => setInputUrl(e.target.value)} className="w-full bg-background border border-border rounded p-2 mb-4 text-fg font-mono text-sm" />
        <label className="label block mb-2">Supabase Anon Key</label>
        <input type="password" value={inputKey} onChange={(e) => setInputKey(e.target.value)} className="w-full bg-background border border-border rounded p-2 mb-4 text-fg font-mono text-sm" />
        <button onClick={handleSave} className={`w-full py-2 rounded font-bold transition-colors ${saved ? 'bg-green text-white' : 'bg-primary text-white'}`}>{saved ? 'Saved!' : 'Save Connection'}</button>
      </div>

      {/* Risk Parameters */}
      <div className="card p-5 h-fit">
        <h3 className="font-bold text-lg border-b border-border pb-2 mb-4 text-emerald-500">Risk Parameters</h3>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="label block mb-2 text-xs">Max Risk Per Trade (%)</label>
            <input type="number" defaultValue="1.5" className="w-full bg-background border border-border rounded p-2 text-fg font-mono" />
          </div>
          <div>
            <label className="label block mb-2 text-xs">Min R:R Ratio</label>
            <input type="number" defaultValue="2.0" className="w-full bg-background border border-border rounded p-2 text-fg font-mono" />
          </div>
          <div>
            <label className="label block mb-2 text-xs">Max Daily Drawdown (%)</label>
            <input type="number" defaultValue="4.0" className="w-full bg-background border border-border rounded p-2 text-fg font-mono text-red-400" />
          </div>
          <div>
            <label className="label block mb-2 text-xs">Max Total Drawdown (%)</label>
            <input type="number" defaultValue="10.0" className="w-full bg-background border border-border rounded p-2 text-fg font-mono text-red-500" />
          </div>
        </div>
      </div>

      {/* Session Configuration */}
      <div className="card p-5 h-fit md:col-span-2">
        <h3 className="font-bold text-lg border-b border-border pb-2 mb-4 text-purple-500">Session Killzones</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="border border-border rounded p-4 flex items-center justify-between">
            <div><div className="font-bold">London</div><div className="text-xs text-gray-500">07:00 - 10:00 UTC</div></div>
            <input type="checkbox" defaultChecked className="toggle" />
          </div>
          <div className="border border-border rounded p-4 flex items-center justify-between">
            <div><div className="font-bold">New York</div><div className="text-xs text-gray-500">12:00 - 15:00 UTC</div></div>
            <input type="checkbox" defaultChecked className="toggle" />
          </div>
          <div className="border border-border rounded p-4 flex items-center justify-between opacity-50">
            <div><div className="font-bold">Asia Range</div><div className="text-xs text-gray-500">00:00 - 03:00 UTC</div></div>
            <input type="checkbox" className="toggle" />
          </div>
        </div>
      </div>
      
    </div>
  );
}
