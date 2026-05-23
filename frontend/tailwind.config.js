/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#1a1714',
          soft: '#4a4540',
          muted: '#9a9590',
        },
        paper: {
          DEFAULT: '#f5f0e8',
          2: '#ede8dc',
          3: '#e2ddd0',
        },
        accent: {
          DEFAULT: '#8b4513',
          light: '#a0522d',
        },
      },
      fontFamily: {
        serif: ['"Nanum Myeongjo"', 'Georgia', 'serif'],
        sans: ['Pretendard', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
