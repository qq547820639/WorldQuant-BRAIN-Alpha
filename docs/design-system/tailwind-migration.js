/**
 * BRAIN Alpha Ops — Terminal Precision Tailwind Config
 * v2.0 Migration Reference
 *
 * Replace the existing tailwind.config.js with this file.
 * Old config was: brand-indigo (50-700), success/warning/danger/muted
 *
 * Key changes:
 *   - brand.* → accent.* (amber-based)
 *   - Added surface elevation scale (surface-1 through surface-3)
 *   - Added semantic positive/negative/warning/info with subtle backgrounds
 *   - Neutral grays replaced with warm-tinted scale
 *   - Monospace font switched to JetBrains Mono
 */

export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"DM Sans"', "system-ui", "-apple-system", "sans-serif"],
        mono: ['"JetBrains Mono"', '"Fira Code"', '"Cascadia Code"', "monospace"],
        display: ['"DM Sans"', "system-ui", "-apple-system", "sans-serif"],
      },
      fontSize: {
        "2xs":   ["0.6875rem", { lineHeight: "1.4" }],  // 11px — micro labels
        xs:      ["0.75rem",   { lineHeight: "1.5" }],   // 12px
        sm:      ["0.8125rem", { lineHeight: "1.5" }],   // 13px — table cells
        base:    ["0.9375rem", { lineHeight: "1.5" }],   // 15px — body
        md:      ["1.0625rem", { lineHeight: "1.4" }],   // 17px — nav
        lg:      ["1.25rem",   { lineHeight: "1.3" }],   // 20px — section titles
        xl:      ["1.5rem",    { lineHeight: "1.2" }],   // 24px — panel titles
        "2xl":   ["1.875rem",  { lineHeight: "1.15" }],  // 30px — KPI values
        "3xl":   ["2.375rem",  { lineHeight: "1.1" }],   // 38px — hero metrics
      },
      spacing: {
        // 4px base grid — use sparingly, prefer the named scale
        "0.5": "0.125rem",
        "grid-1": "0.25rem",
        "grid-2": "0.5rem",
        "grid-3": "0.75rem",
        "grid-4": "1rem",
        "grid-5": "1.25rem",
        "grid-6": "1.5rem",
        "grid-8": "2rem",
        "grid-10": "2.5rem",
        "grid-12": "3rem",
        "grid-16": "4rem",
      },
      borderRadius: {
        none: "0",
        sm: "2px",
        md: "4px",
        lg: "6px",
        xl: "8px",
      },
      colors: {
        // ── Warm-tinted Neutral Scale ──
        neutral: {
          0:   "oklch(0.985 0.002 45)",
          5:   "oklch(0.960 0.003 45)",
          10:  "oklch(0.920 0.004 45)",
          15:  "oklch(0.870 0.005 45)",
          20:  "oklch(0.820 0.005 45)",
          25:  "oklch(0.760 0.006 45)",
          30:  "oklch(0.700 0.006 45)",
          35:  "oklch(0.640 0.006 45)",
          40:  "oklch(0.580 0.006 45)",
          50:  "oklch(0.480 0.006 45)",
          60:  "oklch(0.380 0.007 45)",
          70:  "oklch(0.300 0.007 45)",
          80:  "oklch(0.220 0.008 45)",
          85:  "oklch(0.180 0.008 45)",
          90:  "oklch(0.145 0.009 45)",
          95:  "oklch(0.115 0.009 45)",
          98:  "oklch(0.095 0.008 45)",
          100: "oklch(0.080 0.007 45)",
        },

        // ── Surface Elevation (dark theme) ──
        surface: {
          root:   "oklch(0.085 0.006 45)",
          1:      "oklch(0.100 0.007 45)",
          2:      "oklch(0.115 0.007 45)",
          3:      "oklch(0.135 0.008 45)",
          hover:  "oklch(0.155 0.008 45)",
          active: "oklch(0.175 0.009 45)",
        },

        // ── Accent: Amber (replaces old brand.*) ──
        accent: {
          subtle: "oklch(0.65 0.07 80 / 0.12)",
          DEFAULT: "oklch(0.65 0.14 80)",
          hover:   "oklch(0.72 0.12 83)",
          pressed: "oklch(0.55 0.13 75)",
          text:    "oklch(0.72 0.14 83)",
        },

        // ── Semantic Colors ──
        positive: {
          subtle:  "oklch(0.52 0.06 155 / 0.15)",
          DEFAULT: "oklch(0.52 0.10 155)",
          text:    "oklch(0.62 0.10 160)",
        },
        negative: {
          subtle:  "oklch(0.48 0.06 22 / 0.15)",
          DEFAULT: "oklch(0.48 0.12 22)",
          text:    "oklch(0.58 0.12 25)",
        },
        warning: {
          subtle:  "oklch(0.65 0.06 85 / 0.15)",
          DEFAULT: "oklch(0.65 0.10 85)",
          text:    "oklch(0.75 0.10 88)",
        },
        info: {
          subtle:  "oklch(0.58 0.06 245 / 0.12)",
          DEFAULT: "oklch(0.58 0.12 245)",
          text:    "oklch(0.68 0.10 248)",
        },

        // ── Data Visualization ──
        data: {
          positive: "oklch(0.52 0.10 155)",
          negative: "oklch(0.48 0.12 22)",
          neutral:  "oklch(0.50 0.08 188)",
          accent:   "oklch(0.65 0.14 80)",
          muted:    "oklch(0.45 0.005 45)",
        },

        // ── Border Colors ──
        border: {
          subtle:  "oklch(0.22 0.007 45)",
          DEFAULT: "oklch(0.28 0.008 45)",
          strong:  "oklch(0.36 0.008 45)",
          focus:   "oklch(0.65 0.14 80)",
        },

        // ── Text Colors ──
        text: {
          primary:   "oklch(0.92 0.003 45)",
          secondary: "oklch(0.72 0.005 45)",
          tertiary:  "oklch(0.52 0.006 45)",
          disabled:  "oklch(0.38 0.006 45)",
          inverse:   "oklch(0.10 0.007 45)",
        },
      },
    },
  },
  plugins: [],
};


/* ═══════════════════════════════════════════════════════════════
   MIGRATION MAP: old → new class names
   ═══════════════════════════════════════════════════════════════

   Backgrounds:
     bg-slate-50      → bg-surface-root
     bg-white         → bg-surface-1
     bg-slate-50      → bg-surface-2  (table headers)
     bg-slate-100     → bg-surface-hover
     bg-white/95      → bg-surface-2/95

   Text:
     text-slate-950   → text-text-primary
     text-slate-700   → text-text-secondary
     text-slate-600   → text-text-secondary
     text-slate-500   → text-text-tertiary
     text-gray-400    → text-text-tertiary

   Brand → Accent:
     bg-brand-600     → bg-accent
     text-brand-700   → text-accent
     bg-brand-50/40   → bg-accent-subtle
     border-brand-200 → border-accent/20

   Success/Warning/Danger:
     bg-success       → bg-positive
     text-success     → text-positive
     text-danger      → text-negative
     text-warning     → text-warning

   Borders:
     border-slate-200 → border-border-subtle
     border-slate-300 → border-border-DEFAULT

   Badges:
     bg-emerald-50    → bg-positive-subtle
     text-emerald-700 → text-positive
     bg-red-50        → bg-negative-subtle
     bg-amber-50      → bg-warning-subtle

   Cards:
     .card            → .panel
     .reader-panel    → .panel
     shadow-sm        → (remove — depth via surface color, not shadow)
*/
