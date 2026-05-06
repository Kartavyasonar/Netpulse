# NetPulse — Distributed Network Operations & Anomaly Detection Platform

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.111-green)
![React](https://img.shields.io/badge/React-18-61dafb)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791)

> A distributed NOC platform deployed across two Oracle Cloud VMs. Monitors network topology from multiple geographic vantage points, correlates outages to distinguish site-local failures from global ones, detects anomalies statistically, and visualises live network health through a React dashboard.


---

## Architecture

```
┌──────────────────────────┐         ┌──────────────────────────────────────┐
│  Probe Node (Frankfurt)  │         │  Primary Node (Mumbai)               │
│  Oracle Cloud VM #2      │         │  Oracle Cloud VM #1                  │
│  NODE_ROLE=probe         │──POST──►│  /api/ingest  (metric aggregation)   │
│                          │◄─HB────►│  /api/heartbeat (dead-man's switch)  │
│  icmp_prober             │──logs──►│  log_receiver :9020 (TCP syslog)     │
│  arp_scanner             │         │  anomaly_detector (2σ baseline)      │
│  route_tracer            │         │  probe_runner (local ICMP)           │
│  heartbeat sender        │         │  PostgreSQL 16                       │
│  probe_sender            │         │  FastAPI :8000                       │
└──────────────────────────┘         │  Nginx (TLS + reverse proxy)         │
                                     └──────────────┬───────────────────────┘
                                                    │ HTTPS
                                     ┌──────────────▼───────────────────────┐
                                     │  React 18 Dashboard (Vercel)         │
                                     │  Dashboard, Hosts, Incidents,        │
                                     │  Topology, Routes, Nodes             │
                                     └──────────────────────────────────────┘
```

### Node Roles

| Role | What it does |
|------|-------------|
| `primary` | Runs local ICMP probes, stores all data in PostgreSQL, exposes REST API, runs anomaly detection, receives metrics from probe nodes, checks heartbeats, runs log receiver on TCP :9020 |
| `probe` | Runs ICMP probes, POSTs results to primary `/api/ingest`, sends heartbeats to peers, ships logs to primary TCP :9020 |

`NODE_ROLE` in `.env` controls which scheduler jobs start on boot.

---

## Features

**Distributed Probe Aggregation** — Each probe node POSTs results to `/api/ingest` every 60s. The primary correlates results within a 120-second window: if both nodes see a host as down it's a global outage; if only one sees it down it's a site-local failure. Results are stored separately in `ingested_metrics` alongside locally-generated `probe_metrics`.

**Dead-Man's Switch Heartbeat** — Every probe node sends `POST /api/heartbeat` to peers every 30s. After 3 consecutive missed heartbeats (90s silence), the primary fires a `PROBE NODE DOWN` alert via Slack and email. NetPulse monitors itself — no external health check service needed.

**Statistical Anomaly Detection (2σ)** — Maintains a rolling 60-minute baseline of RTT and packet loss per host. Alert fires when the current value exceeds `mean + (2 × σ)`. Packet loss > 0% is WARNING; > 20% is CRITICAL. Host unreachable is always CRITICAL. Incidents auto-resolve when metrics return to baseline.

**Scapy pcap RTT Delta** — When `PCAP_ENABLED=true`, a parallel `scapy.sniff()` capture runs alongside the ICMP probe using a BPF kernel filter. The delta between the pcap RTT (kernel clock) and ICMP RTT (userspace clock) quantifies OS scheduling jitter. Both values stored per metric.

**ICMP Rate Limiting** — On Linux startup, iptables `hashlimit` rules are applied programmatically: 10 ICMP packets/second per source IP (burst 20). Prevents the monitoring tool from being used as an ICMP reflection amplifier.

**Async Probing (asyncio.gather)** — All hosts are probed concurrently using `asyncio.gather()` and `asyncio.Semaphore`. Lower memory footprint than threads, no GIL contention, natural fit for the FastAPI event loop.

**ARP Topology Scanning** — Reads `/proc/net/arp` directly (zero network traffic) to get MAC-to-IP mappings. Detects new and disappeared devices between scan cycles. Feeds the topology graph.

**Traceroute Path Monitoring** — TTL-incremented probes map the hop-by-hop path to each host. Consecutive traces are diff'd — if any hop's IP changes, `path_changed` is flagged and a diff summary is stored.

**Structured JSON Logging + Log Shipping** — All log lines emit as structured JSON. Probe nodes ship logs to the primary's TCP :9020 using Python's `SocketHandler`. The primary re-emits them into the local logging hierarchy tagged with the remote node's IP.

---

## Tech Stack

**Backend:** FastAPI 0.111, Uvicorn, SQLAlchemy 2.0 (async), asyncpg, Alembic, Pydantic v2, python-jose (JWT), passlib + bcrypt, APScheduler, icmplib, Scapy, python-nmap, networkx, httpx, numpy, pandas

**Frontend:** React 18, React Router v6, Recharts, react-force-graph-2d, Axios, date-fns, lucide-react, Tailwind CSS, Vite

**Infrastructure:** PostgreSQL 16, Nginx, Let's Encrypt, Docker + Docker Compose, Oracle Cloud Ubuntu 22.04, Vercel, systemd, UFW + iptables

---

## Project Structure

```
netpulse/
├── backend/
│   ├── app/
│   │   ├── api/              auth, hosts, metrics, incidents, topology, routes, ingest
│   │   ├── core/             config, database, security, scheduler, logging_setup, log_receiver
│   │   ├── models/           all 8 database tables
│   │   ├── probers/          icmp_prober, arp_scanner, route_tracer
│   │   ├── schemas/          Pydantic request/response models
│   │   ├── services/         anomaly_detector, heartbeat, probe_runner, probe_sender
│   │   └── main.py           FastAPI app, CORS, lifespan, iptables setup
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── pages/            Dashboard, Hosts, Nodes, Incidents, Topology, Routes, Login
│       ├── components/       charts (Recharts), dashboard widgets, topology graph
│       ├── hooks/            useAuth, usePolling
│       └── services/         api.js — Axios instance + per-resource helpers
├── infra/
│   ├── setup_vps.sh          Primary node full setup (Ubuntu 22.04)
│   ├── setup_probe_node.sh   Probe node setup (no PostgreSQL)
│   ├── nginx.conf            TLS + reverse proxy config
│   ├── netpulse.service      systemd unit file
│   └── rules.v4              Static iptables rules
└── docker-compose.yml        Local: PostgreSQL + API + Nginx
```

---

## Database Models

| Table | Description |
|-------|-------------|
| `hosts` | Monitored IPs/hostnames with status: `up`, `down`, `degraded`, `unknown` |
| `probe_metrics` | One row per probe cycle per host — RTT, packet loss, pcap RTT delta |
| `incidents` | Anomaly alerts with severity, sigma deviation, node correlation JSON, alert dispatch flags |
| `route_traces` | Traceroute results per host with hop JSON and path-change diff |
| `arp_entries` | ARP cache entries — MAC, IP, interface, state, first/last seen |
| `probe_nodes` | Registered distributed nodes with heartbeat status and missed count |
| `ingested_metrics` | Probe results received from remote nodes via `/api/ingest` |
| `heartbeat_logs` | Log of every received heartbeat POST |

---

## API Reference

All endpoints require `Authorization: Bearer <token>` except `/health` and `/api/auth/login`. Node-to-node endpoints also require `X-Node-Secret` header.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/auth/login` | Returns JWT |
| `GET` | `/api/hosts` | List monitored hosts |
| `POST` | `/api/hosts` | Add a host |
| `PATCH` | `/api/hosts/{id}` | Update label or active status |
| `DELETE` | `/api/hosts/{id}` | Remove host and all its data |
| `POST` | `/api/hosts/seed` | Seed default hosts from env |
| `GET` | `/api/metrics/dashboard` | Aggregated dashboard data |
| `GET` | `/api/metrics/{host_id}/timeseries` | RTT + packet loss history (`?hours=1`) |
| `GET` | `/api/incidents` | List incidents (`?resolved=false`) |
| `POST` | `/api/incidents/{id}/resolve` | Manually resolve an incident |
| `GET` | `/api/topology/graph` | Network graph nodes + edges |
| `GET` | `/api/topology/arp` | Raw ARP table |
| `GET` | `/api/routes` | Route traces (`?host_id=N`) |
| `POST` | `/api/routes/{host_id}/trace` | Trigger manual traceroute |
| `POST` | `/api/ingest` | Probe node submits batch results |
| `GET` | `/api/nodes` | List probe nodes with heartbeat status |
| `POST` | `/api/heartbeat` | Probe node sends heartbeat |
| `GET` | `/health` | Node health — id, role, region |

---

## Environment Variables

Copy `backend/.env.example` to `backend/.env`. Key variables:

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL connection string |
| `SECRET_KEY` | JWT signing key — generate with `openssl rand -hex 32` |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Dashboard login credentials |
| `FRONTEND_URL` | Allowed CORS origin |
| `PROBE_INTERVAL_SECONDS` | How often probes run (default `60`) |
| `DEFAULT_HOSTS` | Comma-separated hosts seeded on `/api/hosts/seed` |
| `SMTP_*` / `SLACK_WEBHOOK_URL` | Alert delivery configuration |
| `NODE_ROLE` | `primary` or `probe` |
| `NODE_ID` / `NODE_LABEL` / `NODE_REGION` | Node identity |
| `NODE_SECRET` | Shared secret for node-to-node auth — generate with `openssl rand -hex 24` |
| `PRIMARY_INGEST_URL` | Probe nodes: URL of the primary to POST results to |
| `PEER_NODE_URLS` | Comma-separated peer URLs for heartbeat |
| `SYSLOG_HOST` | Probe nodes: primary VPS IP for log shipping |
| `PCAP_ENABLED` | Enable Scapy pcap RTT measurement (`true`/`false`) |
| `PCAP_INTERFACE` | Network interface for pcap capture (e.g. `eth0`) |
| `IPTABLES_RATE_LIMIT` | ICMP packets/second per source IP (default `10`) |

---

## Local Development

1. Start PostgreSQL via Docker
2. `cd backend` → create venv → `pip install -r requirements.txt` → `cp .env.example .env` → `uvicorn app.main:app --reload`
3. `cd frontend` → `npm install` → `npm run dev`
4. Login at `http://localhost:5173` — `admin` / `netpulse2026`

> ICMP probing requires root or `NET_RAW` capability on Linux.

---

## Production Deployment

**Primary VM (VM 1)** — Run `sudo bash infra/setup_vps.sh`. Set `NODE_ROLE=primary` in `.env`. Start with systemd (`netpulse.service`). Obtain TLS cert with Certbot.

**Probe VM (VM 2)** — Run `sudo bash infra/setup_probe_node.sh` (no PostgreSQL installed). Set `NODE_ROLE=probe`, `PRIMARY_INGEST_URL`, `PEER_NODE_URLS`, and `SYSLOG_HOST` in `.env`.

**Frontend** — Deploy `frontend/` to Vercel. Set `VITE_API_URL=https://your-primary-domain.com`. The `vercel.json` includes an SPA rewrite rule for React Router.

---

## Security

- **TLS** — Nginx terminates HTTPS with Let's Encrypt. HTTP redirects to HTTPS. TLS 1.2/1.3 only, with security headers (`X-Frame-Options`, `HSTS`, `X-Content-Type-Options`).
- **Firewall** — UFW allows only 22, 80, 443. Probe node additionally opens 8000 for heartbeat.
- **ICMP rate limiting** — iptables hashlimit applied on startup: 10 pps per source IP, burst 20.
- **JWT** — HS256, 24-hour expiry. Node-to-node auth uses a separate `X-Node-Secret` header.
- **Passwords** — bcrypt-hashed (bcrypt 4.0.1 pinned).

> ⚠️ Change all default credentials (`ADMIN_PASSWORD`, `SECRET_KEY`, `NODE_SECRET`) before any public deployment.

---

## Default Credentials

| | Value |
|-|-------|
| Admin login | `admin` / `netpulse2026` |
| PostgreSQL | `netpulse` / `netpulse_pass` / db `netpulse` |