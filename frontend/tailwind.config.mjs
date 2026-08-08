/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,html,js,jsx,ts,tsx,vue}'],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#eff6ff', 100: '#dbeafe', 500: '#2563eb',
          600: '#1d4ed8', 700: '#1e40af',
        },
      },
    },
  },
  plugins: [],
};
