"""Shared, dependency-free visual system for the heritage learning screens."""

BRAND = "#193E3A"
ACCENT = "#245C52"
PALE = "#F0F5F1"

THEME_HEAD = """
<style>
    :root {
        --cb-ink: #203631; --cb-muted: #5E6C65; --cb-paper: #F7F6F2;
        --cb-line: #DFE5DE; --cb-green: #245C52; --cb-gold: #977444;
        --q-primary: #245C52; --q-secondary: #977444;
    }
    html { scroll-padding-top: 110px; }
    body { background: var(--cb-paper); color: var(--cb-ink);
        font-family: 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif;
        font-size: 15px; line-height: 1.75; -webkit-font-smoothing: antialiased; }
    .cb-shell { width: min(1120px, calc(100% - 64px)); margin: 0 auto;
        min-width: 0; padding-top: 40px; padding-bottom: 72px; gap: 24px; }
    .cb-shell > * { max-width: 100%; }
    .cb-header { background: #FCFCF9; color: var(--cb-ink);
        border-bottom: 1px solid var(--cb-line); box-shadow: none; }
    .cb-header-inner { width: min(1120px, calc(100% - 64px)); margin: auto;
        min-height: 80px; gap: 24px; align-items: center; }
    .cb-brand { display: flex; gap: 10px; align-items: center;
        color: #193E3A; text-decoration: none; font-weight: 750;
        font-size: 22px; letter-spacing: -.045em; white-space: nowrap; }
    .cb-brand-mark { border: 1px solid #C4D5CA; background: #EDF3ED;
        padding: 9px; border-radius: 12px; color: #245C52; }
    .cb-nav { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
    .cb-nav a { color: #52625A; text-decoration: none; font-weight: 600;
        font-size: 14px; padding: 9px 12px; min-height: 44px; border-radius: 8px; }
    .cb-nav a:hover, .cb-nav a[aria-current='page'] {
        color: #193E3A; background: #EAF1EA; }
    .cb-title { color: #193E3A; font-weight: 750; letter-spacing: -.045em;
        line-height: 1.45; overflow-wrap: anywhere; }
    .cb-title.text-3xl { font-size: clamp(26px, 3vw, 36px); margin-bottom: 4px; }
    .cb-title.text-2xl { font-size: 23px; }
    .cb-title.text-xl { font-size: 19px; }
    .cb-muted { color: var(--cb-muted); line-height: 1.8; }
    .cb-card { background: #FFFFFF; border: 1px solid var(--cb-line);
        border-radius: 16px; box-shadow: 0 3px 12px #243E3110;
        min-width: 0; overflow-wrap: anywhere; }
    .cb-card .cb-card { box-shadow: none; background: #FDFEFC; }
    .cb-action { min-height: 48px; border-radius: 9px; font-weight: 650;
        padding: 10px 20px; letter-spacing: -.02em; box-shadow: none; }
    .cb-shell .q-btn { border-radius: 9px; box-shadow: none; min-height: 44px;
        text-transform: none; font-weight: 600; }
    .cb-shell .q-btn:not(.q-btn--flat):not(.q-btn--outline):not(.q-btn--round):not([aria-pressed]) {
        background-color: var(--cb-green) !important; color: #FFFFFF !important; }
    .cb-shell .q-btn--outline { color: var(--cb-green) !important;
        background: #FFFFFF; }
    .cb-shell .q-btn--outline:before { border-color: #B8CDC0; }
    .cb-shell .q-btn--flat { color: var(--cb-green) !important; }
    .cb-shell .q-btn.disabled { opacity: .6 !important; }
    .cb-choice { min-height: 62px; border: 1px solid var(--cb-line); border-radius: 10px; }
    .cb-shell a { display: inline-flex; align-items: center; min-height: 44px;
        color: #245C52; text-decoration-color: #9BB5A6; text-underline-offset: 4px;
        overflow-wrap: anywhere; transition: color .15s; }
    .cb-shell a:hover { color: #122F2A; text-decoration-thickness: 2px; }
    .cb-shell .text-blue-700, .cb-shell .text-blue-800, .cb-shell .text-blue-900 {
        color: #245C52; }
    .cb-shell .bg-blue-50 { background-color: #F0F5F1; }
    .cb-shell .q-field { line-height: 1.5; }
    .cb-shell .q-field__control { background: #FBFCF9; border-radius: 9px;
        padding-left: 14px; padding-right: 14px; min-height: 56px; }
    .cb-shell .q-field__control:before { border-color: #BCCBC1; }
    .cb-shell .q-field__label { color: #52655A; }
    .cb-shell .q-field__native, .cb-shell .q-field__input { color: var(--cb-ink); }
    .cb-shell .q-field__bottom { padding: 5px 12px 0; min-height: 16px; }
    .cb-shell .q-btn-toggle { background: #EDF2EC; padding: 5px;
        border: 1px solid #D9E3D8; border-radius: 11px; box-shadow: none; gap: 4px; }
    .cb-shell .q-btn-toggle > .q-btn { flex: 1; min-height: 44px; border-radius: 7px;
        color: #52655A; background: transparent !important; }
    .cb-shell .q-btn-toggle > .q-btn[aria-pressed='true'],
    .cb-shell .q-btn-toggle > .q-btn[aria-checked='true'],
    .cb-shell .q-btn-toggle > .q-btn.bg-primary {
        background: #245C52 !important; color: white !important; }
    .cb-shell .q-expansion-item { border: 1px solid var(--cb-line);
        border-radius: 10px; background: #FAFCF8; overflow: hidden; }
    .cb-shell .q-expansion-item > .q-expansion-item__container > .q-item {
        min-height: 52px; font-size: 14px; color: #365447; font-weight: 600; }
    .cb-shell .q-expansion-item__content { padding: 16px 20px; }
    .cb-shell .q-radio { min-height: 52px; padding: 8px; }
    .cb-card .q-radio { border: 1px solid transparent; border-radius: 8px; }
    .cb-card .q-radio:hover, .cb-card .q-radio[aria-checked='true'] {
        background: #EDF4EB; border-color: #C4D7BF; }
    .cb-shell [role='alert'] { border-left: 3px solid #A96A29;
        background: #FBF4E9; color: #754A23; padding: 12px 16px; border-radius: 6px; }
    .cb-hero { position: relative; width: 100%; padding: 24px 32px;
        background: #EAF0E7; border: 1px solid #D9E2D4; border-radius: 18px;
        gap: 10px; overflow: hidden; }
    .cb-hero:after { content: ''; position: absolute; right: -42px; top: -70px;
        width: 250px; height: 250px; border: 1px solid #CCD8C5; border-radius: 50%;
        box-shadow: 0 0 0 26px #E2EADC, 0 0 0 27px #CCD8C5;
        pointer-events: none; opacity: .65; }
    .cb-hero > * { position: relative; z-index: 1; }
    .cb-eyebrow { font-size: 12px; font-weight: 700; letter-spacing: .15em;
        color: #557348; text-transform: uppercase; }
    .cb-hero-title { font-family: 'Georgia', 'Batang', 'AppleMyungjo', serif;
        font-size: clamp(28px, 4vw, 43px); font-weight: 700;
        letter-spacing: -.07em; color: #193E3A; line-height: 1.4; }
    .cb-hero-copy { font-size: 16px; color: #52634E; max-width: 650px; }
    .cb-badge { background: #FFFFFFB3; border: 1px solid #CFDAC8; color: #39573B;
        border-radius: 6px; padding: 4px 10px; font-size: 12px; font-weight: 600; }
    .cb-study-steps { display: flex; gap: 20px; flex-wrap: wrap; color: #58704F;
        font-size: 13px; margin-top: 4px; }
    .cb-study-steps span { display: flex; gap: 7px; align-items: center; }
    .cb-study-steps b { display: inline-grid; place-items: center; width: 22px; height: 22px;
        background: #D6E1CD; border-radius: 50%; font-size: 11px; }
    .cb-mode-strip { width: 100%; display: grid; grid-template-columns: 1fr minmax(240px, 38%);
        align-items: center; gap: 20px; }
    .cb-mode-strip .cb-title { font-size: 17px; }
    .cb-form-grid { width: 100%; display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
    .cb-form-grid > * { min-width: 0; }
    .cb-search-bar { width: 100%; display: grid; grid-template-columns: 220px 1fr;
        gap: 16px; align-items: start; }
    .cb-search-submit { width: 100%; display: flex; justify-content: flex-end; }
    .cb-section-title { width: 100%; border-bottom: 1px solid var(--cb-line);
        padding-bottom: 14px; margin-top: 8px; }
    .cb-result-card { border-left: 3px solid #B7CBB2; }
    .cb-reading { font-size: 16px; line-height: 1.95; }
    .cb-reading .q-expansion-item__content { font-size: 15px; }
    .cb-kiosk-action { min-height: 72px; border-radius: 16px; font-size: 1.15rem;
        font-weight: 750; padding: 0 28px; }
    .cb-kiosk-card { min-height: 148px; border: 2px solid #C4D4C3; border-radius: 22px; }
    :focus-visible { outline: 3px solid #966024; outline-offset: 4px; }
    .cb-skip-link { position: fixed; top: -100px; left: 16px; z-index: 99999;
        padding: 12px; background: white; color: #193E3A; }
    .cb-skip-link:focus { top: 12px; }
    .cb-diagrams { display:flex; flex-wrap:wrap; gap:16px; width:100%; }
    .cb-diagrams figure { margin:0; padding:12px; text-align:center;
        border:1px solid var(--cb-line); border-radius:10px; background:#fcfdfb; }
    .cb-diagrams figcaption { font-size:13px; max-width:210px; }
    .cb-kiosk .q-radio, .cb-kiosk .q-btn { min-height: 72px; }
    .cb-kiosk .q-radio { font-size: 1.1rem; }
    .cb-kiosk-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); }
    .cb-compare-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    @media (max-width: 900px) {
        .cb-header-inner { gap: 8px; flex-wrap: wrap; padding: 12px 0; }
        .cb-header-inner > .q-space { display: none; }
        .cb-nav { margin-left: auto; gap: 2px; }
        .cb-nav a { padding: 8px; font-size: 13px; }
    }
    @media (max-width: 720px) {
        .cb-shell, .cb-header-inner { width: calc(100% - 32px); }
        .cb-shell { padding-top: 24px; padding-bottom: 40px; gap: 20px; }
        .cb-header-inner { min-height: 68px; }
        .cb-brand { font-size: 19px; }
        .cb-nav { width: 100%; margin-left: 0; justify-content: space-between; }
        .cb-nav a { font-size: 12px; padding: 6px 8px; }
        .cb-hero { padding: 28px 24px; }
        .cb-hero:after { right: -150px; }
        .cb-hero-copy { font-size: 14px; }
        .cb-study-steps { gap: 12px; }
        .cb-card { padding: 20px; }
        .cb-mode-strip, .cb-form-grid, .cb-search-bar,
        .cb-compare-grid, .cb-kiosk-grid { grid-template-columns: minmax(0, 1fr); }
        .cb-mode-strip { gap: 12px; }
        .cb-search-submit .q-btn { width: 100%; }
        .cb-reading { font-size: 15px; }
    }
    @media (prefers-reduced-motion: reduce) {
        *, *:before, *:after { scroll-behavior: auto !important; transition: none !important; }
    }
</style>
<script>document.documentElement.lang = 'ko';</script>
"""
