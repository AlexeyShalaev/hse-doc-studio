import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "bg-0": "var(--bg-0)",
        "bg-1": "var(--bg-1)",
        "bg-2": "var(--bg-2)",
        "bg-3": "var(--bg-3)",
        "bg-hover": "var(--bg-hover)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        "border-soft": "var(--border-soft)",
        "fg-0": "var(--fg-0)",
        "fg-1": "var(--fg-1)",
        "fg-2": "var(--fg-2)",
        "fg-3": "var(--fg-3)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        "accent-soft": "var(--accent-soft)",
        "accent-line": "var(--accent-line)",
        "c-ok": "var(--c-ok)",
        "c-warn": "var(--c-warn)",
        "c-err": "var(--c-err)",
        "c-info": "var(--c-info)",
        "c-ok-soft": "var(--c-ok-soft)",
        "c-warn-soft": "var(--c-warn-soft)",
        "c-err-soft": "var(--c-err-soft)",
        "c-info-soft": "var(--c-info-soft)",
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "system-ui", "sans-serif"],
        mono: [
          "JetBrains Mono",
          "IBM Plex Mono",
          "ui-monospace",
          "SFMono-Regular",
          "monospace",
        ],
        display: ["Inter", "sans-serif"],
      },
      fontSize: {
        "2xs": ["10px", { lineHeight: "1.2" }],
        xs: ["11px", { lineHeight: "1.35" }],
        sm: ["12px", { lineHeight: "1.4" }],
        base: ["13px", { lineHeight: "1.45" }],
        md: ["14px", { lineHeight: "1.45" }],
        lg: ["16px", { lineHeight: "1.4" }],
        xl: ["18px", { lineHeight: "1.35" }],
        "2xl": ["22px", { lineHeight: "1.3" }],
        "3xl": ["28px", { lineHeight: "1.2" }],
      },
      borderRadius: {
        "r-1": "3px",
        "r-2": "6px",
        "r-3": "10px",
        "r-4": "14px",
        pill: "999px",
      },
      boxShadow: {
        "elev-1": "var(--shadow-1)",
        "elev-2": "var(--shadow-2)",
        "elev-pop": "var(--shadow-pop)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        spin: { to: { transform: "rotate(360deg)" } },
        "pulse-ring": {
          "0%": { transform: "scale(1)", opacity: "0.8" },
          "70%": { transform: "scale(1.5)", opacity: "0" },
          "100%": { transform: "scale(1.5)", opacity: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        spin: "spin 1s linear infinite",
        "pulse-ring": "pulse-ring 1.5s ease-out infinite",
      },
    },
  },
  plugins: [tailwindcssAnimate],
} satisfies Config;
