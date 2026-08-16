"""The sign-in page has to work on the worst day, not the best one.

It is the page you land on when something has gone wrong, so it must render on
a cold server with no network: no webfont, no CDN, no image file. And it is the
page a stranger sees, so it must say what the thing IS -- a bare password box on
a half-remembered domain gives nobody a way to tell they are in the right place.

TWO LOGIN TEMPLATES EXIST AND ONLY ONE IS WIRED UP.

    templates/dash_login.html   rendered by routes/dash_auth_routes.py, which
                                dashboard.py registers -- this is the real one
    templates/login.html        belongs to routes/auth_routes.py, whose
                                blueprint is never registered

The unregistered one builds its URLs with url_for('auth.login'), an endpoint
that does not exist in the running app, so it would raise BuildError if it were
ever rendered. Editing it changes nothing anybody can see. This test pins WHICH
template the app actually serves, so the next person does not spend an hour
improving the wrong file -- which is exactly what happened here.
"""
import re
import sys

sys.path.insert(0, r"D:\AltaScraper")

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(label)
    print("  %-62s %s" % (label, "OK" if ok else "FAIL got=%r want=%r" % (got, want)))


def truthy(label, got):
    check(label, bool(got), True)


HTML = open(r"D:\AltaScraper\templates\dash_login.html", encoding="utf-8").read()
CSS = open(r"D:\AltaScraper\static\css\dash_login.css", encoding="utf-8").read()

print("\n== the app serves THIS template ==")
route = open(r"D:\AltaScraper\routes\dash_auth_routes.py", encoding="utf-8").read()
truthy("dash_auth_routes renders dash_login.html",
       'render_template("dash_login.html"' in route)
dash = open(r"D:\AltaScraper\dashboard.py", encoding="utf-8-sig").read()
truthy("and dashboard.py registers that module", "_dash_auth_routes.register(" in dash)

print("\n== it renders with nothing but itself ==")
# A CDN, a webfont or an <img> is one more thing that has to be reachable at the
# moment you are trying to find out why nothing is reachable.
truthy("no external stylesheet or script",
       not re.search(r'(src|href)\s*=\s*["\']https?://', HTML))
truthy("no webfont import", "@import" not in CSS and "fonts.googleapis" not in CSS)
truthy("no image files, only inline svg",
       "<svg" in HTML and not re.search(r"<img\b", HTML))
truthy("the stylesheet is the app's own", '/static/css/dash_login.css' in HTML)
truthy("  and cache-busted with the app's asset version", "{{ ASSET_V }}" in HTML)

print("\n== the contract with the route ==")
# Three variables, and all three branches have to be handled: the shared
# password, real accounts, and a failed attempt.
truthy("the shared-password mode asks for a password only",
       re.search(r"{%\s*else\s*%}[\s\S]{0,400}Team password", HTML) is not None)
truthy("the accounts mode asks for email AND password",
       re.search(r"not bootstrap[\s\S]{0,600}name=\"email\"[\s\S]{0,600}name=\"password\"",
                 HTML) is not None)
truthy("an error is shown when there is one", "{% if error %}" in HTML)
truthy("  and a non-string error still reads as words",
       'error if error is string else "Wrong password."' in HTML)
truthy("where you were heading is carried through",
       'name="next" value="{{ next }}"' in HTML)
truthy("it posts back to the same place, as the route expects",
       '<form method="post" class="form">' in HTML)

print("\n== it says what the thing is ==")
for word in ("Listing generation", "Compliance", "Sales", "Image Studio"):
    truthy("  names %s" % word, word in HTML)
truthy("and where it sells", "Amazon UK" in HTML)
# Whitespace-normalised: prose in a template is wrapped for the developer
# reading it, so "publish to Amazon" is split across two lines in the source
# and matching the raw text asserts the line width rather than the words.
FLAT = re.sub(r"\s+", " ", HTML)
truthy("and warns what the console can do", "publish to Amazon" in FLAT)

print("\n== usable ==")
truthy("every field has a label", HTML.count('class="lbl"') >= 1
       and 'for="password"' in HTML)
truthy("the password field autocompletes as a password",
       'autocomplete="current-password"' in HTML)
truthy("the error is announced to a screen reader", 'role="alert"' in HTML)
truthy("the decorative chart is not read out as content", 'aria-hidden="true"' in HTML)
truthy("focus is visible for keyboard users", ":focus-visible" in CSS)
# Under 16px, iOS zooms the page the moment the field is focused and the box
# ends up half off-screen.
truthy("inputs are 16px on a phone, so iOS does not zoom",
       re.search(r"max-width:520px\)\{[\s\S]{0,200}font-size:16px", CSS) is not None)
truthy("the form comes first on a small screen", "order:-1" in CSS)
truthy("motion is dropped when the reader asks", "prefers-reduced-motion" in CSS)

print("\n== it looks like the app it opens ==")
# The console's own palette, not a second one to keep in step.
for token in ("#1a1d23", "#2dd4a8", "#1e2128"):
    truthy("  uses the console colour %s" % token, token in CSS)

print("\n%d failed" % len(fails))
for f in fails:
    print("  FAILED:", f)
sys.exit(1 if fails else 0)
