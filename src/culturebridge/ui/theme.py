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
/* Desktop harness layout: quiet surfaces, one navigation rail and one work area. */
:root {
 --cb-paper:#fafaf9; --cb-surface:#fff; --cb-ink:#292b29; --cb-muted:#6b706b;
 --cb-green:#315c4f; --cb-line:#e5e7e3; --cb-soft:#f0f2ee; --cb-radius:12px;
}
html {scroll-padding-top:76px}
body {background:var(--cb-paper);font-size:15px;line-height:1.65}
.cb-header {background:#fafaf9f5;border-bottom:1px solid var(--cb-line)}
.cb-header-inner {width:100%;min-height:58px;padding:0 22px;gap:12px}
.cb-workspace-title {font-size:14px;font-weight:650}
.cb-workspace-caption {font-size:12px;color:var(--cb-muted)}
.cb-sidebar {background:#f0f1ed;color:var(--cb-ink)}
.cb-sidebar .q-drawer__content {display:flex;flex-direction:column;padding:24px 14px 14px;gap:24px;height:100%;min-height:0}
.cb-sidebar .cb-brand {padding:0 10px;font-size:19px;letter-spacing:-.04em;gap:10px}
.cb-sidebar .cb-brand .q-icon {color:#315c4f}
.cb-sidebar .cb-brand-mark {padding:0;background:transparent;border:0;border-radius:0}
.cb-sidebar .cb-nav {display:flex;flex-direction:column;align-items:stretch;gap:4px}
.cb-sidebar .cb-nav a {display:flex;align-items:center;gap:12px;padding:10px 12px;
 min-height:44px;font-size:14px;border-radius:8px;color:#555b54;box-shadow:none;
 justify-content:flex-start;text-align:left;white-space:nowrap}
.cb-sidebar .cb-nav a[aria-current=page],.cb-thread-link[aria-current=page] {
 background:#e1e5dd;color:#253e32;font-weight:650}
.cb-sidebar a {text-decoration:none}
.cb-thread-list {flex:1 1 0;min-height:0;overflow-y:auto;align-content:start;flex-wrap:nowrap}
.cb-thread-items {flex:0 0 auto;min-width:0}
.cb-thread-row {min-width:0;flex:0 0 auto;border-radius:8px}
.cb-thread-row:hover {background:#e7eae2}
.cb-sidebar-label {padding:0 12px 10px;font-size:12px;color:#72786f;font-weight:650}
.cb-thread-link {display:block;flex:1 1 0;min-width:0;padding:10px 12px;border-radius:8px;
 color:#535950;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.cb-thread-menu {flex:0 0 32px;opacity:.7}
.cb-thread-more {align-self:flex-start;flex:0 0 auto}
.cb-thread-link:hover,.cb-sidebar-settings:hover {background:#e7eae2}
.cb-thread-empty {padding:0 12px;color:#73796f;font-size:12px}
.cb-sidebar-bottom {margin-top:auto;border-top:1px solid #dfe3d9;padding-top:12px}
.cb-sidebar-bottom .q-expansion-item {font-size:12px}
.cb-sidebar-bottom .q-item {padding:8px 10px;min-height:44px}
.cb-sidebar-bottom .q-expansion-item__content {display:flex;flex-direction:column;padding:8px 14px}
.cb-sidebar-bottom .q-expansion-item__content a {color:#596152;padding:8px 0;min-height:40px}
.cb-sidebar-settings {display:flex;align-items:center;gap:12px;padding:10px 12px;
 color:#4f584a;border-radius:8px;font-size:14px;min-height:44px}
.cb-shell {width:min(1040px,calc(100% - 64px));padding-top:32px;gap:22px}
.cb-shell.cb-chat-workspace {width:min(820px,calc(100% - 64px));padding-bottom:40px}
.cb-chat-workspace:has(.cb-welcome) {padding-top:clamp(48px,13vh,150px)}
.cb-welcome {align-items:center;text-align:center;margin-bottom:14px}
.cb-welcome-mark {color:#315c4f;margin-bottom:8px}
.cb-title.text-3xl {font-size:clamp(26px,2.5vw,34px);font-weight:650;letter-spacing:-.045em}
.cb-card {border-radius:12px;box-shadow:none;border-color:var(--cb-line)}
.cb-shell .cb-learning-start {border:1px solid #d7dcd3!important;border-radius:18px!important;
 box-shadow:0 4px 16px #202b1807;padding:20px!important;background:#fff!important}
.cb-entry-prompt .q-field__control {min-height:100px!important;background:transparent!important}
.cb-entry-prompt.q-field--outlined .q-field__control:before,
.cb-entry-prompt.q-field--outlined .q-field__control:after {border:0}
.cb-prompt-examples {order:3;gap:6px}
.cb-shell .cb-prompt-examples .q-btn {min-height:36px;border-radius:8px;font-size:12px;
 background:#f5f6f3!important;color:#59634f!important;font-weight:500}
.cb-start-actions {justify-content:flex-end}
.cb-shell .q-btn {border-radius:8px;min-height:44px;font-size:14px;font-weight:550}
.cb-shell .q-field__control {min-height:52px;border-radius:10px;background:#fff}
.cb-shell .q-expansion-item {background:#f8f9f6;border-radius:10px}
.cb-shell .q-expansion-item>.q-expansion-item__container>.q-item {min-height:44px;font-size:13px}
.cb-shell .cb-learning-start>.q-expansion-item {border:0;background:transparent}
.cb-transcript {max-width:780px;gap:22px}
.cb-shell .cb-message-assistant {background:transparent;border:0;border-left:0;
 border-radius:0!important;padding:16px 0!important}
.cb-shell .cb-message-user {background:#ecefe8!important;border:0;
 border-radius:16px!important;padding:16px 20px!important}
.cb-message-body {font-size:15px;line-height:1.9}
.cb-composer-dock {position:sticky;bottom:0;z-index:5;background:var(--cb-paper);
 padding:16px 0;box-shadow:0 -12px 18px var(--cb-paper)}
.cb-composer {border-radius:14px}
.cb-composer .q-field__control {background:#fff;border-radius:14px}
.cb-composer textarea {max-height:180px;overflow-y:auto!important}
.cb-composer-actions {padding:6px 0;justify-content:flex-end}
.cb-chat-options {max-width:780px}
.cb-library-tabs a {padding:8px 14px;border-radius:8px;text-decoration:none;font-size:14px}
.cb-library-tabs a[aria-current=page] {background:var(--cb-soft);font-weight:650}
.cb-course-grid>.cb-card {border-top:1px solid var(--cb-line)!important}
.cb-course-art,.cb-course-art svg {height:140px}
.cb-next-actions {background:#f2f4ee;border-radius:12px}
.cb-shell.cb-kiosk .q-btn,.cb-shell.cb-kiosk .q-radio {min-height:72px;font-size:1.1rem}
@media(max-width:900px) {
 .cb-shell,.cb-shell.cb-chat-workspace {width:calc(100% - 40px)}
 .cb-workspace-caption {display:none}
 .cb-chat-workspace:has(.cb-welcome) {padding-top:48px}
 .cb-welcome .cb-muted {font-size:14px}
}
@media(max-width:480px) {
 .cb-shell,.cb-shell.cb-chat-workspace {width:calc(100% - 28px)}
 .cb-header-inner {padding:0 12px}.cb-start-actions .q-btn {width:100%}
 .cb-welcome {text-align:left;align-items:flex-start}
 .cb-shell .cb-learning-start {padding:14px!important}
 .cb-composer-dock {position:static}
}
.cb-quiz-progress {padding:12px 18px;border-radius:10px;background:#edf2e9;
 font-weight:650;color:var(--cb-green)}
@media (prefers-reduced-motion: reduce) {
 *,*:before,*:after {scroll-behavior:auto!important;transition:none!important}
}
</style>
<script>document.documentElement.lang='ko';</script>
"""
