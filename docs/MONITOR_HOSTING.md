# Hosting the live monitor on Netlify

## The constraint, first

The bot runs on your machine, next to IB Gateway. Netlify is a static host on
the internet. **A hosted page cannot read a file on your laptop** — so the bot
has to push its state up, and the page pulls it down from there.

    your laptop                         Netlify
    ----------------------------        ----------------------------
    run_aries_futures.py
      -> state/dashboard.json  (local record, always written)
      -> POST /api/state ----------->  netlify/functions/state.mjs
                                         -> Netlify Blobs
                                       monitor/index.html
                                         <- GET /api/state

Consequences worth knowing before you rely on it:

- **If the bot is not running, the page shows the last snapshot it pushed.**
  That is why the page shows the snapshot's age and turns the indicator to
  `stale` after 3 minutes. A dead bot must not look like a quiet one.
- Pushing is **opt-in**. With no `ARIES_STATE_URL` set, nothing leaves the
  machine and the monitor stays local-only. The local file is always written.
- A failed push is **logged, never fatal**. The trading loop does not stop
  because a CDN hiccuped.

## Setup

### 1. Connect the repo

In Netlify: *Add new site → Import an existing project → GitHub →* this repo,
branch `claude/aries-trading-engine-build-8nmia3`. `netlify.toml` already sets
the build command, the publish directory and the functions directory, so take
the defaults.

### 2. Make two tokens

Two separate ones, because the two sides need different trust. The bot can
write; your browser can only read.

    python -c "import secrets; print('write', secrets.token_urlsafe(32)); print('read ', secrets.token_urlsafe(24))"

### 3. Set them on the site

*Site configuration → Environment variables → Add a variable:*

| key | value |
|---|---|
| `ARIES_WRITE_TOKEN` | the write token |
| `ARIES_READ_TOKEN` | the read token |

Then **redeploy** — functions only pick up new environment variables on a
fresh deploy.

### 4. Point the bot at the site

In your local `.env` (gitignored, never committed):

    ARIES_STATE_URL=https://<your-site>.netlify.app/api/state
    ARIES_WRITE_TOKEN=<the same write token>

### 5. Open it

    https://<your-site>.netlify.app/monitor/

It will ask for the read key once and keep it in that browser. To skip the
prompt — on a phone, say — open it with the key in the URL **fragment**:

    https://<your-site>.netlify.app/monitor/#k=<read token>

A fragment is never sent to the server, so the key stays out of access logs
and out of any referrer header. The page stores it and strips it from the URL.
A query string (`?k=`) would not be safe this way, which is why the endpoint
does not accept one.

### 6. Check it works

    python run_aries_futures.py --replay --capital 25000

The last lines say either `published to <url>` or `not published (<reason>)`.

## Who can see it

Only someone holding the read token. There is no unauthenticated path to the
data: the function returns 401 without the header, `/monitor/*` and `/api/*`
are sent `X-Robots-Tag: noindex`, and the page is set `X-Frame-Options: DENY`.

That said, this is a shared secret in a URL on a public host — appropriate for
a paper-trading monitor, and **not** the thing to rely on if the page ever
carries anything more sensitive than position counts and equity. Nothing here
can place an order; the bot's IBKR credentials never leave your machine.

If a token leaks: change it in the Netlify UI, redeploy, update `.env`.

## Local use has not gone away

    python scripts/serve_dashboard.py     # http://127.0.0.1:8787/monitor/

Served from localhost the page reads `state/dashboard.json` directly and needs
no key at all. It falls back to `/api/state` only if the local file is missing.

## Tests

    npm test        # the function: auth, validation, storage round trip
    pytest          # the publisher: trimming, failure handling, monitor wiring

`npm test` also runs an end-to-end check in which the real Python publisher
pushes over real HTTP into the real function and the snapshot is read back.
That seam is where a header-name or bearer-format mismatch would otherwise
show up as a monitor that is simply always empty.
