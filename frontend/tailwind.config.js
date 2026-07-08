/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './lib/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        charcoal: '#33343B',
        ink: '#1A1A1A',
        muted: '#6B6B73',
        subtle: '#BFC0C5',
        accent: '#A3D16B',
        'accent-dark': '#8BB85A',
        success: '#A3D16B',
        surface: '#F4F5F8',
        'surface-elevated': '#FFFFFF',
        // Legacy aliases — mapped to new palette
        navy: '#33343B',
        navy2: '#8BB85A',
        teal: '#A3D16B',
        mint: '#A3D16B',
        light: '#F4F5F8',
        border: '#E2E3E8',
        mid: '#6B6B73',
        lt: '#BFC0C5',
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
      fontSize: {
        'display-lg': ['2.25rem', { lineHeight: '1.15', letterSpacing: '-0.03em', fontWeight: '700' }],
        'display': ['1.75rem', { lineHeight: '1.2', letterSpacing: '-0.02em', fontWeight: '700' }],
      },
      borderRadius: {
        '2xl': '1rem',
        '3xl': '1.25rem',
        '4xl': '1.5rem',
      },
      boxShadow: {
        soft: '0 1px 2px rgba(26, 26, 26, 0.04), 0 4px 16px rgba(26, 26, 26, 0.06)',
        card: '0 0 0 1px rgba(191, 192, 197, 0.35), 0 8px 24px rgba(26, 26, 26, 0.06)',
        'card-hover': '0 0 0 1px rgba(163, 209, 107, 0.35), 0 12px 32px rgba(163, 209, 107, 0.15)',
        glow: '0 0 24px rgba(163, 209, 107, 0.45)',
        'glow-success': '0 0 20px rgba(163, 209, 107, 0.4)',
        sidebar: '4px 0 24px rgba(0, 0, 0, 0.15)',
      },
      backgroundImage: {
        'mesh': 'radial-gradient(ellipse 80% 60% at 10% 0%, rgba(163, 209, 107, 0.1) 0%, transparent 55%), radial-gradient(ellipse 70% 50% at 90% 10%, rgba(163, 209, 107, 0.06) 0%, transparent 50%), linear-gradient(180deg, #F8F9FC 0%, #F0F2F6 100%)',
        'accent-gradient': 'linear-gradient(135deg, #A3D16B 0%, #8BB85A 100%)',
        'success-gradient': 'linear-gradient(135deg, #A3D16B 0%, #8BB85A 100%)',
        'sidebar': 'linear-gradient(180deg, #222328 0%, #1A1A1A 55%, #141414 100%)',
      },
      animation: {
        'fade-in': 'fade-in 0.35s ease-out',
        'slide-up': 'slide-up 0.4s ease-out',
        'pulse-glow': 'pulse-glow 2.5s ease-in-out infinite',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'pulse-glow': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(163, 209, 107, 0.45)' },
          '50%': { boxShadow: '0 0 0 8px rgba(163, 209, 107, 0)' },
        },
      },
      transitionTimingFunction: {
        premium: 'cubic-bezier(0.22, 1, 0.36, 1)',
      },
    },
  },
  safelist: [
    'aspect-video',
    'aspect-square',
    'aspect-[9/16]',
    'aspect-[16/9]',
    'object-cover',
    'object-contain',
    'grid-cols-1',
    'grid-cols-2',
    'grid-cols-3',
    'grid-cols-4',
    'sm:grid-cols-2',
    'sm:grid-cols-3',
    'md:grid-cols-3',
    'md:grid-cols-4',
    'lg:grid-cols-4',
  ],
  plugins: [],
}
