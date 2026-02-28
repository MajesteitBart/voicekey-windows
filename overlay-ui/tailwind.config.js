/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        border: "hsl(var(--border))",
        card: "hsl(var(--card))",
        "card-foreground": "hsl(var(--card-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        ring: "hsl(var(--ring))",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: ["Segoe UI Variable", "Segoe UI", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      boxShadow: {
        acrylic: "0 9px 18px rgba(0,0,0,0.19), 0 2px 6px rgba(0,0,0,0.15)",
        flyout: "0 8px 16px rgba(0,0,0,0.14)",
      },
    },
  },
  plugins: [],
}
