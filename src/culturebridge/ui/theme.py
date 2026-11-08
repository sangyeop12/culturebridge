"""Shared CultureBridge design tokens and components. No external font dependency."""

BRAND = "#193E3A"
ACCENT = "#245C52"
PALE = "#F0F5F1"

THEME_HEAD = """
<style>
:root {
 --cb-paper: #F7F3E9; --cb-surface:#fffefa; --cb-ink:#253b35; --cb-muted:#627168;
 --cb-green:#245C52; --cb-gold:#916b3e; --cb-line:#dce2d9; --cb-soft:#edf3ec;
 --cb-radius:18px; --q-primary:#245C52; --q-secondary:#916b3e;
}
html {scroll-behavior:smooth;scroll-padding-top:110px}
body {background:var(--cb-paper);color:var(--cb-ink);font-family:'Segoe UI','Malgun Gothic',
 'Apple SD Gothic Neo',sans-serif;font-size:16px;line-height:1.8;-webkit-font-smoothing:antialiased}
.nicegui-content {padding:0!important;gap:0;min-height:calc(100vh - 80px)}
.cb-shell,.cb-header-inner,.cb-context-wrap,.cb-site-footer {
 width:min(1160px,calc(100% - 64px));margin-left:auto;margin-right:auto;min-width:0}
.cb-shell {padding-top:36px;padding-bottom:64px;gap:24px}
.cb-shell>* {max-width:100%;min-width:0}
.cb-header {background:#fffef9f5;color:var(--cb-ink);border-bottom:1px solid var(--cb-line);
 box-shadow:none;
 backdrop-filter:blur(12px)}
.cb-header-inner {min-height:80px;align-items:center;gap:24px}
.cb-brand {display:inline-flex;align-items:center;gap:10px;min-height:44px;
 font-size:22px;font-weight:780;letter-spacing:-.055em;color:#193e3a;
 text-decoration:none;white-space:nowrap}
.cb-brand-mark {color:var(--cb-green);padding:10px;border:1px solid #cedbd0;
 background:var(--cb-soft);border-radius:13px}
.cb-nav {display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.cb-nav a {padding:10px 14px;min-height:44px;font-size:14px;color:#53665b;text-decoration:none;
 font-weight:650;border-radius:10px;white-space:nowrap}
.cb-nav a:hover,.cb-nav a[aria-current=page] {color:#193e3a;background:var(--cb-soft)}
.cb-settings-link {display:inline-flex;align-items:center;justify-content:center;
 min-width:44px;min-height:44px;border-radius:10px;color:var(--cb-green);text-decoration:none}
.cb-settings-link:hover,.cb-settings-link[aria-current=page] {background:var(--cb-soft)}
.cb-context-wrap {padding-top:14px;display:flex;justify-content:space-between;align-items:center;
 gap:16px;flex-wrap:wrap}
.cb-breadcrumb {display:flex;gap:8px;align-items:center;font-size:13px;color:var(--cb-muted)}
.cb-breadcrumb a {color:var(--cb-muted);text-decoration:none;min-height:32px;display:inline-flex;
 align-items:center}
.cb-subnav {display:flex;flex-wrap:wrap;gap:4px}
.cb-subnav a {color:#53665b;text-decoration:none;font-size:13px;min-height:40px;
 display:inline-flex;align-items:center;
 padding:5px 12px;border-radius:8px;border:1px solid transparent}
.cb-subnav a[aria-current=page] {background:var(--cb-surface);border-color:var(--cb-line);
 color:var(--cb-green);font-weight:700}
.cb-related-menu {max-width:100%;font-size:14px}
.cb-related-menu .q-item {min-height:44px;border-radius:10px}
.cb-related-menu .q-expansion-item__content {padding:4px 0 8px}
.cb-details>.q-expansion-item__container>.q-item {min-height:56px;font-weight:650}
.cb-details>.q-expansion-item__container>.q-expansion-item__content {
 padding:0 24px 24px;display:flex;flex-direction:column;gap:12px}
.cb-next-actions {padding:18px 0;border-top:1px solid var(--cb-line);align-items:center}
.cb-prompt-examples .q-btn {font-size:13px;min-height:40px}
.cb-citation+.cb-citation {border-top:1px solid var(--cb-line);padding-top:14px;margin-top:10px}
.cb-title {color:#193e3a;font-weight:750;letter-spacing:-.045em;line-height:1.45;
 overflow-wrap:anywhere}
.cb-title.text-3xl {font-family:'Batang','AppleMyungjo','Georgia',serif;
 font-size:clamp(27px,3vw,36px);margin-bottom:4px}
.cb-title.text-2xl {font-size:24px}
.cb-title.text-xl {font-size:20px}
.cb-title.text-lg {font-size:18px}
.cb-muted {color:var(--cb-muted);line-height:1.8}
.cb-card {background:var(--cb-surface);border:1px solid var(--cb-line);
 border-radius:var(--cb-radius);
 box-shadow:0 4px 18px #203f3006;min-width:0;overflow-wrap:anywhere}
.cb-card .cb-card {box-shadow:none;background:#fafcf8;border-radius:12px}
.cb-shell .q-btn {min-height:44px;border-radius:10px;text-transform:none;font-weight:650;
 letter-spacing:-.02em;box-shadow:none}
.cb-shell .q-btn:not(.q-btn--flat):not(.q-btn--outline):not(.q-btn--round):not([aria-pressed]) {
 background-color:var(--cb-green)!important;color:white!important}
.cb-shell .q-btn--outline {color:var(--cb-green)!important;background:#fffefa}
.cb-shell .q-btn--outline:before {border-color:#bbcdbf}
.cb-shell .q-btn--flat {color:var(--cb-green)!important}
.cb-shell .q-btn.disabled {opacity:.55!important}
.cb-action {min-height:48px;padding:10px 22px;border-radius:10px}
.cb-shell a {color:var(--cb-green);min-height:40px;display:inline-flex;align-items:center;
 text-underline-offset:5px;text-decoration-color:#9ab4a6;overflow-wrap:anywhere}
.cb-shell a:hover {color:#153b32;text-decoration-thickness:2px}
.cb-link-primary,.cb-link-secondary {padding:10px 20px;border-radius:10px;
 text-decoration:none!important;
 font-weight:700;min-height:48px!important}
.cb-shell .cb-link-primary {background:var(--cb-green);color:white}
.cb-shell .cb-link-primary:hover {background:#193e3a;color:white}
.cb-link-secondary {background:#fffef9;border:1px solid #bcccbc}
.cb-shell .text-blue-700,.cb-shell .text-blue-800,.cb-shell .text-blue-900 {color:var(--cb-green)}
.cb-shell .bg-blue-50 {background:var(--cb-soft)}
.cb-shell .q-field {line-height:1.5}
.cb-shell .q-field__control {border-radius:11px;background:#fcfdfa;padding-left:14px;
 padding-right:14px;min-height:56px}
.cb-shell .q-field__control:before {border-color:#bccabf}
.cb-shell .q-field__label {color:#597064}
.cb-shell .q-field__native,.cb-shell .q-field__input {color:var(--cb-ink);font-size:16px}
.cb-shell .q-field__bottom {padding:5px 12px 0;min-height:16px}
.cb-shell .q-btn-toggle {padding:4px;background:#eaf0e8;border:1px solid var(--cb-line);
 border-radius:12px;gap:4px;box-shadow:none}
.cb-shell .q-btn-toggle>.q-btn {flex:1;min-height:44px;border-radius:8px;
 background:transparent!important;color:#53665b}
.cb-shell .q-btn-toggle>.q-btn[aria-pressed=true],.cb-shell .q-btn-toggle>.q-btn[aria-checked=true],
 .cb-shell .q-btn-toggle>.q-btn.bg-primary {background:var(--cb-green)!important;
 color:white!important}
.cb-shell .q-expansion-item {border:1px solid var(--cb-line);border-radius:12px;
 background:#f9fbf6;overflow:hidden;width:100%}
.cb-shell .q-expansion-item>.q-expansion-item__container>.q-item {min-height:50px;font-size:14px;
 color:#365647;font-weight:650}
.cb-shell .q-expansion-item__content {padding:16px 20px}
.cb-shell .q-radio {min-height:52px;padding:8px}
.cb-card .q-radio {border:1px solid transparent;border-radius:10px}
.cb-card .q-radio:hover,.cb-card .q-radio[aria-checked=true] {background:var(--cb-soft);
 border-color:#bfcebf}
.cb-shell [role=alert] {padding:14px 18px;background:#fbf1e3;border-left:3px solid #a86e31;
 color:#765025;border-radius:10px}
.cb-section-heading {margin-top:12px}
.cb-section-title {width:100%;padding-bottom:12px;border-bottom:1px solid var(--cb-line)}
.cb-hero {position:relative;width:100%;padding:36px 40px;background:#eee9dc;
 border:1px solid #ded6c5;border-radius:22px;gap:14px;overflow:hidden}
.cb-hero.cb-illustrated {min-height:342px}
.cb-illustrated>:not(.cb-hero-art) {max-width:60%;position:relative;z-index:1}
.cb-eyebrow {font-size:12px;color:#69774f;font-weight:750;letter-spacing:.1em}
.cb-hero-title {white-space:pre-line;font-family:'Batang','AppleMyungjo','Georgia',serif;
 font-size:clamp(32px,4vw,46px);font-weight:700;line-height:1.35;letter-spacing:-.065em;
 word-break:keep-all}
.cb-hero-copy {font-size:16px;color:#526454;line-height:1.9}
.cb-badge {padding:3px 9px;font-size:12px;border:1px solid #d4d9c7;background:#fffef9ae;
 border-radius:6px;color:#496144}
.cb-hero-art {position:absolute!important;bottom:0;right:0;width:40%;margin:0;line-height:0;
 z-index:0}
.cb-heritage-art {display:block;width:100%;height:auto}
.cb-art-caption {font-size:12px;line-height:1.6;color:#746f61}
.cb-study-steps {display:flex;gap:16px;flex-wrap:wrap;font-size:12px;color:#5b7057;margin-top:4px}
.cb-study-steps span {display:flex;align-items:center;gap:7px}
.cb-study-steps b {display:inline-grid;place-items:center;width:22px;height:22px;
 border-radius:50%;background:#dce4cf;font-size:11px}
.cb-learning-start {border-top:3px solid #9bb7a4;padding:28px!important;scroll-margin-top:110px}
.cb-start-options {display:grid;grid-template-columns:1fr 1fr;gap:12px;width:100%}
.cb-start-actions {width:100%;align-items:center;gap:18px;flex-wrap:wrap}
.cb-transcript {max-width:920px;align-self:center}
.cb-message {max-width:100%;box-shadow:none;padding:24px!important;gap:12px!important}
.cb-message-assistant {border-radius:4px 18px 18px 18px;background:#fffefa}
.cb-message-user {align-self:flex-end;max-width:85%;border-radius:18px 4px 18px 18px;
 background:#e8f0e7;border-color:#ccd9cb}
.cb-message-body {font-size:16px;line-height:1.95;white-space:pre-wrap}
.cb-message .q-expansion-item {margin-top:4px;background:#f7f9f3}
.cb-composer {max-width:920px;align-self:center}
.cb-composer-actions {width:100%;max-width:920px;align-self:center;align-items:center;gap:10px}
.cb-chat-options {width:100%;max-width:920px;align-self:center}
.cb-conversation-link {padding:16px 20px;border:1px solid var(--cb-line);border-radius:12px;
 background:var(--cb-surface);text-decoration:none;width:100%;font-weight:650}
.cb-course-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px;width:100%}
.cb-course-card {padding:0!important;overflow:hidden;gap:0!important}
.cb-course-art {width:100%;height:190px;background:#eee9dc;overflow:hidden}
.cb-course-art svg {width:100%;height:100%}
.cb-course-body {padding:26px;gap:12px;flex:1}
.cb-course-body>a {margin-top:auto;font-weight:700}
.cb-course-number {font-size:12px;color:var(--cb-gold);letter-spacing:.08em}
.cb-course-banner {width:100%;max-height:210px;overflow:hidden;background:#eee9dc;
 border:1px solid var(--cb-line);border-radius:18px}
.cb-course-banner svg {width:100%;height:210px}
.cb-world-banner {display:grid;grid-template-columns:1fr 240px;width:100%;align-items:center;
 gap:24px;
 padding:24px 28px;background:#eee9dc;border:1px solid #ded6c5;border-radius:18px}
.cb-world-banner svg {max-height:135px}
.cb-mode-strip {display:grid;grid-template-columns:1fr minmax(240px,38%);gap:20px;
 align-items:center;width:100%}
.cb-mode-strip .cb-title {font-size:18px}
.cb-form-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;width:100%}
.cb-search-bar {display:grid;grid-template-columns:220px 1fr;gap:16px;width:100%;align-items:start}
.cb-search-submit {display:flex;justify-content:flex-end;width:100%}
.cb-choice {min-height:64px;border:1px solid var(--cb-line);border-radius:12px}
.cb-result-card {border-left:3px solid #a5bfa8}
.cb-reading {font-size:17px;line-height:2;max-width:78ch}
.cb-compare-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
.cb-diagrams {display:flex;flex-wrap:wrap;gap:16px;width:100%}
.cb-diagrams figure {margin:0;padding:16px;border:1px solid var(--cb-line);border-radius:12px;
 background:#fafcf8;text-align:center}
.cb-diagrams figcaption {font-size:13px;max-width:210px}
.cb-kiosk-action {min-height:72px;border-radius:16px;font-size:1.15rem;font-weight:750;
 padding:0 28px}
.cb-kiosk-card {min-height:148px;border:2px solid #c4d4c3;border-radius:20px}
.cb-kiosk-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr))}
.cb-kiosk .q-radio, .cb-kiosk .q-btn { min-height: 72px; }
.cb-shell.cb-kiosk .q-btn-toggle>.q-btn {min-height:72px}
.cb-kiosk-header {gap:12px;flex-wrap:wrap}
.cb-kiosk-header .q-space {min-width:0}
.cb-kiosk .q-radio {font-size:1.1rem}
.cb-site-footer {order:100;margin-top:auto;padding:26px 0 32px;border-top:1px solid var(--cb-line);
 color:var(--cb-muted);font-size:12px}
.cb-site-footer a {color:#52675b;min-height:40px;display:inline-flex;align-items:center;
 text-underline-offset:4px}
.cb-footer-brand {font-size:17px;font-weight:750;color:#193e3a}
:focus-visible {outline:3px solid #94652e;outline-offset:4px}
.cb-shell[tabindex="-1"]:focus {outline:3px solid #94652e;outline-offset:4px}
.q-btn:focus-visible,.q-item:focus-visible {outline-offset:-3px}
.cb-shell .q-field,.cb-shell .q-field__inner {min-width:0;max-width:100%}
.cb-shell .q-table__container {max-width:100%;overflow-x:auto}
.cb-skip-link {position:fixed;top:-100px;left:16px;z-index:99999;padding:12px;background:white;
 color:#193e3a}
.cb-skip-link:focus {top:12px}
@media (max-width: 1000px) {
 .cb-header-inner {gap:12px;flex-wrap:wrap;padding:12px 0}
 .cb-header-inner>.q-space {display:none}
 .cb-nav {margin-left:auto}.cb-nav a {padding:8px 10px}
}
@media (max-width: 720px) {
 .cb-shell,.cb-header-inner,.cb-context-wrap,.cb-site-footer {width:calc(100% - 32px)}
 .cb-shell {padding-top:24px;padding-bottom:40px;gap:20px}
 .cb-header-inner {min-height:64px;gap:8px}
 .cb-brand {font-size:20px}
 .cb-settings-link {margin-left:auto}
 .cb-nav {order:1}
 .cb-nav {width:100%;margin:0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:2px}
 .cb-nav a {padding:6px 4px;font-size:12px;white-space:normal;min-height:52px;
  justify-content:center;text-align:center;line-height:1.5;word-break:keep-all}
 .cb-context-wrap {padding-top:14px;gap:8px}
 .cb-subnav {gap:0}.cb-subnav a {padding:4px 9px;font-size:12px}
 .cb-card {padding:20px}
 .cb-hero {padding:26px 22px;border-radius:18px}
 .cb-hero.cb-illustrated {min-height:0}
 .cb-illustrated>:not(.cb-hero-art) {max-width:100%}
 .cb-hero-title {font-size:31px}
 .cb-hero-copy {font-size:14px}
 .cb-hero-art {position:relative!important;width:100%;margin:0 0 -26px}
 .cb-hero-art svg {height:105px;width:100%}
 .cb-study-steps {gap:12px}
 .cb-start-options,.cb-course-grid,.cb-form-grid,.cb-search-bar,.cb-mode-strip,
 .cb-compare-grid,.cb-kiosk-grid,.cb-world-banner {grid-template-columns:minmax(0,1fr)}
 .cb-learning-start {padding:22px!important}
 .cb-world-banner {padding:22px}.cb-world-banner svg {max-height:110px}
 .cb-search-submit .q-btn {width:100%}
 .cb-message {padding:20px!important}.cb-message-user {max-width:94%}
 .cb-reading,.cb-message-body {font-size:16px}
 .cb-site-footer {padding-bottom:24px}
}
.cb-hero.cb-home-intro {min-height:0;padding:24px 30px;gap:6px}
.cb-home-intro .cb-hero-title {font-size:clamp(26px,3vw,34px);line-height:1.4}
.cb-home-intro .cb-hero-art {width:28%;max-height:160px;overflow:hidden}
.cb-home-intro>:not(.cb-hero-art) {max-width:70%}
.cb-home-intro .cb-art-caption {font-size:11px}
@media (max-width:720px) {
 .cb-header-inner {gap:8px}
 .cb-nav a {padding:8px 4px}
 .cb-hero.cb-home-intro {padding:20px;gap:8px}
 .cb-home-intro>:not(.cb-hero-art) {max-width:100%}
 .cb-home-intro .cb-hero-art {display:none}
 .cb-home-intro .cb-art-caption {display:none}
 .cb-details>.q-expansion-item__container>.q-expansion-item__content {padding:0 16px 16px}
 .cb-next-actions {flex-direction:column;align-items:stretch}
 .cb-related-menu {width:100%}
}
/* Illustrated learning gallery: shared across every existing learning route. */
:root {--cb-paper:#f7f8f4;--cb-surface:#ffffff;--cb-ink:#203e39;
 --cb-muted:#536b65;--cb-line:#dce7e0;--cb-soft:#eaf3ee;--cb-radius:24px}
body {line-height:1.75;
 background:radial-gradient(ellipse at 90% 0,#e8f2e9,transparent 50%),var(--cb-paper)}
.cb-header {background:#ffffffed}
.cb-header-inner {min-height:84px}
.cb-brand-mark {background:#245c52;color:#fff;border:none;border-radius:15px}
.cb-nav a {font-size:15px;padding:12px 18px;border-radius:15px}
.cb-nav a[aria-current=page] {background:#e2efe8;box-shadow:inset 0 -3px #74a98e}
.cb-title.text-3xl,.cb-hero-title {font-family:inherit;font-weight:800;letter-spacing:-.055em}
.cb-title.text-3xl {font-size:clamp(28px,3vw,38px)}
.cb-shell {gap:28px;padding-top:32px}
.cb-card {box-shadow:0 8px 28px #173f3510;border-color:#e2eae4}
.cb-shell .q-btn,.cb-link-primary,.cb-link-secondary {border-radius:16px;min-height:50px}
.cb-shell .q-field__control {border-radius:16px;min-height:60px;background:#fff}
.cb-shell .q-expansion-item {border-radius:16px;background:#f6f9f5}
.cb-shell .q-expansion-item>.q-expansion-item__container>.q-item {min-height:56px;font-size:15px}
.cb-shell .q-radio {min-height:56px}
.cb-card .q-radio {border:1px solid #dce7e0;background:#fff;margin:4px 0}
.cb-hero.cb-home-intro {padding:48px;min-height:450px;justify-content:center;
 background:#edf4e9;border:0;border-radius:32px;gap:18px}
.cb-home-intro .cb-hero-title {font-size:clamp(34px,4vw,52px);line-height:1.25;max-width:52%}
.cb-home-intro .cb-hero-copy {max-width:44%;font-size:18px;line-height:1.8}
.cb-home-intro .cb-eyebrow {color:#386b55;font-size:13px;letter-spacing:.04em}
.cb-home-intro .cb-hero-art {display:block;width:49%;max-height:none;right:0;bottom:24px}
.cb-home-intro .cb-hero-art svg {width:100%;height:auto;display:block}
.cb-home-intro .cb-art-caption {max-width:44%;font-size:11px;color:#536b65;order:5}
.cb-home-intro .cb-hero-actions {max-width:51%;gap:10px}
.cb-discovery-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;width:100%}
.cb-shell .cb-discovery-card {display:flex;flex-direction:column;align-items:stretch;padding:0;
 overflow:hidden;text-decoration:none;background:white;border:1px solid #dce7e0;border-radius:24px;
 box-shadow:0 6px 20px #173f3508;transition:transform .18s ease,box-shadow .18s ease}
.cb-discovery-card:hover {transform:translateY(-4px);box-shadow:0 12px 28px #173f3518}
.cb-discovery-art {width:100%;height:150px;overflow:hidden;background:#edf3e9}
.cb-discovery-art svg {width:100%;height:180px;transform:translateY(-18px)}
.cb-discovery-card:nth-child(2) .cb-discovery-art {background:#eee9f7}
.cb-discovery-card:nth-child(3) .cb-discovery-art {background:#fff0df}
.cb-discovery-art svg>rect {fill:transparent}
.cb-discovery-copy {padding:22px 24px 26px}
.cb-learning-start {border:1px solid #c7dfd5!important;background:#fff!important;
 border-radius:28px!important}
.cb-course-art {border-radius:20px 20px 0 0;overflow:hidden}
.cb-course-art svg {max-height:210px}
.cb-course-grid>.cb-card:nth-child(3n+2) {border-top:5px solid #b4a0d0}
.cb-course-grid>.cb-card:nth-child(3n+1) {border-top:5px solid #89b6a2}
.cb-course-grid>.cb-card:nth-child(3n) {border-top:5px solid #e5b37d}
.cb-message-assistant {border-radius:24px 24px 24px 6px!important;border-left:4px solid #a9c9b6}
.cb-message-user {background:#e9f0fc!important;border-color:#cddbeb;
 border-radius:24px 24px 6px 24px!important}
.cb-message-body,.cb-reading {line-height:1.95;max-width:76ch}
.cb-compare-grid>div {border:1px solid #d7e5dd;border-radius:18px!important;padding:22px!important}
.cb-compare-grid>div:nth-child(2) {background:#f1edf8!important;border-color:#ded5ed}
.cb-next-actions {background:#eef5ee;border:1px solid #dce7e0;border-radius:20px;padding:20px}
.cb-site-footer {border-top:1px solid #dce7e0;padding-top:30px;margin-top:24px}
a:focus-visible,button:focus-visible,[tabindex="0"]:focus-visible {
 outline:3px solid #6e57a1!important;outline-offset:4px}
@media(max-width:900px) {
 .cb-hero.cb-home-intro {padding:32px;min-height:390px}
 .cb-home-intro .cb-hero-title {font-size:38px}
 .cb-discovery-copy {padding:18px}
 .cb-discovery-copy .text-xl {font-size:18px}
}
@media(max-width:720px) {
 .cb-header-inner {min-height:70px}.cb-nav a {font-size:12px;padding:8px 4px}
 .cb-hero.cb-home-intro {padding:28px 24px;min-height:0;gap:16px}
 .cb-home-intro>:not(.cb-hero-art),.cb-home-intro .cb-hero-title,
 .cb-home-intro .cb-hero-copy,.cb-home-intro .cb-art-caption,
 .cb-home-intro .cb-hero-actions {max-width:100%}
 .cb-home-intro .cb-hero-title {font-size:34px}
 .cb-home-intro .cb-hero-copy {font-size:16px}
 .cb-home-intro .cb-hero-art {position:relative!important;width:100%;right:auto;bottom:auto;
 height:auto;max-height:none;margin:0;order:4}
 .cb-home-intro .cb-art-caption {display:block;order:5}
 .cb-home-intro .cb-hero-actions {width:100%}
 .cb-hero-actions a {width:100%;justify-content:center}
 .cb-discovery-grid {grid-template-columns:1fr;gap:12px}
 .cb-shell .cb-discovery-card {flex-direction:row;align-items:center;min-height:128px}
 .cb-discovery-art {width:112px;min-width:112px;height:128px;align-self:stretch}
 .cb-discovery-art svg {height:128px;transform:none}
 .cb-discovery-copy {padding:16px;min-width:0}
 .cb-discovery-copy .text-xl {font-size:18px}
 .cb-card {border-radius:20px}
 .cb-shell {gap:22px}
}
/* Keep the learning action close to the first screen; artwork supports it. */
.cb-hero.cb-home-intro {min-height:250px;padding:30px 36px;gap:12px}
.cb-home-intro .cb-hero-title {font-size:clamp(30px,3vw,40px);max-width:65%}
.cb-home-intro .cb-hero-copy {font-size:16px;max-width:60%}
.cb-home-intro .cb-hero-art {width:32%;bottom:16px}
.cb-home-intro .cb-art-caption {max-width:60%;font-size:11px}
.cb-other-start {align-items:center;border-bottom:1px solid var(--cb-line);padding-bottom:18px}
.cb-quiz-progress {padding:12px 18px;border-radius:14px;background:#eaf3ee;
 font-weight:700;color:#245c52}
@media(max-width:720px) {
 .cb-hero.cb-home-intro {padding:24px;min-height:0}
 .cb-home-intro .cb-hero-title,.cb-home-intro .cb-hero-copy,
 .cb-home-intro .cb-art-caption {max-width:100%}
 .cb-home-intro .cb-hero-title {font-size:30px}
 .cb-home-intro .cb-hero-art {width:100%;bottom:auto;max-height:130px}
 .cb-home-intro .cb-hero-art svg {height:130px;width:100%}
 .cb-other-start {gap:8px}
}
@media (prefers-reduced-motion: reduce) {
 *,*:before,*:after {scroll-behavior:auto!important;transition:none!important}
}
</style>
<script>document.documentElement.lang='ko';</script>
"""
