# OneFlowAI — Frontend

Production-grade frontend foundation for the OneFlowAI multi-channel, AI-powered
conversation platform. This is the real architecture the SaaS app expands into —
**not** a throwaway prototype.

> Backend integration is intentionally **not** wired up in this sprint. All
> content is served from a typed **mock-data layer** and is ready to be swapped
> for real API calls.

## Tech Stack

| Concern        | Choice                                   |
| -------------- | ---------------------------------------- |
| Framework      | Next.js 15 (App Router)                  |
| Language       | TypeScript (strict)                      |
| Styling        | TailwindCSS + CSS variables              |
| UI primitives  | shadcn/ui-style (Button, Card, Input, …) |
| Animation      | Framer Motion                            |
| Icons          | lucide-react                             |
| Theming        | next-themes (light / dark / system)      |
| Forms          | React Hook Form + Zod                    |
| Data           | TanStack Query + Axios (mock service)    |

## Theme

- **Primary:** Cyan `#00D5FF` · **Secondary:** White · **Dark:** `#050816`
- Light / Dark / System themes with a smooth, flash-free switch
  (`next-themes` sets the class before paint; body colors transition softly).
- All colors are CSS variables in `app/globals.css`, consumed via Tailwind
  tokens (`bg-background`, `text-brand`, …).

## Getting Started

```bash
# 1. Install dependencies (Node.js 18.18+ or 20+ recommended)
npm install

# 2. (optional) configure the future API base URL
cp .env.example .env.local

# 3. Run the dev server
npm run dev
# open http://localhost:3000
```

### Scripts

| Command             | Description                          |
| ------------------- | ------------------------------------ |
| `npm run dev`       | Start the dev server                 |
| `npm run build`     | Production build                     |
| `npm run start`     | Serve the production build           |
| `npm run lint`      | ESLint (next/core-web-vitals)        |
| `npm run typecheck` | TypeScript strict type-check         |

> Note: `npm run build` fetches the Inter font from Google Fonts at build time
> (standard `next/font` behavior), so build requires network access.

## Routes

| Path         | Description                                   |
| ------------ | --------------------------------------------- |
| `/`          | Landing page (all sections)                   |
| `/features`  | Features overview                             |
| `/pricing`   | Pricing + FAQ                                 |
| `/docs`      | Documentation shell (mock content)            |
| `/login`     | Login form (React Hook Form + Zod, mock)      |
| `/dashboard` | Dashboard preview (sidebar, KPIs, charts)     |

## Project Structure

```
app/            # App Router routes + root layout + globals.css
components/
  ui/           # shadcn-style primitives (button, card, badge, input, label)
  shared/       # cross-cutting (theme-toggle, animated-counter, glow-card, …)
  layout/       # navbar, mobile-nav, footer, site-shell
  landing/      # landing sections (hero, features, statistics, faq, …)
  dashboard/    # sidebar, stat-card, charts, server-health, overview
providers/      # theme + TanStack Query providers
hooks/          # useMounted, useMediaQuery, useScrolled, useDashboardOverview
services/       # axios client + mock dashboard service
types/          # shared domain types
lib/            # utils (cn), constants, animation presets, mock-data
utils/          # formatting helpers
assets/         # source design assets
public/         # static files
```

## Component Hierarchy

```
RootLayout (AppProviders: ThemeProvider + QueryProvider)
├── Landing "/"  → SiteShell
│   ├── Navbar (Logo, nav underline, ThemeToggle, MobileNav)
│   ├── Hero (AINetworkBackground, floating metric cards)
│   ├── Features (GlowCard × n)
│   ├── HowItWorks · DashboardPreview · Statistics (AnimatedCounter)
│   ├── AIFlow · HotelIntegration (FlowDiagram)
│   ├── PricingPreview · Faq · Cta
│   └── Footer
└── Dashboard "/dashboard"
    ├── DashboardSidebar · DashboardHeader · MobileBottomNav
    └── DashboardOverview (StatCard, MiniChart, ServerHealth)  ← TanStack Query
```

## Theme System

- `providers/theme-provider.tsx` wraps `next-themes` with
  `attribute="class"`, `defaultTheme="system"`, `enableSystem`.
- `app/globals.css` defines light tokens in `:root` and dark tokens in `.dark`.
- `components/shared/theme-toggle.tsx` offers Light / System / Dark and persists
  the choice (handled by `next-themes`).

## Animation System

- Reusable Framer Motion variants live in `lib/animations.ts`
  (`fadeUp`, `scaleIn`, `staggerContainer`, `floatCard`, spring transitions).
- `components/shared/reveal.tsx` and `section-heading.tsx` apply scroll-reveal.
- `AnimatedCounter` counts up on scroll; `AINetworkBackground` is an interactive
  canvas (nodes, lines, glow, mouse attraction). All respect
  `prefers-reduced-motion`.

## Mock Data Layer

- `lib/mock-data.ts` holds all landing + dashboard content (typed via `types/`).
- `services/dashboard.service.ts` simulates latency and returns mock data.
- `hooks/use-dashboard-overview.ts` consumes it through TanStack Query.
- To connect the backend later: replace the service bodies with `apiClient`
  calls (`services/api-client.ts`) — components and hooks stay unchanged.

## Notes

- Strict TypeScript, ESLint clean, no inline styles for layout, componentized
  sections, dependency-free SVG charts (no charting lib needed).
- Fully responsive with a touch-friendly mobile drawer and dashboard bottom nav.

---

# Frontend Sprint 2 — Application (Auth + Dashboard)

The real OneFlowAI application: authentication, protected routing, a reusable
dashboard shell, and live backend integration. **No mock authentication.**

## Backend Integration

The app talks to the existing FastAPI backend. To avoid CORS in the browser,
Next.js **proxies** `/api/v1/*` to the backend (see `next.config.mjs`), so the
Axios client stays same-origin.

```bash
# .env.local
BACKEND_URL=http://localhost:8000        # your running FastAPI backend
```

Typed service layer (no `fetch` inside components):

```
services/
  api/         client.ts (Axios + interceptors), errors.ts (ApiError)
  auth/        auth.service.ts, token.ts (cookie storage)
  workspace/   workspace.service.ts
  customer/    customer.service.ts
  conversation/conversation.service.ts
```

TanStack Query hooks live in `hooks/api/*`; query keys in `lib/query-keys.ts`.

## Authentication

- **Login / Register / Logout / Remember me / Forgot-password UI**
  (`/login`, `/register`, `/forgot-password`).
- Forms use **React Hook Form + Zod**; backend errors are surfaced inline.
- JWT is stored in a cookie so middleware can guard routes and Axios can attach
  `Authorization: Bearer …`. Remember-me controls cookie persistence.
- A response interceptor clears the token on `401`; `AuthProvider` validates it
  via `/auth/me`.

## Protected Routing

- `middleware.ts` redirects guests away from `/dashboard/*` to `/login`, and
  redirects logged-in users away from `/login` and `/register` to `/dashboard`.
- `AuthGuard` (client) re-validates the token via `/auth/me`.

## Dashboard Shell (reusable)

`components/dashboard/shell/*` — collapsible sidebar (with responsive drawer),
top navigation (search placeholder, notifications, theme toggle, profile menu,
workspace selector), and breadcrumbs. Used by `app/dashboard/layout.tsx` for all
dashboard pages.

## Dashboard Overview (live data)

`/dashboard` shows the workspace name/slug, current user, customer count,
conversation count, and latest customers/conversations — all from the backend.
Loading shows skeletons; missing data shows elegant empty states.

## Error Handling

- Global toast (sonner) for query failures (`403 / 404 / 500 / network`); `401`
  is handled by the auth flow.
- Friendly `app/not-found.tsx` (404) and `app/error.tsx` (500) pages.

---

# Testing Instructions

### 1. Start the backend (FastAPI)

```bash
# in the backend project
uv run uvicorn app.main:app --reload      # serves http://localhost:8000
# ensure Postgres/Redis/Qdrant are up (docker compose up -d)
```

### 2. Start the frontend

```bash
npm install
echo "BACKEND_URL=http://localhost:8000" > .env.local
npm run dev                                # http://localhost:3000
```

### 3. Manual test flow

1. Visit `/dashboard` while logged out → redirected to `/login`.
2. Go to `/register`, create an account → redirected to `/dashboard` with your
   real workspace name/slug and user email.
3. Reload `/login` while logged in → redirected to `/dashboard`.
4. Overview shows Customer/Conversation counts (0 with empty states on a fresh
   account) — create data via the backend API and refresh to see it appear.
5. Toggle "Remember me" on login and reload — the session persists.
6. Use the profile menu → **Log out** → redirected to `/login`; `/dashboard`
   is protected again.
7. Collapse the sidebar, resize to mobile (drawer), toggle the theme.

### 4. Quality checks

```bash
npm run lint        # ESLint
npm run build       # production build + type-check (requires network for fonts)
```

> Note: the login/register forms surface backend validation errors (e.g. a
> duplicate email returns `409` → "A user with this email already exists").

---

# Localization (i18n)

The app uses **next-intl** with the App Router. The UI ships in **Thai** (the
MVP's default), while **all code stays English**. Every user-visible string comes
from a centralized dictionary — no hardcoded copy inside components.

## Architecture

```
i18n/
  config.ts     locales (["th","en"]) + defaultLocale ("th") + cookie name
  request.ts    resolves the locale from the NEXT_LOCALE cookie, loads messages
  actions.ts    setLocale() server action (for a future language switcher)
messages/
  th.json       Thai dictionary (active default)
  en.json       English dictionary (future / fallback)
```

- The root layout wraps the app in `NextIntlClientProvider`, so both server
  components (`getTranslations`) and client components (`useTranslations`) can
  translate.
- Data files (`lib/mock-data.ts`, `lib/premium-data.ts`, `lib/constants.ts`,
  `lib/dashboard-nav.ts`) hold only **ids/keys + icons**; display text lives in
  the dictionaries keyed by those ids. Technical proper nouns (CPU, PostgreSQL,
  LINE…) intentionally stay untranslated.
- Validation messages (Zod), toasts, empty/loading/error states, metadata
  titles, navigation, and marketing copy are all translated.

## Switching language

The active locale is read from the `NEXT_LOCALE` cookie (falls back to `th`).
A language switcher can call the `setLocale` server action:

```tsx
import { setLocale } from "@/i18n/actions";
// e.g. in a client component: <button onClick={() => setLocale("en")}>EN</button>
```

## Adding a new language (e.g. Japanese)

1. Add the locale to `i18n/config.ts`:
   ```ts
   export const locales = ["th", "en", "ja"] as const;
   export const localeNames = { th: "ไทย", en: "English", ja: "日本語" };
   ```
2. Create `messages/ja.json` by copying `messages/th.json` and translating the
   values (keys stay identical).
3. Done — no component or routing changes required. Set the `NEXT_LOCALE`
   cookie to `ja` (via `setLocale`) to preview it.

> Because the locale is resolved from a cookie, pages are server-rendered per
> request. If you later want per-URL locales (e.g. `/en/...`) for SEO, next-intl
> supports adding routing without changing the dictionaries.
