from collections import deque
import argparse, threading, webbrowser
from http.server import ThreadingHTTPServer
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json


HISTORY_SECONDS = 120
samples = deque()          # (epoch_ms, latency_ms or None)
lock = threading.Lock()
target = {"host": "8.8.8.8", "port": 443}
cfg = {"interval": 0.5}


PAGE = r""""""
def make_handler(page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/api/target":
                with lock:
                    body, ctype = json.dumps({**target, "interval_ms": int(cfg["interval"] * 1000)}).encode(), "application/json"
            elif u.path == "/api/interval":
                try:
                    ms = int(parse_qs(u.query).get("ms", ["0"])[0])
                except ValueError:
                    ms = 0
                if not (50 <= ms <= 5000):
                    self.send_error(400)
                    return
                cfg["interval"] = ms / 1000
                body, ctype = b"{}", "application/json"
            elif u.path == "/api/set":
                q = parse_qs(u.query)
                host = q.get("host", [""])[0].strip()
                try:
                    port = int(q.get("port", ["0"])[0])
                except ValueError:
                    port = 0
                if not host or len(host) > 253 or not (1 <= port <= 65535) or not all(c.isalnum() or c in ".-:" for c in host):
                    self.send_error(400)
                    return
                with lock:
                    target.update(host=host, port=port)
                    samples.clear()
                body, ctype = b"{}", "application/json"
            elif u.path == "/api/samples":
                since = int(parse_qs(u.query).get("since", ["0"])[0])
                with lock:
                    out = [s for s in samples if s[0] > since]
                body, ctype = json.dumps(out).encode(), "application/json"
            elif u.path == "/":
                body, ctype = page.encode(), "text/html; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    return Handler

def sampler(timeout):
    while True:
        start = time.time()
        with lock:
            host, port = target["host"], target["port"]
        ms = probe(host, port, timeout)
        now = int(start * 1000)
        with lock:
            if (host, port) != (target["host"], target["port"]):
                continue  # target changed mid-probe; discard
            samples.append((now, None if ms is None else round(ms, 1)))
            while samples and samples[0][0] < now - HISTORY_SECONDS * 1000:
                samples.popleft()
        while time.time() < start + cfg["interval"]:   # re-checked live so the slider feels instant
            time.sleep(0.02)


def main():
    ap = argparse.ArgumentParser(description="Wi-Fi integrity graph")
    ap.add_argument("--host", default="8.8.8.8")
    ap.add_argument("--port", type=int, default=443)
    ap.add_argument("--interval", type=float, default=0.5)
    ap.add_argument("--timeout", type=float, default=1.0, help="threshold in s for a drop to count")
    ap.add_argument("--listen", type=int, default=6767)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    target.update(host=a.host, port=a.port)
    cfg["interval"] = max(0.05, a.interval)
    threading.Thread(target=sampler, args=(a.timeout,), daemon=True).start()
    page = PAGE
    srv = ThreadingHTTPServer(("127.0.0.1", a.listen), make_handler(page))
    url = f"http://127.0.0.1:{a.listen}/"
    print(f"Pinging {a.host}:{a.port} every {a.interval}s  ->  {url}   (Ctrl+C to stop)")
    if not a.no_browser:
        threading.Timer(0.6, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()