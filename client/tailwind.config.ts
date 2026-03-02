import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // Koru CRM Color Scheme - Light Theme
        primary: {
          DEFAULT: '#EF1D1D', // Primary color
          light: '#F97373',
          dark: '#B91C1C',
          gradient: 'linear-gradient(135deg, #EF1D1D 0%, #F97373 50%, #B91C1C 100%)',
        },
        secondary: {
          DEFAULT: '#1E40AF', // Blue gradient
          dark: '#1E3A8A',
          light: '#3B82F6',
        },
        scaffold: '#F9FAFB', // Light Background
        card: '#FFFFFF', // Card Background
        bar: '#FFFFFF', // Top Bar Background
        background: '#F9FAFB',
        sidebar: '#FFFFFF',
        panel: '#F8FAFC',
        text: {
          primary: '#0F172A',
          secondary: '#475569',
          muted: '#94A3B8',
        },
        border: '#E5E7EB',
        chat: {
          user: '#EF1D1D',
          agent: '#F1F5F9',
          ai: '#EEF2FF',
        },
        status: {
          success: '#22C55E',
          warning: '#F59E0B',
          error: '#EF4444',
          info: '#3B82F6',
        },
      },
      spacing: {
        'sidebar-mobile': '0px',
        'sidebar-tablet': '64px',
        'sidebar-laptop': '72px',
        'sidebar-desktop': '80px',
        'sidebar-ultrawide': '96px',
        'chatlist-tablet': '260px',
        'chatlist-laptop': '300px',
        'chatlist-desktop': '340px',
        'chatlist-ultrawide': '380px',
        'context-tablet': '260px',
        'context-laptop': '300px',
        'context-desktop': '340px',
        'context-ultrawide': '380px',
      },
      height: {
        'chat-header': '64px',
        'message-input': '56px',
        'kpi-card': '120px',
      },
      maxWidth: {
        'message-bubble': '70%',
        'modal-sm': '360px',
        'modal-md': '520px',
        'modal-lg': '720px',
        'modal-xl': '960px',
      },
      minHeight: {
        'chart': '320px',
        'chart-lg': '360px',
      },
    },
  },
  plugins: [],
};

export default config;
