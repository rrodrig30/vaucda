/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#2c5282',
          500: '#3182ce',
          600: '#2c5282',
        },
        secondary: {
          DEFAULT: '#4299e1',
        },
        accent: {
          DEFAULT: '#63b3ed',
        },
        medical: {
          DEFAULT: '#0d9488',
          500: '#14b8a6',
        },
        success: {
          DEFAULT: '#10b981',
          50: '#ecfdf5',
          900: '#065f46',
        },
        warning: {
          DEFAULT: '#f59e0b',
          50: '#fefce8',
          900: '#92400e',
        },
        error: {
          DEFAULT: '#ef4444',
          50: '#fee2e2',
          900: '#dc2626',
        },
        info: {
          DEFAULT: '#06b6d4',
          50: '#f0f9ff',
          900: '#1d4ed8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['Roboto Mono', 'monospace'],
      },
      boxShadow: {
        primary: '0 4px 12px rgba(59, 130, 246, 0.3)',
        'primary-lg': '0 8px 20px rgba(59, 130, 246, 0.4)',
        medical: '0 4px 12px rgba(13, 148, 136, 0.3)',
        focus: '0 0 0 4px rgba(44, 82, 130, 0.1)',
      },
    },
  },
  plugins: [],
};
