from pydantic_settings import BaseSettings
from typing import List
import os


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://netpulse:netpulse_pass@localhost:5432/netpulse"
    )

    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "CHANGE_THIS_IN_PRODUCTION_USE_OPENSSL_RAND")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Admin credentials
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "netpulse2026")

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        os.getenv("FRONTEND_URL", "https://netpulse.vercel.app"),
    ]

    # Probe interval
    PROBE_INTERVAL_SECONDS: int = int(os.getenv("PROBE_INTERVAL_SECONDS", "60"))

    # Anomaly detection
    ANOMALY_SIGMA_THRESHOLD: float = 2.0
    BASELINE_WINDOW_MINUTES: int = 60

    # Alerting
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    ALERT_FROM_EMAIL: str = os.getenv("ALERT_FROM_EMAIL", "alerts@netpulse.local")
    ALERT_TO_EMAIL: str = os.getenv("ALERT_TO_EMAIL", "")
    SLACK_WEBHOOK_URL: str = os.getenv("SLACK_WEBHOOK_URL", "")

    # Default hosts
    DEFAULT_HOSTS: str = os.getenv(
        "DEFAULT_HOSTS",
        "8.8.8.8,1.1.1.1,8.8.4.4,google.com,github.com,cloudflare.com"
    )

    # ── Change 1: Distributed probe node settings ─────────────────────────
    # Set NODE_ROLE=probe on secondary VMs, NODE_ROLE=primary on main VPS
    NODE_ROLE: str = os.getenv("NODE_ROLE", "primary")
    NODE_ID: str = os.getenv("NODE_ID", "primary-01")
    NODE_LABEL: str = os.getenv("NODE_LABEL", "Primary Node")
    NODE_REGION: str = os.getenv("NODE_REGION", "us-ashburn-1")

    # Primary node URL — probe nodes POST results here
    PRIMARY_INGEST_URL: str = os.getenv("PRIMARY_INGEST_URL", "")
    # Shared secret for node-to-node auth
    NODE_SECRET: str = os.getenv("NODE_SECRET", "CHANGE_THIS_NODE_SECRET")

    # ── Change 2: Dead-man's switch ───────────────────────────────────────
    HEARTBEAT_INTERVAL_SECONDS: int = 30
    HEARTBEAT_MISS_THRESHOLD: int = 3    # alert after 3 missed = 90s silence
    # Peer node URLs to send heartbeats to (comma-separated)
    PEER_NODE_URLS: str = os.getenv("PEER_NODE_URLS", "")

    # ── Change 3: Structured logging ──────────────────────────────────────
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    # Syslog forwarding: set SYSLOG_HOST=primary-vps-ip to ship logs
    SYSLOG_HOST: str = os.getenv("SYSLOG_HOST", "")
    SYSLOG_PORT: int = int(os.getenv("SYSLOG_PORT", "514"))

    # ── Change 4: pcap integration ────────────────────────────────────────
    PCAP_ENABLED: bool = os.getenv("PCAP_ENABLED", "false").lower() == "true"
    PCAP_INTERFACE: str = os.getenv("PCAP_INTERFACE", "eth0")

    # ── Change 5: iptables rate limiting ─────────────────────────────────
    IPTABLES_RATE_LIMIT: int = int(os.getenv("IPTABLES_RATE_LIMIT", "10"))  # pps

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
