/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // NetCoop AI Design System Colors
        'glass': {
          'bg': 'rgba(10, 14, 29, 0.95)',
          'panel': 'rgba(15, 20, 40, 0.7)',
          'border': 'rgba(56, 189, 248, 0.15)',
          'hover': 'rgba(56, 189, 248, 0.08)',
        },
        'neon': {
          'blue': '#38bdf8',
          'cyan': '#22d3ee',
          'teal': '#14b8a6',
          'green': '#4ade80',
          'magenta': '#e879f9',
          'red': '#f87171',
          'amber': '#fbbf24',
        },
        'surface': {
          '50': 'rgba(255,255,255,0.05)',
          '100': 'rgba(255,255,255,0.08)',
          '200': 'rgba(255,255,255,0.12)',
          '300': 'rgba(255,255,255,0.16)',
        },
      },
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      backdropBlur: {
        'xs': '2px',
        'glass': '12px',
        'glass-heavy': '24px',
      },
      boxShadow: {
        'glass': '0 8px 32px rgba(0, 0, 0, 0.4), inset 0 1px 0 rgba(255, 255, 255, 0.06)',
        'glass-hover': '0 12px 40px rgba(0, 0, 0, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.08)',
        'neon-blue': '0 0 20px rgba(56, 189, 248, 0.3)',
        'neon-cyan': '0 0 20px rgba(34, 211, 238, 0.3)',
        'neon-green': '0 0 20px rgba(74, 222, 128, 0.3)',
        'neon-red': '0 0 20px rgba(248, 113, 113, 0.3)',
        'inner-glass': 'inset 0 1px 0 rgba(255,255,255,0.06), inset 0 -1px 0 rgba(0,0,0,0.2)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite alternate',
        'slide-in-right': 'slideInRight 0.3s ease-out',
        'slide-in-up': 'slideInUp 0.3s ease-out',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        glow: {
          '0%': { boxShadow: '0 0 5px rgba(56, 189, 248, 0.2)' },
          '100%': { boxShadow: '0 0 20px rgba(56, 189, 248, 0.4)' },
        },
        slideInRight: {
          '0%': { transform: 'translateX(20px)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        slideInUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
