"""Build site77/index.html from a saved copy of the live 1976 page.

Usage:  python3 -I site77/tools/build_from_76.py <path-to-1976-index.html>

Keeps the 1976 layout, tabs, styles and scripts. Swaps in 1977 event details,
strips every 1976 classmate, photo, payment link, email, committee name and price,
and recolors the gold accents to green so the palette is green and white only.
"""
import base64, os, re, sys

SRC = sys.argv[1]
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "public")
P = "[PLACEHOLDER]"
EMAIL = "southhigh77@gmail.com"

s = open(SRC, encoding="utf-8").read()
fails = []

def sub(old, new, count=1, regex=False):
    global s
    if regex:
        s2, n = re.subn(old, new, s, flags=re.S)
    else:
        n = s.count(old)
        s2 = s.replace(old, new)
    if n == 0 or (count and n != count):
        fails.append((old[:70], n))
    s = s2

# ---- 1. Logo: pull the embedded Spartan logo out into its own file ----
m = re.search(r'data:image/png;base64,([A-Za-z0-9+/=]+)', s)
open(os.path.join(OUT_DIR, "logo.png"), "wb").write(base64.b64decode(m.group(1)))
s = re.sub(r'data:image/png;base64,[A-Za-z0-9+/=]+', 'logo.png', s)

# ---- 2. Head ----
sub('<title>South High Class of 1976 — 50-Year Reunion</title>',
    '<title>South High Class of 1977 — 50-Year Reunion</title>')
sub(r'<meta name="description" content="[^"]*">',
    '<meta name="description" content="South Torrance High School Class of 1977 — 50-Year Reunion, '
    'September 18, 2027, Redondo Beach. Help us find missing classmates and share your old photos.">',
    regex=True)

# ---- 3. Hero ----
sub('~ Class of 1976 ~', '~ Class of 1977 ~')
sub('Saturday<br>September 26, 2026<br><span style="font-size:1rem;font-family:Libre Franklin,serif;'
    'font-weight:700;letter-spacing:0;">6:00 &ndash; 11:00 PM</span>',
    'Saturday<br>September 18, 2027<br><span style="font-size:1rem;font-family:Libre Franklin,serif;'
    'font-weight:700;letter-spacing:0;">Time: ' + P + '</span>')
sub('400 N Harbor Dr<br>Redondo Beach, CA 90277', '400 N. Harbor Dr.<br>Redondo Beach, CA 90277')
# 1976 Friday-night happy hour (Hennessey's) is 1976-only: drop the card.
sub(r'\s*<div class="preparty-wrap">.*?</div>\s*</div>\s*(?=</section>)', '\n', regex=True)

# ---- 4. Reunion tab ----
sub('— Saturday, September 26, 2026 —', '— Saturday, September 18, 2027 —')
sub('Saturday, September 26, 2026<br><span class="muted">6:00 PM &ndash; 11:00 PM</span>',
    'Saturday, September 18, 2027<br><span class="muted">Time: ' + P + '</span>')
sub('400 N Harbor Dr, Redondo Beach, CA 90277<br>Discounted group rate for our class',
    '400 N. Harbor Dr., Redondo Beach, CA 90277<br>Group room rate: ' + P)
sub(r'<div class="info-b">\$95 <span class="muted">to Sept 15</span>.*?</div>',
    '<div class="info-b">' + P + '<br><span class="muted">Ticket prices coming soon</span></div>',
    regex=True)

# Tickets block: no prices, no PayPal/Zelle until the committee decides.
sub(r'<h3>🎟️ Tickets</h3>.*?(?=</div>\s*<div class="rd-block">\s*<h3>🏨)',
    '<h3>🎟️ Tickets</h3>\n'
    '      <p>Ticket prices: <strong>' + P + '</strong></p>\n'
    '      <p>How to pay: <strong>' + P + '</strong></p>\n'
    '      <p class="rd-note">The committee is still setting prices and payment. Add your info below and '
    "we'll let you know the moment tickets open.</p>\n"
    "      <p class=\"rd-note\">Bringing a spouse or guest? They're family too.</p>\n    ",
    regex=True)

sub(r'<h3>🏨 Hotel Room Block</h3>\s*<p>.*?</p>',
    '<h3>🏨 Hotel Room Block</h3>\n'
    '      <p>We\'re arranging a block of rooms at the Redondo Beach Hotel for our class. '
    'Group rate: <strong>' + P + '</strong>. To reserve, call <strong>' + P + '</strong> and mention the '
    '<strong>South High Class of 1977 reunion block</strong>. Questions? Email '
    '<strong><a href="mailto:' + EMAIL + '" style="color:var(--green);">' + EMAIL + '</a></strong>.</p>',
    regex=True)

sub('Just add <strong>"Spartan Fund"</strong> in your payment memo. Every bit helps.',
    'How to give: <strong>' + P + '</strong>. Every bit helps.')

sub('<a href="mailto:steinunnsouth76@gmail.com" style="color:var(--green);">steinunnsouth76@gmail.com</a>',
    '<a href="mailto:' + EMAIL + '" style="color:var(--green);">' + EMAIL + '</a>')

# ---- 5. Sign-up form ----
sub(r'(<div class="success-banner" id="success">\s*<h3>You\'re In!</h3>\s*<p>[^<]*</p>).*?(?=</div>\s*<div class="form-wrap">)',
    r'\1' + '\n      <p style="margin-top:0.6rem;font-size:1rem;">Ticket prices and how to pay: <strong>'
    + P + "</strong>. We'll email you as soon as tickets open.</p>\n    ",
    regex=True)
sub("name='reunion-1976'", "name='reunion-1977' data-netlify=\"true\" netlify-honeypot=\"bot-field\"")
sub('value="reunion-1976"', 'value="reunion-1977"')
sub("what we called you in '76)", "what we called you in '77)")

# ---- 6. Classmates tab: empty roster, same controls ----
sub('— The Class of 1976 —', '— The Class of 1977 —')
sub(r'(<div class="name-list" id="cmList">).*?(</div>\s*\n\s*<p class="cm-noresults")',
    r'\1\n  \2', regex=True)
s, n = re.subn(r'[ \t]*<template id="card-\d+">.*?</template>\n?', '', s, flags=re.S)
if n == 0:
    fails.append(("templates", 0))
# Friendly empty state until Phase 2 fills the roster.
sub("if (noRes) noRes.style.display = (shown === 0) ? 'block' : 'none';",
    "if (noRes) {\n      noRes.style.display = (shown === 0) ? 'block' : 'none';\n"
    "      if (rows.length === 0) noRes.textContent = 'The Class of 1977 roster is being built from the yearbook. Check back soon!';\n    }")

# ---- 7. In Memoriam tab: empty grid ----
sub(r'(<div class="mem-grid">).*?(</div>\s*<p class="mem-foot">)', r'\1\n\n  \2', regex=True)

# ---- 8. Footer ----
sub('South Torrance High School · Class of 1976', 'South Torrance High School · Class of 1977')
sub('50-Year Reunion · Saturday, September 26, 2026 · Redondo Beach Hotel, 400 N Harbor Dr',
    '50-Year Reunion · Saturday, September 18, 2027 · Redondo Beach Hotel, 400 N. Harbor Dr.')
sub(r'<div>Tobi \(Golin\).*?</div>',
    '<div>Susan Best · Karen Czuleger · Jenefer Harger</div>\n'
    '  <div style="margin-top:0.5rem;"><a href="mailto:' + EMAIL + '" style="color:inherit;">' + EMAIL + '</a></div>',
    regex=True)
sub("Site built by Lauren (McAlpine) Cotner '78", 'Site manager: Lauren (McAlpine) Cotner')

# ---- 9. Countdown ----
sub("// Target: September 26, 2026 at 6:00 PM local time (event start guess)",
    "// Target: September 18, 2027. Start time is a [PLACEHOLDER]; 6:00 PM used until it is set.")
sub("new Date('2026-09-26T18:00:00')", "new Date('2027-09-18T18:00:00')")

# ---- 10. 1976 music widget comes out; Phase 3 adds the Summer of 1977 player ----
sub(r'\n#musicWidget\{.*?@media print\{#musicWidget,#musicPanel\{display:none !important;\}\}\n', '\n', regex=True)
sub(r'<div id="musicWidget">.*?</script>\n', '', regex=True)
# Pre-party CSS is now unused.
sub(r'\n/\* ===== PRE-REUNION HAPPY HOUR ===== \*/.*?(?=</style>)', '\n', regex=True)

# Payment-button styles for PayPal/Zelle are unused now.
s = re.sub(r'\.pay-btn\.(paypal|zelle) \{[^}]*\}\n', '', s)
s = re.sub(r'\.paypal-alert[^{]*\{[^}]*\}\n', '', s)

# ---- 11. Green and white only: recolor gold / cream / tan accents ----
for old, new in [
    ('--gold: #c5a564;', '--gold: #5e9a57;'),
    ('#c5a564', '#5e9a57'), ('#b8902f', '#2C5827'), ('#a8842f', '#1F5B1F'),
    ('#f5b942; color: #5a3a10', '#d8e6d2; color: #093F01'),
    ('#fbf3dd', '#f0f7ec'), ('#ece7da', '#eef3ec'), ('#9a8f78', '#5b7a57'),
    ('#e7e2d6', '#e3eee0'), ('#fbf7ee', '#f5fbf2'),
]:
    s = s.replace(old, new)

# ---- Safety checks: nothing from 1976 may survive ----
leftovers = [w for w in ['paypal', 'zelle', 'southhigh76', 'steinunn', 'Tabares', '$95', '$120', '$125',
                         '$249', 'Hennessey', 'Quintiliani', 'McClure', 'Harvey', 'Freymodsson', 'Bradshaw',
                         'photos/', 'Class of 1976', '2026', '424-275']
             if w.lower() in s.lower()]
open(os.path.join(OUT_DIR, "index.html"), "w", encoding="utf-8").write(s)
print("written", len(s), "bytes")
print("substitution misses:", fails or "none")
print("1976 leftovers:", leftovers or "none")
