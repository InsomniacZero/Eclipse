# 🏛️ Universal Design System Specification (`DESIGN-SYS.md`)
> **The Universal Visual, Architectural & Interaction Design Standard for All Applications & Tools.**
> *Last Updated: October 2026*

---

> [!IMPORTANT]
> **Universal Scope Across All Projects**:
> This document is the single source of truth for **all current and future web applications, developer tools, admin portals, dashboards, and mobile web experiences** built in this workspace. Every project—whether a full-stack dashboard, high-performance proxy, desktop utility, data inspector, 3D viewport, or mobile-first web app—must adhere strictly to these principles, tokens, and component guidelines.

---

## 🎯 1. Core Philosophy: The Warm Stone & Technical Editorial Aesthetic

Every application built under this design system is engineered with a strict **editorial, high-density, instrument-grade aesthetic** known as **Warm Stone & Terracotta** (or Deep Obsidian).

### Core Principles
1. **Precision Instrument, Not Marketing Toy**: The interface prioritizes data density, telemetry, clear hierarchy, and immediate control over frivolous consumer-facing gimmicks.
2. **Editorial Restraint**: Color is applied with surgical intent. Surfaces are deep neutral stone (`#151515` to `#21201f`) with a single signature accent—**Terracotta Red/Orange (`#d97757`)**—and service-specific accents reserved strictly for badges, status indicators, and syntax highlights.
3. **Tactile Geometry**: Everything has deliberate structure. Radii are crisp (4px, 6px, 8px, 10px). Micro-interactions provide subtle tactile feedback (`scale(0.98)` on click) without laggy spring physics.
4. **100dvh Lock & Viewport Mastery**: Applications never let the window body scroll freely. Every panel is contained within the viewport (`100dvh`), with internal panels handling their own independent, smooth scrolling.
5. **Fluid Duality (PC vs. Phone)**: A desktop layout and a mobile layout are distinct architectural paradigms. Interfaces must adapt structurally between desktop high-density multi-pane views and mobile touch-first bottom ergonomics without breaking or clipping at 125% zoom.
6. **Zero-Glow Matte Craft**: No glowing orbs, no neon bloom, no box-in-a-box nested clutter. Elevation is communicated through subtle layered alpha shadows and crisp hairline borders (`1px solid var(--border-subtle)`).

---

## 🚫 2. The Strict "DO NOT" List (The 18 Forbidden Anti-Patterns)

Any contributor, agent, or developer creating or modifying user interfaces across any project **MUST NEVER** introduce the following anti-patterns:

| ❌ Strictly Forbidden Pattern | Why It Is Banned | ✅ Required Standard |
| :--- | :--- | :--- |
| **1. Status Orbs & Pulsing Dots** | Pulsing green/red dots or glowing orbs feel like cheap sci-fi widgets and create visual noise. | **Structured Text Badges / Solid Chips**: Use clean, flat rectangular badges with subtle background tint and crisp typography (e.g. `[● ONLINE]` in 11px mono). No pulsing animations. |
| **2. Glow Effects on Anything** | Glowing box-shadows, neon borders, and text glows look tacky, amateurish, and degrade text contrast. | **Strictly Matte Surfaces**: Crisp, flat surfaces with subtle **1px solid stone borders** (`#2b2826`). Absolute zero `box-shadow` glows or neon outlines. |
| **3. Nested Cards & Over-Bordering ("Boxing")** | Placing a card inside a card, or boxing buttons inside an already boxed container, creates visually claustrophobic "box-in-a-box" clutter. | **Single-Layer Surface Hierarchy**: One container level only. Divide inner sections using whitespace, subtle dividers (`1px solid var(--border-subtle)`), or flat background color shifts. Never enclose buttons inside separate boxes within cards. |
| **4. Contrasting Hover Line Effects** | High-contrast underline jumps, jarring border outlines, or contrasting lines on hover look jittery and distract the eye. | **Smooth Surface Luminosity Shift**: Hover states must only shift surface luminosity smoothly (e.g. `var(--bg-surface)` to `var(--bg-surface-hover)`), preserving stable geometry. |
| **5. Pill-Shaped Buttons (`rounded-full` / `9999px`)** | Looks like a consumer toy app and breaks visual rhythm in technical tools and dashboards. | **Geometric Structured Radii**: Use `var(--radius-sm)` (6px) or `var(--radius-md)` (8px). Never use `rounded-full` or `9999px` on action buttons. |
| **6. Native `<select>` Dropdowns** | Native browser select dropdowns render inconsistently across OSes, lack search filtering, and look dated. | **Custom Popover Select Component** (`.custom-select-wrapper`) with built-in search filter, keyboard navigation, and custom options list. |
| **7. Default Browser Popups (`alert()`, `confirm()`, `prompt()`)** | Native dialogs freeze the thread, look atrocious, and break application immersion. | **Custom Glassmorphic Toast Notification System** (`showToast()`) and custom modal confirmation overlays. |
| **8. Default Stepping Stone Buttons for Numbers** | Native browser `<input type="number">` spinner steppers look broken, clunky, and render differently in every browser. | **Custom Numeric Stepper or Clean Input**: Hide default browser spin buttons (`::-webkit-inner-spin-button`) and provide dedicated `-` / `+` icon buttons or clean validated numeric inputs. |
| **9. Overcrowding the Header Space** | Stuffing 10 buttons, status chips, search bars, and titles into the top header causes cognitive overload. | **Clean, Breathable Header Architecture**: Maximum 1–2 primary action buttons, clean breadcrumb/title on the left, profile/settings tucked on the far right. Everything else belongs in contextual toolbars. |
| **10. Unnecessary Subtitles & Marketing Fluff** | "Manage and configure your advanced cluster nodes here..." insults the user and wastes critical vertical space. | **Terse, Technical Copy**: Omit redundant descriptions. Use clear titles, self-explanatory controls, and data badges. Let clean UI hierarchy do the talking. |
| **11. Cheap, Inconsistent, or Ugly SVGs** | Low-quality, inconsistent stroke weights, mismatched icon packs, or crude clipart degrade the entire UI. | **Bespoke Vector Standards with `better-icons`**: 24x24 viewBox, uniform 1.75px–2px stroke weight, round line joins and caps, consistent geometric language (Lucide, Tabler, Solar Linear). |
| **12. Default OS Scrollbars** | Bulky gray OS scrollbars destroy dark mode immersion and cause layout shifts. | **Custom Thin or Hidden Scrollbars**: Enforce 4–6px custom stone scrollbars (`var(--border-subtle)`) with rounded thumbs, or `scrollbar-width: thin`. Never show native OS scrollbars. |
| **13. Inconsistent Typography Across the App** | Mixing random fonts, unscaled font sizes, and arbitrary weights produces a chaotic, unpolished layout. | **Strict Dual-Typeface System**: Plus Jakarta Sans for UI/prose and JetBrains Mono for data/code. Enforce tokenized scale and weights across the entire codebase. |
| **14. Emojis in UI Labels, Buttons & Badges** | Emojis (🚀, 🔥, ✨, 🧠, ⚡, 🎉) look amateurish, render inconsistently across OS platforms, and distract from data. | **Zero Emojis in Functional UI**: Replace all emojis with clean, stroke-based monochrome SVG icons. |
| **15. Centered 600px Containers & Wasted Screen Real Estate** | Centering small cards in the middle of a 27" monitor wastes 80% of the display and forces unnecessary scrolling. | **Full Viewport Utilization (`100vw` / `100dvh`)**: Multi-column grids, split inspector panes, and high-density telemetry taking advantage of modern widescreen monitors. |
| **16. Monolithic UI That Fails to Transition Between PC & Phone** | Shrinking a desktop 3-column layout onto mobile creates an unreadable, squished disaster. | **Dedicated Layout Duality**: Desktop uses collapsible sidebars and multi-pane grids; mobile switches to bottom navigation bars, full-screen sheets, and touch-first stacked cards. |
| **17. Fragility at 125% Browser Zoom (Chrome Default)** | Layouts hardcoded in rigid pixels overflow, clip text, or break when users run Chrome at default 125% scaling. | **Fluid Rem & Flex Architecture**: All layouts must be built with `rem` units, flexible wrapping, and minimum dimensions that scale gracefully from 100% to 150% zoom without truncation. |
| **18. Mobile UX Traps (Overflowing Tabs, Tiny Unreadable UI)** | Horizontal screen blowout, tabs cutting off screen with no indicator, and tiny 10px tap targets ruin mobile usability. | **Mobile-First Touch Ergonomics**: Minimum 44x44px touch targets, 14px minimum body text on mobile, and swipeable tab strips with scroll-snap and subtle fade indicators. |

---

## 🎨 3. Color Architecture & Design Tokens (Matte, Zero Glow)

All projects share this unified CSS token architecture. Place these in `tokens.css` or the project's root styling entrypoint. Notice that **all glow tokens and neon shadows have been strictly eliminated**.

### 3.1 Dark Mode (Default Theme)
```css
[data-theme="dark"], :root {
  /* Surfaces - Flat, Instrument Stone */
  --bg-primary:         #151515;       /* Main canvas, deep obsidian */
  --bg-secondary:       #1b1b1b;       /* Sidebars, topbars, toolbars */
  --bg-surface:         #21201f;       /* Standard cards, panels, containers */
  --bg-surface-hover:   #282726;       /* Smooth hover state for interactive rows */
  --bg-elevated:        #2d2b29;       /* Modals, popovers, flyout menus */
  --bg-input:           #191817;       /* Inset input and field backgrounds */
  --bg-glass:           rgba(21, 21, 21, 0.94); /* Clean backdrop surface without bloom */

  /* Subtle Warm Stone Borders - Strictly 1px Solid, Zero Glow */
  --border-subtle:      #2b2826;       /* Card borders, panel dividers */
  --border-medium:      #3d3936;       /* Active card borders, hovered inputs */
  --border-strong:      #524d49;       /* Focused inputs, active buttons */
  --border-focus:       var(--brand-primary);

  /* Typography */
  --text-primary:       #ede9e3;       /* Crisp warm white, high contrast */
  --text-secondary:     #a8a29e;       /* Neutral muted text for descriptions */
  --text-muted:         #78716c;       /* Metadata, shortcuts, timestamps, labels */
  --text-inverse:       #151515;       /* Text on solid brand-colored buttons */

  /* Shadows - Tight, Diffuse Elevation (NO Colored Glows) */
  --shadow-sm:          0 1px 2px rgba(0, 0, 0, 0.35);
  --shadow-md:          0 4px 12px rgba(0, 0, 0, 0.45);
  --shadow-lg:          0 8px 24px rgba(0, 0, 0, 0.55);

  /* Radii - Crisp Geometric Structure */
  --radius-xs:          4px;
  --radius-sm:          6px;
  --radius-md:          8px;
  --radius-lg:          12px;
  --radius-xl:          16px;

  /* Motion & Duration Tokens */
  --duration-micro:     120ms;         /* Press states, icon crossfades */
  --duration-fast:      180ms;         /* Dropdowns, tooltips, tab switches */
  --duration-base:      260ms;         /* Modals, card expansions, toasts */
  --duration-slow:      340ms;         /* Mobile drawer slides, full page view transitions */

  /* Motion Easing Curves (Cubic-Bezier) */
  --ease-out:           cubic-bezier(0.16, 1, 0.3, 1);  /* Natural decelerating entrance */
  --ease-in:            cubic-bezier(0.4, 0, 1, 1);     /* Clean accelerating exit */
  --ease-in-out:        cubic-bezier(0.65, 0, 0.35, 1); /* Smooth symmetric transition */
  --ease-snappy:        cubic-bezier(0.2, 0, 0, 1);     /* Snappy micro-interaction curve */
}
```

### 3.2 Light Mode (Clean Warm Linen)
```css
[data-theme="light"] {
  --bg-primary:         #fcfcfb;       /* Warm alabaster canvas */
  --bg-secondary:       #f5f4f1;       /* Light stone sidebar and toolbars */
  --bg-surface:         #ffffff;       /* Pure white elevated cards */
  --bg-surface-hover:   #f9f8f6;       /* Soft warm hover */
  --bg-elevated:        #ffffff;       
  --bg-input:           #f7f6f3;       
  --bg-glass:           rgba(252, 252, 251, 0.95);

  --border-subtle:      #e7e5e1;       
  --border-medium:      #d6d3ce;       
  --border-strong:      #a8a29e;       

  --text-primary:       #1c1917;       
  --text-secondary:     #57534e;       
  --text-muted:         #8c857f;       
  --text-inverse:       #ffffff;       

  --shadow-sm:          0 1px 2px rgba(0, 0, 0, 0.05);
  --shadow-md:          0 4px 12px rgba(0, 0, 0, 0.08);
  --shadow-lg:          0 8px 24px rgba(0, 0, 0, 0.12);
}
```

### 3.3 Core Brand & Semantic Accents (Matte Tints, Zero Glow)
```css
:root {
  /* Signature Terracotta Brand Accent */
  --brand-primary:      #d97757;       /* Signature primary terracotta */
  --brand-hover:        #c86646;       
  --brand-active:       #b75536;       
  --brand-subtle:       rgba(217, 119, 87, 0.12); /* Subtle flat background tint */

  /* Status Colors (Semantic - Flat, Non-Glowing) */
  --color-success:        #10b981;     /* Healthy, connected, active, 200 OK */
  --color-success-bg:     rgba(16, 185, 129, 0.10);
  --color-success-border: rgba(16, 185, 129, 0.25);

  --color-warning:        #f59e0b;     /* Degraded, rate-limited, pending */
  --color-warning-bg:     rgba(245, 158, 11, 0.10);
  --color-warning-border: rgba(245, 158, 11, 0.25);

  --color-error:          #ef4444;     /* Disconnected, failed, exhausted, 500 */
  --color-error-bg:       rgba(239, 68, 68, 0.10);
  --color-error-border:   rgba(239, 68, 68, 0.25);

  --color-info:           #3b82f6;     /* Informational alerts, link references */
  --color-info-bg:        rgba(59, 130, 246, 0.10);
  --color-info-border:    rgba(59, 130, 246, 0.25);
}
```

### 3.4 Integration & Third-Party Service Accents (Reference Palette)
When displaying service status tags, integration chips, platform cards, or API source indicators, use these flat, matte brand accents:

| Service / Platform | Brand Color Hex | Flat Background Tint | Context / Ecosystem |
| :--- | :--- | :--- | :--- |
| **OpenAI** | `#10a37f` | `rgba(16, 163, 127, 0.10)` | AI / LLM APIs |
| **Anthropic** | `#d97706` | `rgba(217, 119, 6, 0.10)` | AI / LLM APIs |
| **Google Cloud** | `#1a73e8` | `rgba(26, 115, 232, 0.10)` | Cloud & Data Services |
| **Cloudflare** | `#f38020` | `rgba(243, 128, 32, 0.10)` | Edge & Serverless |
| **AWS** | `#ff9900` | `rgba(255, 153, 0, 0.10)` | Cloud Infrastructure |
| **GitHub** | `#24292f` | `rgba(255, 255, 255, 0.08)` | Git & CI/CD Pipelines |
| **Moonshot** | `#00c389` | `rgba(0, 195, 137, 0.10)` | Reasoning APIs |
| **DeepSeek** | `#0066ff` | `rgba(0, 102, 255, 0.10)` | Reasoning & Code Models |

---

## 📜 5. Universal Custom Scrollbar Specification

Default OS scrollbars are **completely banned**. Every scrollable container must apply this custom thin scrollbar rule:

```css
/* Universal Custom Scrollbar */
* {
  scrollbar-width: thin;
  scrollbar-color: var(--border-medium) transparent;
}

::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: var(--border-medium);
  border-radius: var(--radius-xs);
  transition: background var(--duration-fast) var(--ease-out);
}

::-webkit-scrollbar-thumb:hover {
  background: var(--border-strong);
}

/* Utility to intentionally hide scrollbars while preserving scrollability */
.no-scrollbar {
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.no-scrollbar::-webkit-scrollbar {
  display: none;
}
```

---

## 📐 6. Typography & Strict Discipline

Typography must be 100% consistent throughout the entire application. Rogue font sizes and weights are forbidden.

```css
--font-sans: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', Menlo, Monaco, Consolas, monospace;
```

### Font Allocation Rules:
- **`--font-sans`**: Used for all UI labels, navigation links, card titles, button copy, descriptions, and readable text.
- **`--font-mono`**: Used exclusively for technical data:
  - Identifiers, UUIDs, hashes, and cluster IDs
  - Hostnames, IP addresses, ports (e.g. `localhost:8080`, `443`)
  - Telemetry numbers, latencies, throughput (e.g. `14.2 ms`, `1.4 GB/s`)
  - Numeric balances, quotas, timestamps, ISO dates
  - API routes and JSON keys (`/api/v1/status`)

### Strict Type Scale
| Token | REM | Pixels | Weight | Typical Usage |
| :--- | :--- | :--- | :--- | :--- |
| `--font-size-xs` | `0.75rem` | 12px | 500 / 600 | Badges, tags, status chips, table column headers |
| `--font-size-sm` | `0.875rem` | 14px | 500 / 600 | Buttons, input labels, form hints, table rows |
| `--font-size-base` | `0.9375rem` | 15px | 400 / 500 | Body copy, card descriptions, readable logs |
| `--font-size-md` | `1.0625rem` | 17px | 600 | Card titles, modal subsection headers |
| `--font-size-lg` | `1.25rem` | 20px | 600 | Primary section headers, modal titles |
| `--font-size-xl` | `1.5rem` | 24px | 700 | Main dashboard metrics, page titles |
| `--font-size-2xl` | `1.875rem` | 30px | 700 | Hero metrics, standalone landing titles |

---

## 🔘 7. Component Blueprint: Buttons & Interactive Elements

Buttons adhere to strict geometric structure: **No pill shapes (`rounded-full`), no nested boxes, and no contrasting hover lines.**

```css
/* Base Button Geometry */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px 14px;
  font-size: var(--font-size-sm);
  font-weight: 600;
  font-family: var(--font-sans);
  border-radius: var(--radius-md); /* 8px - NEVER rounded-full */
  border: 1px solid transparent;
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
  transition: background var(--duration-micro) var(--ease-snappy), 
              border-color var(--duration-micro) var(--ease-snappy), 
              transform var(--duration-micro) var(--ease-snappy);
  -webkit-tap-highlight-color: transparent !important;
  outline: none;
}

/* Micro-Interaction Click Compression (Tactile, No Spring Jitter) */
.btn:active {
  transform: scale(0.98);
}

/* 1. Primary Action Button (Solid Terracotta) */
.btn-primary {
  background-color: var(--brand-primary);
  color: #ffffff;
  border-color: var(--brand-primary);
}
.btn-primary:hover {
  background-color: var(--brand-hover);
  border-color: var(--brand-hover);
}

/* 2. Secondary Button (Surface with Subtle Border - NO Contrasting Hover Line) */
.btn-secondary {
  background-color: var(--bg-surface);
  color: var(--text-primary);
  border-color: var(--border-subtle);
}
.btn-secondary:hover {
  background-color: var(--bg-surface-hover);
  border-color: var(--border-medium); /* Soft tone shift, never a bright harsh line */
}

/* 3. Ghost / Flat Button */
.btn-ghost {
  background-color: transparent;
  color: var(--text-secondary);
  border-color: transparent;
}
.btn-ghost:hover {
  background-color: var(--bg-surface-hover);
  color: var(--text-primary);
}

/* 4. Danger Button */
.btn-danger {
  background-color: var(--color-error-bg);
  color: var(--color-error);
  border-color: var(--color-error-border);
}
.btn-danger:hover {
  background-color: var(--color-error);
  color: #ffffff;
}

/* 5. Compact Icon Button (44px min tap area on mobile, 36px on desktop) */
.btn-icon {
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: var(--radius-sm);
}
@media (max-width: 768px) {
  .btn-icon {
    width: 44px;
    height: 44px;
  }
}
```

---

## 🎛️ 8. Component Blueprint: Custom Dropdown System

Native `<select>` elements are strictly prohibited. The custom popover component guarantees identical rendering, search filtering, and keyboard accessibility.

```
┌───────────────────────────────────────────────┐
│  Selected: Production Edge Node (us-east)  ▼  │  <- .custom-select-trigger
└───────────────────────────────────────────────┘
        │
        ▼ (on click)
┌───────────────────────────────────────────────┐
│ 🔍 [ Filter options...                      ] │  <- .select-search-input
├───────────────────────────────────────────────┤
│ Production Edge Node (us-east)            ✓   │  <- .select-option.selected
│ Failover Backup (eu-west)                     │  <- .select-option
│ Staging Canary Cluster                        │  <- .select-option
│ Local Development Mock                        │  <- .select-option
└───────────────────────────────────────────────┘  <- .custom-select-popover
```

### HTML Structure
```html
<div class="custom-select-wrapper" id="cluster-select">
  <div class="custom-select-trigger" tabindex="0">
    <span class="trigger-label">Select Option</span>
    <svg class="chevron-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
  </div>
  <div class="custom-select-popover">
    <div class="select-search-box">
      <input type="text" class="select-search-input" placeholder="Filter options..." />
    </div>
    <div class="select-options-list">
      <!-- Populated with .select-option items -->
    </div>
  </div>
</div>
```

---

## 🔢 9. Component Blueprint: Custom Numeric Input (No Default Spinners)

Default browser stepping stone buttons (`<input type="number">` spinner arrows) are ugly and inconsistent. We suppress them and provide structured, clean numeric inputs with optional inline steppers:

```css
/* Suppress default browser stepping stone arrows */
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button {
  -webkit-appearance: none;
  margin: 0;
}
input[type="number"] {
  -moz-appearance: textfield;
}

/* Custom Number Input Stepper Wrapper */
.number-input-group {
  display: inline-flex;
  align-items: center;
  background-color: var(--bg-input);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  overflow: hidden;
  height: 38px;
}

.number-input-group:focus-within {
  border-color: var(--brand-primary);
}

.number-stepper-btn {
  width: 34px;
  height: 100%;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background var(--duration-fast) var(--ease-out);
}
.number-stepper-btn:hover {
  background: var(--bg-surface-hover);
  color: var(--text-primary);
}

.number-stepper-input {
  width: 60px;
  height: 100%;
  background: transparent;
  border: none;
  text-align: center;
  font-family: var(--font-mono);
  font-size: var(--font-size-sm);
  color: var(--text-primary);
  outline: none;
}
```

---

## 🔔 10. Component Blueprint: Toast Notifications & Confirmation Modals

Native `alert()`, `confirm()`, and `prompt()` calls are **strictly forbidden**. All system feedback flows through the custom toast notification system.

### HTML Container
Placed once at the root of the app:
```html
<div id="toast-container"></div>
```

### Toast Styling (Matte, No Glow)
```css
#toast-container {
  position: fixed;
  top: 20px;
  right: 24px;
  z-index: 99999;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast {
  pointer-events: auto;
  background-color: var(--bg-surface);
  border: 1px solid var(--border-medium);
  border-radius: var(--radius-md);
  padding: 12px 18px;
  box-shadow: var(--shadow-lg);
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 280px;
  max-width: 420px;
  animation: toastIn var(--duration-fast) var(--ease-out) forwards;
  transition: all var(--duration-fast) var(--ease-out);
}

.toast.toast-success { border-left: 4px solid var(--color-success); }
.toast.toast-warning { border-left: 4px solid var(--color-warning); }
.toast.toast-error   { border-left: 4px solid var(--color-error); }
.toast.toast-info    { border-left: 4px solid var(--brand-primary); }

@media (max-width: 768px) {
  #toast-container {
    top: auto;
    bottom: 24px;
    left: 16px;
    right: 16px;
  }
  .toast {
    max-width: 100%;
  }
}
```

---

## ⚡ 11. Component Blueprint: Motion Graphic Loaders (No Generic Spinners)

Generic circular spinning wheels convey no real progress and look lazy. Applications must use **thematic motion graphic loaders** tailored to task modality:

### 11.1 Heavy Compute & Reasoning Loader (`.thinking-loader`)
- Used for complex background jobs, multi-step agent reasoning, code compilation, and deep analysis.
- **Motion**: Dual-concentric orbital rings pulsing with crisp geometric nodes and an elapsed duration counter.
- Accompanied by a collapsible thought/log tray (`.trace-box` or `.reasoning-box`) displaying live output tokens in dimmed monospace font.

### 11.2 Media & Canvas Render Loader (`.media-render-loader`)
- Used for image rendering, visual generation, SVG compile, and canvas operations.
- **Motion**: Subtle glowing dot matrix shimmer across an aspect-ratio locked frame (1:1, 16:9, etc.).

### 11.3 Telemetry & Synchronous Pulse Loader (`.data-pulse-loader`)
- Used for quick inline data fetches, polling checks, and API pings.
- **Motion**: Clean warm terracotta pulse bar with high-speed gradient sweep (never spinning discs).

---

## 🏷️ 12. Component Blueprint: Status Badges & Chips (No Status Orbs)

Pulsing status orbs or glowing circular dots are banned. Use clean, flat, rectangular badges with subtle tinted backgrounds and crisp monospace text:

```css
/* Status Badge - Flat, Instrument Grade (NO Pulsing Orbs) */
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  font-family: var(--font-mono);
  font-size: var(--font-size-xs);
  font-weight: 600;
  border-radius: var(--radius-xs); /* 4px geometric radius */
  border: 1px solid transparent;
  user-select: none;
  line-height: 1.2;
}

/* Success / Active */
.status-badge.status-active {
  background-color: var(--color-success-bg);
  border-color: var(--color-success-border);
  color: var(--color-success);
}

/* Warning / Degraded */
.status-badge.status-warning {
  background-color: var(--color-warning-bg);
  border-color: var(--color-warning-border);
  color: var(--color-warning);
}

/* Error / Offline */
.status-badge.status-error {
  background-color: var(--color-error-bg);
  border-color: var(--color-error-border);
  color: var(--color-error);
}

/* Informational / Neutral */
.status-badge.status-neutral {
  background-color: var(--bg-surface-hover);
  border-color: var(--border-subtle);
  color: var(--text-secondary);
}
```

---

## 📐 13. Layout System: 100dvh Lock, Full Screen Width & Anti-Nesting Rules

### 13.1 The Anti-Nesting Rule (Single-Layer Surfaces)
Never place a card inside a card, or enclose buttons in separate bordered boxes inside a card:
- **Rule**: If a container has a border and background (`--bg-surface`), its children must not create additional bordered cards inside it.
- **Organization**: Use whitespace (`gap: 16px`), subtle 1px divider lines (`border-bottom: 1px solid var(--border-subtle)`), or flat background shifts (`--bg-input`).
- **Buttons**: Action buttons sit directly inside the card header or card footer, never wrapped inside an extra bordered sub-card.

### 13.2 Clean Header Architecture (No Overcrowding)
- **Primary Header Rule**: The top header must never contain more than 1–2 primary action buttons.
- **Left Side**: App/Project logo, title, and optional single-level breadcrumb.
- **Center**: Empty or clean global search bar.
- **Right Side**: Status chip, secondary icon buttons (Settings, Theme toggle), and user profile.
- **Contextual Actions**: Batch actions, filters, and local triggers belong inside the specific page/card toolbar, not dumped into the global header.

### 13.3 Full Screen Width & 100dvh Lock
Applications must utilize 100% of the display width and lock the master viewport:

```css
/* Master Viewport Lock */
html, body {
  height: 100%;
  width: 100%;
  overflow: hidden;
  background-color: var(--bg-primary);
  color: var(--text-primary);
}

#app {
  display: flex;
  height: 100dvh;
  width: 100vw;
  overflow: hidden;
}

/* Main Content Area */
.main-content {
  flex: 1;
  height: 100%;
  overflow-y: auto;
  padding: 24px 32px;
}

/* Full Width High-Density Grid */
.catalog-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 18px;
  width: 100%;
}
```

---

## 📱 14. Responsive Architecture: PC vs. Phone & Zoom Scaling

A common failure in UI engineering is shrinking a desktop layout onto a mobile screen. The application must maintain **architectural layout duality**:

### 14.1 PC vs. Phone Duality
- **Desktop (PC)**:
  - Collapsible left sidebar (`260px`).
  - High-density multi-column grids (`repeat(auto-fill, minmax(360px, 1fr))`).
  - Split-pane workbench views with inspector on the right.
- **Mobile (Phone - `< 768px`)**:
  - Sidebar disappears from desktop layout. Replaced by a **bottom navigation bar** (4–5 tabs max) or a smooth slide-out drawer triggered by a menu button.
  - Multi-column grids collapse into **single-column vertical stacks**.
  - Split inspector views convert to full-screen swipeable sheets or stacked cards.
  - Action toolbars become sticky bottom action bars for thumb reachability.

### 14.2 Resiliency to Browser Zoom (125% Default Scaling)
Chrome and Windows frequently run at default 125% display scaling. Interfaces must never clip or break under zoom:
1. **Always Use `rem` for Layout & Typography**: Base font sizes on `rem` so the entire layout scales proportionally when the user zooms.
2. **Never Hardcode Rigid Pixel Heights on Content Containers**: Use `min-height` instead of fixed `height`. Containers must expand vertically when text scales up.
3. **Use Flexible Wrap (`flex-wrap: wrap`) on Toolbars**: Header and card action bars must wrap gracefully rather than pushing buttons off the right edge of the screen.

### 14.3 Mobile Ergonomics & Overflow Prevention
1. **Zero Horizontal Scroll Blowout**:
   ```css
   /* Prevent accidental horizontal screen blowout on mobile */
   body, .main-content, #app {
     max-width: 100vw;
     overflow-x: hidden;
   }
   ```
2. **Scrollable Tabs with Fade Mask**:
   When navigation tabs exceed the screen width on phone, they must scroll horizontally with smooth scroll-snap and a subtle edge fade:
   ```css
   .mobile-tab-bar {
     display: flex;
     overflow-x: auto;
     white-space: nowrap;
     gap: 8px;
     padding: 8px 16px;
     scroll-snap-type: x mandatory;
     scrollbar-width: none;
     -webkit-overflow-scrolling: touch;
     mask-image: linear-gradient(to right, black 90%, transparent 100%);
   }
   .mobile-tab-item {
     scroll-snap-align: start;
     flex-shrink: 0;
   }
   ```
3. **Readable Font Sizes & Touch Targets on Mobile**:
   - Minimum body font size on phone: `14px` (`0.875rem`). Never render 10px or 11px body text.
   - Minimum interactive tap target: `44px x 44px` (with at least 8px spacing between tap targets).

---

## 🧩 15. SVG Iconography & Better-Icons Universal Workflow

To eliminate ugly, mismatched, or crude vectors, all icons across all projects are managed through the standardized **`better-icons`** workflow (Iconify 200+ libraries).

### 15.1 Universal Icon Retrieval CLI
Use the global `better-icons` CLI to search and output clean SVGs:

```bash
# Search for icons across clean, modern icon families (Tabler, Lucide, Solar)
better-icons search settings --limit 10
better-icons search terminal --limit 5

# Get icon SVG directly to stdout or pipe to asset directory
better-icons get tabler:settings > assets/icons/settings.svg
better-icons get lucide:server > assets/icons/server.svg
better-icons get solar:shield-check-linear > assets/icons/shield.svg
```

### 15.2 Vector Geometry Rules
1. **Pure Vectors Only**: All icons must be pure SVG. External icon fonts (FontAwesome, Material Icons ligatures) are strictly forbidden to eliminate Flash of Unstyled Text (FOUT) and layout shifts.
2. **Standard 24x24 Optical Geometry**:
   ```html
   <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
     <!-- Pure path coordinates -->
   </svg>
   ```
3. **Consistency Invariants**:
   - Uniform stroke width (`1.75px` to `2px`) across all icons on any given screen.
   - Do not mix solid filled icons with outlined icons in the same toolbar.
   - Always inherit parent color via `currentColor`.

---

## 💎 16. Design Engineering Polish & Interface Feel

Principles adapted from the `make-interfaces-feel-better` engineering standard to make interfaces feel instrument-grade and tactile:

### 16.1 Font Smoothing & Tabular Numerals
```css
/* Mandatory Root Font Smoothing */
html, body {
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}

/* Tabular Numerals on All Telemetry, Timers, Counters & Data Tables */
.tabular-nums, .stat-value, .latency-badge, .timer, table td {
  font-variant-numeric: tabular-nums;
  font-feature-settings: "tnum" 1;
}
```
*Why*: Tabular numerals ensure that updating numbers (e.g. latency shifting from `89ms` to `102ms`, or a count decrementing) do not shift adjacent elements horizontally.

### 16.2 Concentric Border Radius
When nesting elements with borders and padding, enforce the geometric rule:
$$\text{Outer Radius} = \text{Inner Radius} + \text{Padding}$$
- Example: If an outer panel has `12px` border-radius and `8px` internal padding, any inner container must have `4px` border-radius (`12 - 8 = 4px`). Mismatched nested radii create a cheap, broken appearance.

### 16.3 Optical Over Geometric Alignment
Geometric center often appears optically uncentered:
- **Buttons with Icons**: Shift the icon 1px downward or horizontally to align optically with the font's x-height.
- **Play Buttons**: Triangle play icons must be shifted `+1px` to the right to balance visual center-of-mass.

### 16.4 Hairline Structure over Blunt Borders
On high-DPI displays, blunt opaque borders look heavy. Prefer subtle translucent stone hairlines:
```css
/* Hairline Structure */
--border-subtle: rgba(255, 255, 255, 0.08); /* Dark mode */
/* Light mode */
--border-subtle: rgba(0, 0, 0, 0.08);
```

---

## 🎬 17. GSAP Animation Architecture & 60fps GPU Standards

For non-trivial UI transitions, staged timelines, scroll-driven interactions, and interactive widgets, **GSAP (GreenSock)** is the official workspace animation engine (`gsap-core`, `gsap-timeline`, `gsap-scrolltrigger`, `gsap-react`).

### 17.1 The GPU-Only Transform Rule
GSAP tweens must **strictly animate GPU-composited properties**:
- ✅ Allowed: `x`, `y`, `scale`, `rotation`, `opacity`, `autoAlpha`
- ❌ Forbidden: `top`, `left`, `right`, `bottom`, `width`, `height`, `margin`, `padding`
Animating layout properties triggers CPU layout recalculations and causes jank on mobile devices.

### 17.2 Coordinated Timeline Sequencing (`gsap.timeline()`)
When opening a modal, tray, or workbench panel, choreograph the entrance hierarchically:

```javascript
import { gsap } from "gsap";

// Coordinated Modal Entrance Timeline
const tl = gsap.timeline({ defaults: { ease: "power2.out", duration: 0.24 } });

tl.fromTo(".modal-backdrop", { opacity: 0 }, { opacity: 1, duration: 0.18 })
  .fromTo(".modal-card", 
    { y: 16, opacity: 0, scale: 0.98 }, 
    { y: 0, opacity: 1, scale: 1 }, 
    "-=0.1"
  )
  .fromTo(".modal-field", 
    { y: 8, opacity: 0 }, 
    { y: 0, opacity: 1, stagger: 0.04 }, 
    "-=0.14"
  );
```

### 17.3 Responsive & Accessibility MatchMedia (`gsap.matchMedia()`)
Animations must adapt to viewport size and respect user motion preferences:

```javascript
const mm = gsap.matchMedia();

mm.add({
  // Desktop layout animation
  isDesktop: "(min-width: 768px)",
  // Mobile layout animation
  isMobile: "(max-width: 767px)",
  // User prefers reduced motion
  reduceMotion: "(prefers-reduced-motion: reduce)"
}, (context) => {
  const { isDesktop, isMobile, reduceMotion } = context.conditions;

  if (reduceMotion) {
    // Instant snap without motion
    gsap.set(".panel", { opacity: 1, x: 0 });
    return;
  }

  gsap.from(".panel", {
    x: isDesktop ? 40 : 0,
    y: isMobile ? 40 : 0,
    opacity: 0,
    duration: 0.28,
    ease: "power2.out"
  });
});
```

### 17.4 Memory Lifecycle & Cleanup
In modern component frameworks (React, Vue, vanilla single-page apps), always wrap animations in a context and clean them up on unmount:
```javascript
// Clean teardown prevents memory leaks
const ctx = gsap.context(() => {
  // animations here
}, containerRef);

// On destroy:
ctx.revert();
```

---

## 🏃 18. Motion Design System & Micro-Interactions

Based on the `motion-design` engineering standard, animation must serve functional clarity and tactile reassurance.

### 18.1 Duration Rules by Component Scale
| Component Scale | Duration | Example Use Cases |
| :--- | :--- | :--- |
| **Micro (Instant Feedback)** | `100ms – 140ms` | Button active presses, checkbox checks, icon crossfades |
| **Fast (Small Elements)** | `180ms – 220ms` | Dropdown flyouts, tooltip reveals, tab underline indicators |
| **Base (Medium Surfaces)** | `240ms – 280ms` | Card expansions, toast arrivals, modal reveals |
| **Slow (Large Panels)** | `320ms – 360ms` | Full-screen drawers, mobile navigation transitions |

### 18.2 Disney & UI Motion Principles Applied
1. **Decelerate on Entrance, Accelerate on Exit**:
   - Entrances use `cubic-bezier(0.16, 1, 0.3, 1)` (arrives with momentum, cushions into place).
   - Exits use `cubic-bezier(0.4, 0, 1, 1)` (leaves crisply without lingering).
2. **The 1/3 Motion Distance Rule**:
   - Never slide a modal from off-screen (100% distance). Slide from `12px` to `16px` with opacity. Excessive travel distance creates motion sickness and feels sluggish.
3. **Motion Restraint**:
   - Never animate elements when the user is performing rapid repetitive actions (e.g. typing, rapid scrolling, repeated clicks).
4. **Lottie Micro-Animation Guidelines**:
   - Lottie vector animations are permitted **exclusively** for confirmed state changes (e.g. completion checkmarks, empty state illustrations).
   - Render strictly in monochrome stone/terracotta tokens.
   - Absolutely zero looping party poppers, celebratory confetti, or glowing marketing animations.

---

## 🧊 19. Three.js, WebGL & Canvas Standards

For 3D data visualizations, topology graphs, and WebGL viewports, projects utilize the `threejs-skills` standard and the local sandbox at [threejs-playground/](file:///home/insomniac/Desktop/Janitor/threejs-playground/):

### 19.1 Instrument Aesthetics in 3D
- 3D viewports must integrate seamlessly into the **Warm Stone & Terracotta** aesthetic.
- Canvas background clear color must match the app canvas:
  ```javascript
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setClearColor(0x151515, 1); // Dark obsidian
  ```
- Materials should emphasize matte physical properties (`roughness: 0.8`, `metalness: 0.1`) rather than hyper-reflective glossy plastics.
- **Zero Neon Bloom**: Avoid post-processing bloom shaders that create gaudy colored halos.

### 19.2 Retina DPR Clamping
High-DPI displays (Apple Retina, 4K mobile displays) will overheat the GPU if rendered at full 3x or 4x buffer resolution:
```javascript
// Clamp pixel ratio to maximum 2x
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.setSize(container.clientWidth, container.clientHeight);
```

### 19.3 Battery-Saving Visibility Throttling
Never run an active WebGL `requestAnimationFrame` loop when the canvas is off-screen. Use an `IntersectionObserver`:
```javascript
let isVisible = true;
const observer = new IntersectionObserver(([entry]) => {
  isVisible = entry.isIntersecting;
  if (isVisible) requestAnimationFrame(render);
});
observer.observe(renderer.domElement);

function render() {
  if (!isVisible) return;
  renderer.render(scene, camera);
  requestAnimationFrame(render);
}
```

### 19.4 Strict WebGL Memory Disposal
To prevent GPU memory leaks when navigating between panels or tearing down tabs, traverse and dispose of all resources:
```javascript
function dispose3DScene(scene, renderer) {
  scene.traverse((obj) => {
    if (obj.geometry) obj.geometry.dispose();
    if (obj.material) {
      if (Array.isArray(obj.material)) {
        obj.material.forEach((m) => m.dispose());
      } else {
        obj.material.dispose();
      }
    }
  });
  renderer.dispose();
}
```

---

## 📝 20. Content & Copywriting Discipline

1. **Zero Emojis in Functional UI**: Emojis are banned across all titles, badges, button copy, and status cards. Use clean SVG icons.
2. **Terse Technical Precision**:
   - ❌ *"Welcome to the node orchestrator. Here you can configure all your clusters."*
   - ✅ *"Clusters"* (with badge `[3 ACTIVE]`).
3. **No Redundant Subtitle Text**: If a section title is "Security Settings", do not add a subtitle saying "Manage your security settings". Reserve secondary text strictly for actionable hints, validation errors, or critical warnings.

---

## ✅ 21. Master UI Review & Audit Checklist (Pre-Ship Verification)

Before approving any UI code, frontend PR, or component implementation, verify against this 21-point checklist:

- [ ] **1. Zero Status Orbs**: Are all statuses represented by structured text badges or flat chips rather than pulsing glowing dots?
- [ ] **2. Zero Glow Effects**: Are all box-shadows tight and neutral? (Zero neon outlines, glowing borders, or text blooms).
- [ ] **3. No Nested Cards / Box-in-a-Box**: Are all containers single-layer surfaces with sectioning achieved via whitespace or dividers?
- [ ] **4. No Contrasting Hover Lines**: Do interactive elements shift surface background smoothly on hover without jumping outline borders?
- [ ] **5. No Pill Buttons**: Are all button border-radii set to 6px or 8px? (Zero instances of `border-radius: 9999px` or `rounded-full` on buttons).
- [ ] **6. No Native Selects**: Are all dropdowns and selectors using the custom popover component?
- [ ] **7. No Native Alerts**: Is every notification dispatched through `showToast(msg, type)`?
- [ ] **8. No Number Spinners**: Are default `<input type="number">` stepper arrows hidden via CSS?
- [ ] **9. Clean Header**: Does the top header have maximum 1–2 primary action buttons with zero visual overcrowding?
- [ ] **10. Zero Marketing Fluff**: Are all unnecessary descriptions, boilerplate subtitles, and redundant helper text removed?
- [ ] **11. Better-Icons Verified**: Are all icons sourced cleanly via `better-icons` with matching 24x24 viewBox, stroke widths, and rounded caps?
- [ ] **12. Custom Thin Scrollbars**: Are all scrollable containers using custom 6px stone scrollbars or `scrollbar-width: thin`?
- [ ] **13. Strict Typography Discipline**: Are only Plus Jakarta Sans and JetBrains Mono used, following the strict token scale?
- [ ] **14. Font Smoothing & Tabular Numerals**: Is `-webkit-font-smoothing: antialiased` set on root and `tabular-nums` used on all numeric counters/tables?
- [ ] **15. GPU-Only Animations**: Do all GSAP/CSS animations strictly animate `x`, `y`, `scale`, and `opacity` (never layout properties)?
- [ ] **16. Motion Duration Restraint**: Are durations constrained to 120ms (micro), 180ms (fast), 260ms (base), and 340ms (slow)?
- [ ] **17. Zero Emojis**: Are all emojis eliminated from titles, buttons, badges, and tabs?
- [ ] **18. Full Viewport Utilization**: Does the desktop layout utilize the full `100vw` without centered 600px wrapper constraints?
- [ ] **19. Seamless PC to Phone Duality**: Does the layout properly transform into a bottom nav / drawer and single-column stack on mobile?
- [ ] **20. 125% Zoom Resilient**: Does the layout scale cleanly without clipping or text truncation when Chrome is at 125% zoom?
- [ ] **21. Three.js / WebGL Clamped**: If 3D is used, are pixel ratios clamped to max 2x, offscreen loops paused, and resources disposed?
