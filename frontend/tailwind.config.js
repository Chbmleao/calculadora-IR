/** @type {import('tailwindcss').Config} */
export default {
  // Dark mode follows the OS/browser preference (README §3: light/dark via
  // prefers-color-scheme). `dark:` utilities activate under a dark media query.
  darkMode: "media",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Single accent color (indigo) exposed as a semantic `brand` scale.
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
        },
      },
    },
  },
  plugins: [],
};
