/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './index.html',
    './lifeos_dashboard.html',
    './frontend/js/**/*.js'
  ],
  safelist: [
    {
      pattern: /(bg|text|border)-(slate|red|yellow|green|emerald|blue|indigo|purple|pink|orange)-(50|100|200|300|400|500|600|700|800|900)/
    },
    {
      pattern: /(bg|text)-(primary|secondary|dark|light)/
    }
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif']
      },
      colors: {
        primary: '#4f46e5',
        secondary: '#10b981',
        dark: '#1e293b',
        light: '#f8fafc'
      }
    }
  },
  plugins: []
};
