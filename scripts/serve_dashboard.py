#!/usr/bin/env python3
"""Serve the ARIES live monitor locally.

The page is monitor/index.html and it reads state/dashboard.json, which the
runner writes. Both are local because the broker connection is local -- a
hosted page cannot see a bot running on your own machine.

Note this is NOT dashboard/, which is the compiled output of the ares-react
app and is served by Netlify.

    python scripts/serve_dashboard.py            # http://127.0.0.1:8787
    python scripts/serve_dashboard.py --port 9000 --host 0.0.0.0
"""
import argparse
import functools
import http.server
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Handler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        # the page polls every 3s; never let a proxy or the browser cache it
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()

    def log_message(self, fmt, *args):      # quiet: the dashboard polls often
        pass


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--no-open", action="store_true")
    a = p.parse_args()
    state = ROOT / "state" / "dashboard.json"
    if not state.exists():
        print(f"note: {state} does not exist yet — the dashboard will show "
              f"'no data' until the runner writes it.", file=sys.stderr)
    handler = functools.partial(Handler, directory=str(ROOT))
    # Threading, not the single-threaded default: the page polls every 3s and
    # a 100KB+ snapshot read must not be able to block the next request.
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    url = f"http://{a.host}:{a.port}/monitor/"
    with http.server.ThreadingHTTPServer((a.host, a.port), handler) as httpd:
        print(f"ARIES monitor -> {url}   (ctrl-C to stop)")
        if not a.no_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
