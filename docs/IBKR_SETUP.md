# Step 2: getting IBKR talking to the bot

Plain version: you install a small program from Interactive Brokers that stays
logged into your paper account and listens on a port. The bot connects to that
port. Nothing reaches IBKR's servers except through it, and it runs on your
machine, not here.

Budget about 30 minutes, most of it waiting for the account to be approved.

---

## 1. Get a paper account

A paper account is a full simulation — real prices, real contract specs,
fake money.

Go to **interactivebrokers.com → Open Account**, and either:

- **You already have an IBKR account:** log in to Client Portal, then
  *Settings → Account Settings → Paper Trading Account → create*. Instant.
  Note the username it gives you; it is NOT your live one.
- **You don't:** open a standard individual account. IBKR issues the paper
  account alongside it. Approval usually takes a day or two.

You do not need to fund anything to paper trade.

> Your paper login is a **different username** from your live one, usually
> your live username with a prefix. Write it down — the whole safety story
> below depends on logging in with the right one.

## 2. Download IB Gateway, not TWS

Two programs do the same job:

| | what it is | use it? |
|---|---|---|
| **IB Gateway** | a small window, no charts, just the connection | **yes** |
| TWS | the full trading platform | only if you want the charts |

Gateway uses a fraction of the memory and is built to be left running, which
is what a two-month run needs.

Download: **interactivebrokers.com → Trading → Platforms → IB Gateway**, the
*Latest* (not *Stable*) build is fine. Install it.

## 3. Log in — the one screen that matters

When Gateway opens there is a **Paper Trading / Live Trading** toggle.

**Choose Paper Trading, and use your paper username.** Everything else in
this guide assumes you did. The bot also refuses live ports on its own, but
don't lean on that — get it right here.

## 4. Turn the API on

In IB Gateway: **Configure → Settings → API → Settings**
(In TWS it is *Edit → Global Configuration → API → Settings*.)

Set these:

| setting | value | why |
|---|---|---|
| Enable ActiveX and Socket Clients | **ticked** | without this nothing can connect |
| Socket port | **4002** | Gateway's paper port — note it, step 6 needs it |
| Read-Only API | **ticked, for now** | see below |
| Allow connections from localhost only | ticked | nothing off your machine can reach it |
| Trusted IPs | `127.0.0.1` | same |

Then **OK**, and restart Gateway so it takes effect.

### Leave "Read-Only API" ticked to begin with

That checkbox makes it **physically impossible for anything to place an order
through the API**, whatever the bot does. For the first week or two of
watching, that is exactly what you want: two independent locks, IBKR's and
the bot's `--submit` flag.

Untick it only when you are ready for the bot to actually trade.

### A note on ports

| | live | paper |
|---|---|---|
| IB Gateway | 4001 | **4002** |
| TWS | 7496 | **7497** |

The runner refuses 4001 and 7496 outright, and refuses any port it doesn't
recognise rather than guessing which kind it is.

## 5. Install the client library

On your machine, in the project folder:

```bash
pip install -r requirements.txt
```

That pulls in `ib_async`, which is what the bot uses to talk to Gateway.

## 6. Point the bot at it

In your `.env` (the gitignored one, next to `.env.example`):

```
IB_HOST=127.0.0.1
IB_PORT=4002        # 4002 = Gateway paper. Use 7497 if you chose TWS.
IB_CLIENT_ID=11
```

## 7. Start it in observe mode

With Gateway open and logged in:

```bash
python run_aries_futures.py --paper --capital 25000
```

What you should see, in order:

```
connected to IB Gateway 127.0.0.1:4002 (paper account) via ib_async
resolved 8 contracts
```

then, every 60 seconds, lines like:

```
WOULD BUY 2 MES (have 0, want 2)
```

It is **not trading**. It is telling you what it would do. Open the monitor
alongside it and watch the Target column.

### If you see "no real-time prices … using DELAYED data"

That is normal and fine. A paper account has no futures market-data
subscription by default, so IBKR sends prices on a delay. This book
rebalances once a day on closing prices, so a delay of a few minutes changes
nothing. The message exists so you know which one you're getting rather than
wondering why the numbers look slightly off.

If you later want live prices, it's the *CME Real-Time* bundle in Client
Portal, a few dollars a month. Not needed for this.

### If it can't connect

- **Connection refused** — Gateway isn't running, or the port is wrong.
  Check the port in *Configure → Settings → API → Settings* matches `.env`.
- **It hangs, then times out** — Gateway is showing a dialog waiting for you
  to accept the incoming connection. Accept it and tick "don't ask again".
- **"no contract found for MES"** — the account hasn't been enabled for
  futures. In Client Portal: *Settings → Account Settings → Trading
  Permissions → Futures*. Paper mirrors your live permissions.

## 8. Letting it run for two months

**Gateway logs itself out once a day.** IBKR forces this. Set
*Configure → Settings → Lock and Exit → Auto restart* so it restarts instead
of logging out — it then keeps going without you retyping a password. You
will still need to log in by hand roughly once a week.

The bot survives Gateway going away: the push to the monitor keeps failing
visibly, the activity feed records it, and the page goes `stale`. That is the
behaviour to expect, not a bug.

Two months of this tells you what a backtest cannot: whether fills land where
the prices said, what commissions really cost, whether contract rolls are
handled, and whether the whole thing survives being left alone.

## 9. When you're ready to let it trade

1. Untick **Read-Only API** in Gateway, restart it.
2. Run with `--submit`.

Keep it on the paper account for the full two months regardless. The point
isn't the simulated profit, it's finding out what breaks.

---

## What is NOT tested

Everything above is written from IBKR's documented behaviour, and the bot's
port handling and price parsing are covered by tests. But **no part of this
project has ever connected to a real IB Gateway** — there isn't one in the
environment it was built in. The first connection is yours, and the first run
is likely to turn up something small. Run it in observe mode and read what it
says before you let it near `--submit`.
