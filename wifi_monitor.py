from collections import deque
import argparse, threading, webbrowser
from http.server import ThreadingHTTPServer


HISTORY_SECONDS = 120
samples = deque()          # (epoch_ms, latency_ms or None)
lock = threading.Lock()
target = {"host": "8.8.8.8", "port": 443}
cfg = {"interval": 0.5}


PAGE = r""""""
# def make_handler(page):
#     #todo
# def sampler(timeout):
#     adfa


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