/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        noc: {
          bg: '#0a0e1a',
          panel: '#0f1629',
          border: '#1e2d4a',
          green: '#00ff88',
          red: '#ff4444',
          yellow: '#ffaa00',
          blue: '#3b82f6',
          muted: '#4a5568',
          text: '#e2e8f0',
        }
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      }
    }
  },
  plugins: []
}
