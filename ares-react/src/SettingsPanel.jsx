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
    <div className="space-y-6 max-w-2xl">
      <div className="card p-5">
        <h3 className="font-bold text-lg border-b border-border pb-2 mb-4">Supabase Realtime Connection</h3>
        
        <label className="label block mb-2">Supabase URL</label>
        <input 
          type="text" 
          value={inputUrl}
          onChange={(e) => setInputUrl(e.target.value)}
          className="w-full bg-background border border-border rounded p-2 mb-4 text-fg font-mono text-sm"
          placeholder="https://xxxxxx.supabase.co"
        />

        <label className="label block mb-2">Supabase Anon Key</label>
        <input 
          type="password" 
          value={inputKey}
          onChange={(e) => setInputKey(e.target.value)}
          className="w-full bg-background border border-border rounded p-2 mb-4 text-fg font-mono text-sm"
          placeholder="eyJhbGciOiJIUzI1NiIsInR..."
        />

        <p className="text-xs text-fg-muted mb-4">
          This connects your frontend directly to your secure Supabase database, completely removing the need for fragile network tunnels or WebSockets to the Python Engine.
        </p>
        
        <button 
          onClick={handleSave}
          className={`w-full py-2 rounded font-bold transition-colors ${saved ? 'bg-green text-white' : 'bg-primary text-white hover:opacity-90'}`}
        >
          {saved ? 'Credentials Saved!' : 'Connect to Supabase'}
        </button>
      </div>
    </div>
  );
}
