# Design system — all pages MUST follow this so the site reads as one product

**Feel:** editorial civic data journalism (think NYT Upshot / The Pudding / Bloomberg CityLab), not a SaaS dashboard.
Confident, quiet, generous whitespace, one big number per section that hits you, then the detail.

## Tokens (copy verbatim into each page's CSS)
- Fonts (Google Fonts allowed, fallback stacks required): display **"Instrument Serif"** (headlines, big numbers), body **"Inter"** (400/500/600), mono **"JetBrains Mono"** for numbers in tables (tabular-nums).
- Light: --bg:#FAF8F3 (warm paper) --fg:#141414 --muted:#6B6860 --line:#E6E2D8 --card:#FFFFFF --accent:#D4491E (NYC orange-red, used sparingly) --accent2:#1F5FA8 (subway blue) --ok:#2E7D4F
- Dark: --bg:#101010 --fg:#F2EFE8 --muted:#9C978C --line:#262626 --card:#181818 accents same but slightly lighter.
- Radius 14px cards, 1px --line borders, NO drop shadows in light, subtle in dark. No gradients on cards. One hero gradient/texture max.
- Type scale: hero number 72–120px serif; h1 40px serif; body 17px/1.6; captions 13px muted uppercase tracking .08em.
- Motion: numbers count up on load (600ms, ease-out), rows fade/slide in staggered (≤400ms), hover lifts cards 2px. prefers-reduced-motion respected.
- Data color: sequential single-hue ramp from --line to --accent for "bad" intensity; never rainbow. Bars are 8px tall rounded, muted track.
- Mobile first, 100% must be usable one-handed at 390px; tables collapse to cards under 640px.
- Sticky top bar: site wordmark "NYC civic tools" (serif) left, nav links to all 4 tools right, theme toggle.
- Every page: hero (title + one-sentence what + THE number), then controls, then content, then methodology (collapsed <details>), then footer with data source + GitHub + "nothing stored".
- No CDN JS. Google Fonts <link> only. No emoji in UI. No lorem. No politician names. No AI-tool mentions.
