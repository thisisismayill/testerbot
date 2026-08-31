# TesterBot — the automatic website test bot

You give it a link and it does the rest: walks the site, clicks every button it
finds, fills forms with test data and submits them, listens to the console and
the network, and at the end hands you an **HTML report** + screenshots + JSON.

It does not ask for a salary, it does not get tired, and it runs the same way
every time.

**Everything runs on your machine.** There is no account, no upload and no
server — which is also why there is nothing to pay for.

- Website and a real sample report: <https://testerbot-web.vercel.app>
- Licence: MIT (see [`LICENSE`](LICENSE)) · third-party components: [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md)

---

## The easy way: run it with a button (no terminal)

**Double-click `TesterBot.command`** (on Windows, `TesterBot.bat`).

A window opens in your browser with:

- a box at the top for the **site address**
- a **"Start test"** button beside it
- a "Settings" section: how many pages to walk, whether to submit forms, whether
  to check mobile, and so on
- a "Test behind a login too" section: username, password, login page
- a live log while the test runs, and an **"Open the report"** button at the end
- a list of all your previous tests underneath

The password stays on your computer and is never sent anywhere.
To stop it, press **Ctrl+C** in the black window that opened.

> If `TesterBot.command` will not open the first time: right-click → **Open** →
> then choose **Open** again.

The sections below are for people who want to use the terminal.

---

## Site intelligence (since v1.2)

TesterBot no longer only finds bugs — for every site it audits it also gathers
**intelligence** and shows it at the top of the report:

- **Domain authority** — a 0–10 score (OpenPageRank), similar to Ahrefs' "Domain Rating".
- **Performance** — a Lighthouse score plus real-user metrics (LCP, INP, CLS, TTFB) —
  the same Google data the big tools resell.
- **Technology stack** — what the site is built with (WordPress, React, Shopify,
  jQuery, Cloudflare and so on) — 7,000+ technologies recognised.
- **Hosting** — server, CDN, IP.

**Technology and hosting need no key — they work immediately.** Authority and
performance need a free key (once):

| What for | Where from | Free limit |
|---|---|---|
| Domain authority | [domcop.com/openpagerank](https://www.domcop.com/openpagerank/) → sign up → key | 30,000 domains / month |
| Performance (raises the limit) | [Google PageSpeed API](https://developers.google.com/speed/docs/insights/v5/get-started) | performance works without a key too |

You paste the keys once into the **"Intelligence keys"** section of the
interface — they are stored on your computer only. From the terminal:
`--opr-key` / `--psi-key`, or the `TESTERBOT_OPR_KEY` / `TESTERBOT_PSI_KEY`
environment variables. To turn it off: `--no-intel` (all of it) or `--no-perf`
(just performance, which is the slowest part).

---

## Link graph (since v1.3) — the seed of our own data store

This is the **same logic as the core of Ahrefs**, at a small scale: while the bot
walks the site it records every link, then computes **our own PageRank** (the same
power-iteration algorithm Google and Ahrefs use).

In the report you will see:

- **Strongest pages** — which page is most "authoritative" according to the site's
  internal link structure. It also finds **orphan pages** (ones no internal link
  points to) — a real SEO problem.
- **Domains linked out to** — who your site links to, how many times, and whether
  those links are nofollow.
- **Raw data** — `linkgraph.json` (the full edge list plus the computations) and
  `linkgraph-edges.csv`. This is a real, openable **dataset**, not just a chart.

No key needed, works immediately. Nothing to turn on — it is collected on every crawl.

**Why it matters:** this is the first step on the road to "crawl the open web and
build our own data store". Right now we build one site's internal graph; with the
same logic across many sites you get a cross-domain graph — a real backlink index.

---

## Index mode (v2.0) — our own backlink index + our own Domain Authority

Up to here the bot tested **one** site. Now it can walk **many** sites together,
collect the links between them, and compute **our own Domain Authority metric** —
no third party, no keys. This is the core of Ahrefs (a backlink index plus a
domain rating), at a scale one machine can hold.

**How it works:**

Switch to the **"Many sites · Index"** mode at the top of the interface, type one
domain per line, and press **"Build index"**. From the terminal:

```bash
python3 tb_index.py site-1.com site-2.com rival-3.com
python3 tb_index.py --seeds domains.txt --max-pages 30
```

**What you get:**

- **A Domain Authority ranking** — a 1–100 score per domain. A blend of PageRank
  over the cross-domain link graph and referring-domain count (the same principle
  as Ahrefs DR and Moz DA).
- **Backlink discovery** — click any domain: who links to it, with what anchor
  text, follow or nofollow. Referring domains are sorted by their own authority.
- **Link Intersect · opportunities** — pick "your domain" and the index shows the
  domains that link to your **rivals** but not to you, sorted by how many rivals
  they link to. These are the most valuable backlink opportunities (Ahrefs'
  "Link Intersect" feature, from our own data).
- **A growing index** — every run adds to `testerbot-index.db` (SQLite). Crawling
  a site again updates its links rather than duplicating them.
- **Raw data** — `index-report/index-data.json` and the SQLite database can both
  be opened directly.

**Responsible crawling (important):** index mode **respects robots.txt** by
default, identifies itself honestly (`TesterBotIndex/2.0`) and pauses politely
between pages. Being a "good bot" that does not get blocked is the biggest
structural advantage a link product can have. If you are crawling only your own
site and robots.txt is in your way: `--ignore-robots`. To change the pause:
`--delay 800` (ms).

**Note:** the authority metric gets more accurate the more sites you crawl,
because the graph grows. Crawl several rival sites together and the real picture
appears. Only crawl sites you are allowed to crawl.

---

## 1. Install (once)

You need **Python 3.9+** (check with `python3 --version`).

**macOS / Linux:**
```bash
cd webtester-bot
./install.sh
```

**Windows:**
```
install.bat   (double-click it)
```

The script does two things: installs the Python packages and downloads the
Chromium browser (~150 MB, once only). To do it by hand:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

---

## 2. First run

```bash
python3 tester_bot.py https://your-site.com
```

When it finishes you get a short summary in the terminal, and the full report here:

```
testerbot-report/report.html      ← open in a browser
testerbot-report/report.json      ← for reading with code
testerbot-report/screenshots/     ← evidence images
```

In the report every problem is grouped as **Critical / High / Medium / Low /
Info**, and opens when you click it: what happened, on which page, on which
element, the evidence (network response, error text, screenshot) and a
**suggested fix**.

---

## 3. Testing behind a login

To keep the password out of your command line, use an environment variable:

```bash
export TESTERBOT_PASS='the-test-accounts-password'    # Windows: set TESTERBOT_PASS=...

python3 tester_bot.py https://your-site.com \
  --login-url https://your-site.com/login \
  --username test@your-site.com \
  --login-success-url /dashboard \
  --extra-url https://your-site.com/dashboard \
  --extra-url https://your-site.com/profile
```

- The bot tries to find the login form itself. If it cannot, point it there with
  `--user-selector`, `--pass-selector`, `--submit-selector`.
- `--login-success-url` or `--login-success-text` confirms the sign-in really
  worked. If it did not, the bot records that as a **Critical** problem.
- The bot does not follow `/logout` or `/signout` links, so the session is not
  lost. If it is lost anyway, the bot signs in again automatically.
- To keep the session and reuse it later: `--save-storage-state session.json`,
  then `--storage-state session.json` next time.

> **Important:** use a TEST account only, never a real customer account.

---

## 4. What the bot checks

**At page level**
- Uncaught JavaScript errors and `console.error` messages
- HTTP 4xx / 5xx responses (both the page itself and background API calls)
- Images that fail to load, failed network requests
- Empty or nearly empty pages
- "Junk" text visible to users: `undefined`, `NaN`, `[object Object]`,
  `lorem ipsum`, `{{template}}`, `TODO:`, server error traces

**Links**
- Every internal and external link checked one by one (broken links, 404, 500,
  unreachable host)
- An unknown URL returning 200 instead of 404 (soft-404)
- Duplicate `<title>` tags

**Clicks**
- Every button, tab, accordion, dropdown and modal trigger is tried
- A JS error, a 5xx response or a 404 API call after a click is recorded
- **Dead controls**: clicking changes nothing — not the URL, not the DOM, not the network
- Covered or unclickable elements (z-index and overlay problems)

**Forms**
- Empty submission: does the browser block it? If it does, **is there a check on
  the server too** (the bot disables the browser validation and sends the same
  empty request to the server)
- Is a badly formatted email accepted
- Submission with valid data: does it work, does it return 5xx, or does it do nothing
- **Output escaping**: the bot submits the text `<b>…</b>`; if the page renders it
  as real HTML, that is a serious problem (XSS risk)
- Does the login form accept made-up credentials (critical), and does it show an
  error message for a wrong password

**Mobile / responsive**
- Horizontal scroll at 390px (phone) and 820px (tablet)
- A missing viewport meta tag
- It also tells you which element overflows, with a screenshot

**Accessibility**
- Deque's **axe-core** engine (WCAG 2.1 A/AA) — bundled in, no internet needed
- Plus: images without `alt`, fields without labels, buttons without a name, the
  `lang` attribute, heading hierarchy, duplicate `id`s

**Performance**
- Load time, TTFB (server response time), page weight, request count, DOM size

**Security hygiene (on your own domain only)**
- Is there HTTPS, does the HTTP → HTTPS redirect work
- Mixed content, `target=_blank` + `rel=noopener`
- Missing headers: CSP, X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy
- Files left open by accident: `/.env`, `/.git/config`, `/backup.sql`, `/phpinfo.php` and so on

**SEO / metadata**
- `<title>`, meta description, `h1`, canonical, Open Graph, favicon, robots.txt,
  sitemap.xml, a `noindex` left behind by accident

---

## 5. Safety: what the bot will not touch

In the default mode the bot **does not click** anything that looks like delete,
pay, close-account or sign-out, and does not submit such forms (it recognises
those words in English, Azerbaijani and Russian). It lists what it left alone as
"Skipped" in the report, so you can see it was deliberate.

If you want it to try everything, dangerous buttons included:

```bash
python3 tester_bot.py https://staging.your-site.com --danger-mode
```

⚠️ `--danger-mode` should be used **only on a test/staging copy** — on a real
site it can delete data.

Only run the bot on **your own site**, or one you have written permission to test.

---

## 6. Useful commands

```bash
# Walk further
python3 tester_bot.py https://site.com --max-pages 150 --max-depth 4

# Run with a visible browser (watch what it does)
python3 tester_bot.py https://site.com --headed --slow-mo 400

# Test only the blog
python3 tester_bot.py https://site.com --include "/blog/"

# Stay out of the admin panel
python3 tester_bot.py https://site.com --exclude "/admin" --exclude "\?export="

# Click nothing, submit nothing (the safest mode)
python3 tester_bot.py https://site.com --no-click --no-forms

# If a SPA (React/Vue/Angular) is slow to start
python3 tester_bot.py https://site.com --settle 3000 --nav-timeout 60000

# With a configuration file
python3 tester_bot.py --config config.example.yaml

# CI/CD: fail the build if there is a critical problem
python3 tester_bot.py https://site.com --fail-on critical

# Compare this run with the last one: what did we fix, what did we break?
python3 tester_bot.py https://site.com --baseline reports/last-run

# CI/CD: only fail on problems that are NEW since the baseline
python3 tester_bot.py https://site.com --baseline reports/last-run --fail-on-new high
```

The full list of options: `python3 tester_bot.py --help`

---

## 6a. Comparing two runs (since v2.1)

One report tells you what is wrong today. Two reports tell you whether you are
winning. TesterBot can compare any two runs and say exactly what changed.

```bash
# after a run, against an earlier one
python3 tester_bot.py https://site.com --baseline reports/20260827-monday

# or compare two reports you already have
python3 tb_diff.py reports/before reports/after
```

Either form prints a summary and writes **`diff.html`** next to the newer report:

```
  Fixed      : 4
  New        : 1
  Moved page : 1     (same problem, different URL)
  Re-graded  : 1
  Still open : 27

  Fixed since the last run:
   [CRITICAL] Environment file with secrets is publicly reachable: /.env
   [HIGH    ] HTTP 404 on image: /img/missing-photo.png
```

Every finding carries an identity built from its category, title, page and
element, so the comparison is exact rather than a guess. Three consequences
worth knowing:

- **A fix disappearing from the list is proof the fix landed.** Running the same
  site twice with no changes reports nothing at all, so any movement is real.
- **A problem that only moved to another page is not counted as fixed.** It is
  listed separately under *same problem, different page*.
- **A finding that got worse is called out.** If a low-severity problem is now
  high, it appears under *now more serious* rather than hiding among the
  unchanged rows.

### In a pipeline

`--fail-on` fails the build whenever a problem of that severity exists, which is
strict on a site that already has known issues. `--fail-on-new` is the gentler
rule: it fails only when the build *introduced* something.

```bash
python3 tester_bot.py https://site.com \
    --baseline reports/main-branch \
    --fail-on-new high
```

Exit codes: `0` nothing new, `1` a new finding at that severity or worse,
`2` the reports could not be read.

---

## 7. Try the bot yourself (a deliberately broken site)

The package includes a small test site with **more than 20 deliberate defects**.
To see what the bot finds:

```bash
# terminal 1
python3 testsite/server.py

# terminal 2
python3 tester_bot.py http://localhost:8099 \
  --login-url http://localhost:8099/login \
  --username tester --password secret123 \
  --login-success-url /dashboard \
  --extra-url http://localhost:8099/dashboard
```

In the report you will see the broken links, the JS errors, the dead control, the
unescaped output, the form with no server-side validation, the mobile overflow
and the rest.

---

## 8. Common situations

| Problem | Fix |
|---|---|
| `playwright: command not found` | `python -m playwright install chromium` |
| The site is very slow, it times out | `--nav-timeout 90000 --settle 3000` |
| A self-signed certificate on staging | `--ignore-https-errors` |
| The login is not found | pass `--login-url` + `--user-selector` / `--pass-selector` |
| The report is full of "Low/Info" | click the **Critical** or **High** tile in the report — only those remain |
| The bot takes too long | `--max-pages 25 --no-external-links --no-axe` |
| I do not want forms submitted | `--no-forms` |

---

## 8a. Letting the index grow by itself (since v2.1)

Index mode crawls the domains you name. It also *records* every other domain
those pages link out to — but until now it never went and looked at them. So the
index only ever knew what you had already thought to type in.

`--expand` closes that loop:

```bash
# crawl 20 of the most-linked domains the index has found but never visited
python3 tb_index.py --expand 20
```

Each run reaches one ring further out. Run it again and the domains discovered
last time become the ones crawled this time:

```
run 1  seed: hub.example                    →  2 domains,  5 links
run 2  --expand                             →  3 domains, 13 links
run 3  --expand                             →  3 domains, 19 links
```

The frontier is ordered by **how many different domains link to a candidate**, so
the crawl spends its time on pages the web itself considers worth pointing at,
not on whatever happened to be first alphabetically. `--min-links 3` raises that
bar; a domain mentioned once by one site is usually noise.

Two things it will not do. It never expands into the big link sinks — Facebook,
YouTube, Wikipedia, CDNs — because they link out to everything and would eat the
whole budget; `--skip-domain` adds your own. And `--expand` refuses to run with
`--ignore-robots`, because expanding means crawling sites that are not yours, and
on those, `robots.txt` is not optional.

### Running it on a schedule

```bash
# a night's work, then stop cleanly whatever it has reached
python3 tb_index.py --expand 200 --min-links 2 --time-budget 420 \
    --db ~/testerbot/index.db --out ~/testerbot/dashboard
```

`--time-budget` is in minutes and is checked between domains, so the run always
finishes the domain it is on and never leaves half a site in the index.

On macOS, `crontab -e` and add one line to run it at 02:00 every night:

```
0 2 * * * cd ~/testerbot && ./venv/bin/python tb_index.py --expand 200 --time-budget 420 >> ~/testerbot/crawl.log 2>&1
```

Be honest with yourself about where it runs. On a laptop it crawls while the lid
is open and stops when it is not; that is fine for building a picture of a few
thousand domains in your own field. A round-the-clock index needs a machine that
stays on.

### What to expect

Roughly one to two seconds per page, most of it the politeness delay and the
site's own response time. At the default 25 pages per domain that is about half
a minute per domain, so an overnight run reaches a few hundred domains. The
SQLite index handles millions of links comfortably.

This is a picture of a neighbourhood, not a copy of the web. Pointed at the two
hundred sites that matter in your field it will tell you who really links to
whom — which is the question you actually have. Pointed at "the internet" it
will run forever and finish nothing.

The data lives in your SQLite file. Nothing is sent anywhere.

---

## 9. File structure

```
webtester-bot/
├── TesterBot.command       # ← double-click this (macOS interface)
├── TesterBot.bat           # ← the same for Windows
├── testerbot_ui.py         # the interface server
├── ui_page.py              # the interface page
├── tester_bot.py           # single-site QA (CLI)
├── tb_index.py             # multi-site index (CLI)
├── tb_diff.py              # compare two runs (CLI)
├── reports/                # reports from tests run through the interface
├── requirements.txt
├── install.sh / install.bat
├── config.example.yaml
├── testsite/server.py      # the deliberately broken sample site
└── testerbot/
    ├── crawler.py          # crawling + orchestration
    ├── auth.py             # login
    ├── dom_probe.py        # the JS that collects data from a page
    ├── audits.py           # DOM/network/console checks
    ├── interact.py         # clicking + form tests
    ├── site.py             # robots, sitemap, 404, links, exposed files
    ├── a11y.py             # the axe-core audit
    ├── intelligence.py     # authority + performance + hosting
    ├── techdetect.py       # technology detection (7,000+ signatures)
    ├── linkgraph.py        # single-site link graph + PageRank
    ├── index_store.py      # the growing link index (SQLite)
    ├── authority.py        # our own Domain Authority metric
    ├── harvest.py          # the fast multi-site link crawler
    ├── index_report.py     # the Index Explorer dashboard
    ├── robots.py           # robots.txt + polite crawling
    ├── report.py           # HTML + JSON report
    ├── diff.py             # comparing two runs
    └── vendor/
        ├── axe.min.js      # axe-core (MPL-2.0, Deque Systems)
        └── techfp.json     # technology signatures (MIT)
```

Adding another check is easy: write a new function in `audits.py` that returns
`Finding(...)` and it will appear in the report by itself.

---

## 10. Do not forget

The bot **does not replace a human tester** — it takes over the repetitive,
mechanical part: visiting every page, trying every button, checking every link.
Whether the business logic is correct (say, "is the discount calculated right")
still needs a person.

Treat every finding in the report as "a point to look at", not "a confirmed bug".

---

## Licence

TesterBot is released under the **MIT Licence** — see [`LICENSE`](LICENSE). Use
it, change it, ship it inside your own product; just keep the copyright notice.

The bundled accessibility engine (axe-core, Mozilla Public License 2.0) and the
technology fingerprints (MIT) keep their own licences. See
[`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

## A word on where you point it

Crawl sites you own or have written permission to test. TesterBot identifies
itself honestly in its user agent, respects `robots.txt`, and never clicks a
control that deletes, pays or signs out — but permission is still yours to
obtain, not the tool's.
