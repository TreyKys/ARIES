/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        background: '#0a0e17',
        card: '#131826',
        primary: '#3b82f6',
        green: '#10b981',
        red: '#ef4444',
        amber: '#f59e0b',
        muted: '#1f2937',
        fg: '#f8fafc',
        'fg-muted': '#94a3b8',
        border: '#1e293b'
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Menlo', 'monospace'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
