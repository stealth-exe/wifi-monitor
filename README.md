# wifi-monitor

A lightweight tool that can be used to test the integrity of any network connection. It repeatedly opens a TCP connection to a server of your choice, measures how long it takes, and plots the result in real time. Specifically, 

## Demo
<img width="720" height="450" alt="output" src="https://github.com/user-attachments/assets/ecf1a796-6553-4e5f-83f6-e52a98fab5aa" />



## How it works

- A background thread measures TCP connect time (not ICMP ping, so no admin rights are needed) and keeps the last 120 seconds of samples.
- A small built-in HTTP server serves the page and a few JSON endpoints (`/api/samples`, `/api/target`, `/api/set`, `/api/interval`).
- The page polls for new samples and renders them on a canvas.

## Quick start
Having Python 3.8+ and any browser is recommended.

```bash
python3 wifi_monitor.py
```
Your browser opens automatically at `http://127.0.0.1:6767/`. Press `Ctrl+C` to stop.

## Options

| Flag | Default | Description |
|---|---|---|
| `--host` | `8.8.8.8` | Host to ping |
| `--port` | `443` | TCP port to connect to |
| `--interval` | `0.5` | Seconds between pings (minimum 0.05) |
| `--timeout` | `1.0` | Seconds before a connection counts as dropped |
| `--listen` | `6767` | Local port for the web UI |
| `--min-y` | `50` | Minimum top value of the y-axis, in ms |
| `--no-browser` | off | Don't auto-open the browser |

Example:

```bash
python3 wifi_monitor.py --host 1.1.1.1 --port 53 --interval 0.25 --timeout 2 --no-browser
```

## Features

- values for current ping, drop rate, average latency, and jitter 
- choose from built-in targets (Google, Cloudflare, Quad9, OpenDNS, etc) or enter any custom `host:port`.
- slider from 100 ms to 2 s; applies immediately


## Using `--no-browser`

By default the script opens the graph in your browser on startup. `--no-browser` skips that, so the monitor just runs in the background of your terminal. This is useful when you:

- want to open the graph in a specific browser or profile yourself,
- are running it over SSH, in a terminal multiplexer (tmux/screen), or on a machine without a display,
- are restarting it often and don't want a new tab each time.

The monitor still runs and collects data. To view it, open the URL printed in the terminal (by default `http://127.0.0.1:6767/`) in any browser on the same machine.

You can also read the raw data directly from the JSON API:

```bash
curl http://127.0.0.1:6767/api/target

# All samples from the last 120 s, as [timestamp_ms, latency_ms] pairs
# (latency is null for a dropped connection)
curl http://127.0.0.1:6767/api/samples

#only samples since (ms epoch)
curl "http://127.0.0.1:6767/api/samples?since=1700000000000"
```

## Notes

- Latency is TCP handshake time, which will differ slightly from ICMP ping values.
- Switching servers clears the current graph.
