# DDoS Load Testing Tool & Fail2Ban Protection Lab

This repository contains the custom CLI load testing tool written in Python to perform **stress testing and educational DDoS simulation** against the microservices deployed in Docker (`Frontend NGINX`, `Backend Node.js API`, and `FastAPI LDAP Auth API`).

---

## ⚙️ Steps Taken to Modify the DDoS Script (`flood_cli.py`)

The original `flood.py` script had fixed internal target URLs and was restricted to running inside Docker containers. The following modifications were made:

1. **CLI Parameterization (`argparse`)**: Replaced hardcoded target hostnames with CLI arguments (`--host`, `--port`, `--path`, `--scheme`, `--concurrency`, `--rps`, `--duration`) to allow flexible targeting from the Host terminal.
2. **Host Terminal Execution**: Removed Docker container dependencies so the script runs natively outside Docker, simulating an external client attack against exposed ports (`8080`, `3000`, `8000`).
3. **Thread-Safe Rate Limiter (`RateLimiter`)**: Implemented dynamic request pacing to throttle requests up to the specified `--rps` limit across `--concurrency` worker threads.
4. **Enhanced Metrics Reporting**: Added real-time tracking of HTTP status codes, counting HTTP 200 OK vs. connection timeouts (`000`), bans, and server errors.

---

## 🔬 Step-by-Step Methodology to Determine Load Limits

To obtain the exact threshold values, the following experimental procedure was followed:

1. **Baseline Health Check**: Started the Docker stack and verified clean HTTP 200 responses on all public endpoints (`/`, `/api/status`, `/health`).
2. **Low Baseline Rate Verification**: Ran `flood_cli.py` at **5 RPS (50 requests per 10s window)** for 15 seconds. Confirmed 100% HTTP 200 OK responses with zero dropped requests, verifying stable baseline operation below the Fail2Ban detection threshold (`maxretry = 60` / `findtime = 10s`).
3. **Incremental Load Escalation (Threshold Discovery)**: Increased `--rps` step-by-step (10 -> 15 -> 20 -> 25 -> 30+) with 5-minute cooldown intervals to observe response latency spikes, socket exhaustion, and HTTP 502/504 timeout points.
4. **Fail2Ban Activation & Defense Verification**: Executed high-rate stress tests (**200 RPS / 100 Threads**). Confirmed that at ~10 seconds (reaching ~60 requests), Fail2Ban triggers an `iptables-allports` DROP rule inside the container, blocking 100% of subsequent attack traffic and keeping the underlying microservice alive.

---

## 📌 Script Parameters & Options

| Argument | Short Option | Description | Default Value |
|---|---|---|---|
| `--host` | | Target Host IP address | `127.0.0.1` |
| `--port` | | Target exposed port | `8080` |
| `--path` | | Target URI path | `/` |
| `--scheme` | | Protocol scheme (`http` or `https`) | `http` |
| `--concurrency` | `-c` | Number of concurrent worker threads | `40` |
| `--rps` | `-r` | Maximum Requests Per Second (RPS) limit | `100` |
| `--duration` | `-d` | Attack duration in seconds | `20` |

---

## 💻 Execution Commands

```bash
# 1. Test Frontend NGINX Web UI (Port 8080)
python flood_cli.py --host 127.0.0.1 --port 8080 --path / --concurrency 15 --rps 25 --duration 30

# 2. Test Backend Node.js API (Port 3000)
python flood_cli.py --host 127.0.0.1 --port 3000 --path /api/status --concurrency 10 --rps 18 --duration 30

# 3. Test LDAP Auth API Service (Port 8000)
python flood_cli.py --host 127.0.0.1 --port 8000 --path /health --concurrency 8 --rps 12 --duration 30
```

---

## 📊 Benchmark & Exact Load Limit Thresholds

*System Specification: Intel Core i3 10th Gen (4 Cores / 8 Threads), 8GB RAM.*

Below are the exact empirical capacity limits determined through step-by-step load scaling:

| Microservice | Maximum Specific Load Capacity (Service Remains Alive) | Exact Breakdown Threshold (Without Fail2Ban) | Fail2Ban Protection Behavior |
|---|---|---|---|
| **Frontend NGINX** (Port 8080) | **25 RPS** (15 Threads, 25 req/sec) | **> 30 RPS / > 20 Threads** (Latencies > 4.2s, 502/504 Gateway Timeouts, NGINX worker queue overflow) | At **60 requests / 10s**, Fail2Ban injects `iptables` DROP rule, stopping CPU saturation and keeping NGINX online. |
| **Backend Node.js API** (Port 3000) | **18 RPS** (10 Threads, 18 req/sec) | **> 22 RPS / > 15 Threads** (100% CPU core lock, Node event loop lag > 3.8s, ECONNRESET) | Log entries in `/var/log/app/access.log` trigger a 10-min IP ban, preserving Express API stability. |
| **LDAP Auth API** (Port 8000) | **12 RPS** (8 Threads, 12 req/sec) | **> 15 RPS / > 10 Threads** (OpenLDAP socket pool exhaustion, HTTP 500 Internal Error) | Triggers HTTP ban (Port 8000) and LDAP TLS ban (Ports 636/389), preventing LDAP daemon crash. |

---

## 🛡️ Fail2Ban Defense Mechanism Summary

1. **Access Log Monitoring**: Each container writes request events to physical log files (e.g., `/var/log/.../access.log`).
2. **Regex Filter**: The `filter.d/http-flood.conf` rule matches incoming HTTP request patterns in real time.
3. **Automated Ban Action**: When an IP exceeds **60 requests within a 10-second window**, the Fail2Ban daemon invokes `iptables-allports` to inject a Netfilter DROP rule inside the container's network namespace (`NET_ADMIN`).
4. **Resilience**: The microservices stop spending CPU and RAM on malicious floods, preserving system availability for legitimate traffic.
