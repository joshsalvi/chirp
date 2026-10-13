/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Theme accent — overridden by CSS variables per theme
        accent: {
          50:  'var(--accent-50)',
          100: 'var(--accent-100)',
          200: 'var(--accent-200)',
          300: 'var(--accent-300)',
          400: 'var(--accent-400)',
          500: 'var(--accent-500)',
          600: 'var(--accent-600)',
          700: 'var(--accent-700)',
          800: 'var(--accent-800)',
          900: 'var(--accent-900)',
        },
        // Keep chirp green for things that must always be green
        chirp: {
          50: '#fefce8', 100: '#fef9c3', 200: '#fef08a', 300: '#fde047',
          400: '#facc15', 500: '#eab308', 600: '#ca8a04', 700: '#a16207',
          800: '#854d0e', 900: '#713f12', 950: '#422006',
        },
        surface: {
          950: 'var(--s950)', 900: 'var(--s900)', 800: 'var(--s800)',
          700: 'var(--s700)', 600: 'var(--s600)', 500: 'var(--s500)',
          400: 'var(--s400)', 300: 'var(--s300)',
        },
      },
      fontFamily: {
        display: ['Lora', 'Georgia', 'serif'],
        sans:    ['DM Sans', '-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
        mono:    ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        'sm': '6px', DEFAULT: '10px', 'md': '10px',
        'lg': '14px', 'xl': '18px', '2xl': '24px', '3xl': '32px',
      },
      boxShadow: {
        'glow':    '0 0 24px var(--glow-color)',
        'glow-lg': '0 0 48px var(--glow-color)',
        'lift':    '0 4px 24px rgba(0,0,0,0.5), 0 1px 4px rgba(0,0,0,0.3)',
        'card':    '0 1px 3px rgba(0,0,0,0.4), 0 4px 16px rgba(0,0,0,0.2)',
        'modal':   '0 24px 80px rgba(0,0,0,0.7)',
      },
      animation: {
        'fade-in':    'fadeIn .22s ease-out both',
        'slide-up':   'slideUp .28s cubic-bezier(.16,1,.3,1) both',
        'slide-down': 'slideDown .22s cubic-bezier(.16,1,.3,1) both',
        'scale-in':   'scaleIn .2s cubic-bezier(.34,1.56,.64,1) both',
        'shimmer':    'shimmer 1.8s linear infinite',
        'live':       'livePulse 2s ease-in-out infinite',
        'float':      'float 6s ease-in-out infinite',
        'stagger-1':  'fadeIn .3s .05s ease-out both',
        'stagger-2':  'fadeIn .3s .1s ease-out both',
        'stagger-3':  'fadeIn .3s .15s ease-out both',
        'stagger-4':  'fadeIn .3s .2s ease-out both',
        'stagger-5':  'fadeIn .3s .25s ease-out both',
        'stagger-6':  'fadeIn .3s .3s ease-out both',
        'pop-in':     'popIn .3s cubic-bezier(.34,1.56,.64,1) both',
      },
      keyframes: {
        fadeIn:    { '0%': { opacity:'0' }, '100%': { opacity:'1' } },
        slideUp:   { '0%': { transform:'translateY(14px)', opacity:'0' }, '100%': { transform:'translateY(0)', opacity:'1' } },
        slideDown: { '0%': { transform:'translateY(-10px)', opacity:'0' }, '100%': { transform:'translateY(0)', opacity:'1' } },
        scaleIn:   { '0%': { transform:'scale(.94)', opacity:'0' }, '100%': { transform:'scale(1)', opacity:'1' } },
        shimmer:   { '0%': { backgroundPosition:'-200% 0' }, '100%': { backgroundPosition:'200% 0' } },
        livePulse: { '0%,100%': { opacity:'1', transform:'scale(1)' }, '50%': { opacity:'.4', transform:'scale(1.5)' } },
        float:     { '0%,100%': { transform:'translateY(0)' }, '50%': { transform:'translateY(-6px)' } },
        popIn:     { '0%': { transform:'scale(.85) translateY(6px)', opacity:'0' }, '100%': { transform:'scale(1) translateY(0)', opacity:'1' } },
      },
      transitionTimingFunction: {
        'spring': 'cubic-bezier(.34,1.56,.64,1)',
        'out':    'cubic-bezier(.16,1,.3,1)',
        'snappy': 'cubic-bezier(.4,0,.2,1)',
      },
      backgroundImage: {
        'grain': "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.04'/%3E%3C/svg%3E\")",
      },
    },
  },
  plugins: [],
}
