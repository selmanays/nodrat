import type { Config } from "tailwindcss";

/**
 * Tailwind config — Nodrat Design System tokens
 * docs/design/design-system.md §2, §7
 */
const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
    "./src/app/**/*.{ts,tsx}",
  ],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: {
        "2xl": "1400px",
      },
    },
    extend: {
      colors: {
        // ---- Brand (Mat Lacivert) ----
        brand: {
          50: "#F0F4F8",
          100: "#D9E2EC",
          200: "#BCCCDC",
          300: "#829AB1",
          500: "#486581",
          700: "#243B53",
          900: "#102A43",
          950: "#0A1F33",
        },

        // ---- Accent (Sıcak Amber — sınırlı kullanım) ----
        accent: {
          50: "#FFF8E1",
          100: "#FFECB3",
          300: "#FFD54F",
          500: "#FFA000",
          700: "#FF6F00",
          900: "#E65100",
        },

        // ---- Semantic ----
        success: { DEFAULT: "#10B981" },
        warning: { DEFAULT: "#F59E0B" },
        error: { DEFAULT: "#EF4444" },
        info: { DEFAULT: "#3B82F6" },

        // shadcn/ui token mapping (CSS variables)
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "monospace"],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
