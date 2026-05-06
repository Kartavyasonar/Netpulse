#!/bin/bash
# NetPulse Probe Node Setup — Second Oracle Cloud VPS
# Run as root on your SECOND VPS: bash setup_probe_node.sh
# 
# Difference from setup_vps.sh:
#   - No PostgreSQL needed (probe nodes don't store data locally)
#   - NODE_ROLE=probe in .env
#   - Sets PRIMARY_INGEST_URL to point to your primary VPS
#   - Lighter footprint

set -euo pipefail

echo "=== NetPulse Probe Node Setup ==="
echo "This is a SECONDARY probe node — no DB, just probing + shipping"

# 1. System deps
apt-get update && apt-get install -y \
  python3.11 python3.11-venv python3-pip \
  libpcap-dev nmap traceroute iputils-ping iproute2 \
  git ufw curl iptables-persistent

# 2. Firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 443/tcp
# Allow heartbeat endpoint
ufw allow 8000/tcp
ufw --force enable

# 3. Service user
id -u netpulse &>/dev/null || useradd --system --no-create-home --shell /bin/false netpulse

# 4. App setup
mkdir -p /opt/netpulse
git clone https://github.com/YOUR_USERNAME/netpulse.git /opt/netpulse || \
  (cd /opt/netpulse && git pull)

python3.11 -m venv /opt/netpulse/venv
/opt/netpulse/venv/bin/pip install --upgrade pip
/opt/netpulse/venv/bin/pip install -r /opt/netpulse/backend/requirements.txt

# 5. Configure probe node .env
cat > /opt/netpulse/backend/.env << 'EOF'
# PROBE NODE CONFIGURATION
NODE_ROLE=probe
NODE_ID=frankfurt-01
NODE_LABEL=Frankfurt Probe Node
NODE_REGION=eu-frankfurt-1

# Point to your primary VPS
PRIMARY_INGEST_URL=https://YOUR_PRIMARY_DOMAIN.com
NODE_SECRET=CHANGE_THIS_SAME_SECRET_AS_PRIMARY

# Heartbeat — tell primary we're alive
PEER_NODE_URLS=https://YOUR_PRIMARY_DOMAIN.com

# What to probe (same or different hosts from primary)
DEFAULT_HOSTS=8.8.8.8,1.1.1.1,google.com,github.com,cloudflare.com

# Logging — ship WARNING+ logs to primary
SYSLOG_HOST=YOUR_PRIMARY_VPS_IP
LOG_LEVEL=INFO

# No DB needed on probe nodes — use a dummy URL
DATABASE_URL=postgresql+asyncpg://netpulse:netpulse_pass@localhost:5432/netpulse
EOF

echo "EDIT /opt/netpulse/backend/.env with your actual values!"

# 6. iptables ICMP rate limiting (Change 5)
cp /opt/netpulse/infra/rules.v4 /etc/iptables/rules.v4
netfilter-persistent reload

# 7. CAP_NET_RAW for ICMP
setcap cap_net_raw+ep /opt/netpulse/venv/bin/python3.11

# 8. Systemd service
cat > /etc/systemd/system/netpulse-probe.service << 'EOF'
[Unit]
Description=NetPulse Probe Node
After=network.target

[Service]
Type=exec
User=netpulse
WorkingDirectory=/opt/netpulse/backend
EnvironmentFile=/opt/netpulse/backend/.env
ExecStart=/opt/netpulse/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
Restart=on-failure
RestartSec=10
AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN
CapabilityBoundingSet=CAP_NET_RAW CAP_NET_ADMIN
StandardOutput=journal
StandardError=journal
SyslogIdentifier=netpulse-probe

[Install]
WantedBy=multi-user.target
EOF

chown -R netpulse:netpulse /opt/netpulse
systemctl daemon-reload
systemctl enable netpulse-probe
systemctl start netpulse-probe

echo ""
echo "=== Probe Node Setup Complete ==="
echo "Check status: systemctl status netpulse-probe"
echo "View logs: journalctl -u netpulse-probe -f"
echo ""
echo "On your PRIMARY node, add this to .env:"
echo "PEER_NODE_URLS=http://$(curl -s ifconfig.me):8000"
