#!/bin/bash
# NetPulse VPS Setup Script — Oracle Cloud Ubuntu 22.04
# Run as root: bash setup_vps.sh

set -euo pipefail

echo "=== NetPulse VPS Setup ==="

# 1. Update system
apt-get update && apt-get upgrade -y

# 2. Install system dependencies
apt-get install -y \
  python3.11 python3.11-venv python3-pip \
  postgresql postgresql-contrib \
  nginx certbot python3-certbot-nginx \
  libpcap-dev nmap traceroute iputils-ping iproute2 \
  git ufw curl

# 3. Configure UFW firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable
echo "Firewall configured"

# 4. Create netpulse system user
id -u netpulse &>/dev/null || useradd --system --no-create-home --shell /bin/false netpulse
echo "Service user created"

# 5. Set up PostgreSQL
sudo -u postgres psql <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'netpulse') THEN
    CREATE ROLE netpulse WITH LOGIN PASSWORD 'netpulse_pass';
  END IF;
END
\$\$;
CREATE DATABASE netpulse OWNER netpulse;
EOF
echo "PostgreSQL configured"

# 6. Set up app directory
mkdir -p /opt/netpulse
git clone https://github.com/YOUR_USERNAME/netpulse.git /opt/netpulse || true

# 7. Python virtual environment
python3.11 -m venv /opt/netpulse/venv
/opt/netpulse/venv/bin/pip install --upgrade pip
/opt/netpulse/venv/bin/pip install -r /opt/netpulse/backend/requirements.txt

# 8. Copy .env
cp /opt/netpulse/backend/.env.example /opt/netpulse/backend/.env
echo "EDIT /opt/netpulse/backend/.env with your real values!"

# 9. Grant CAP_NET_RAW to Python (for ICMP)
setcap cap_net_raw+ep /opt/netpulse/venv/bin/python3.11

# 10. Install systemd service
cp /opt/netpulse/infra/netpulse.service /etc/systemd/system/
chown -R netpulse:netpulse /opt/netpulse
systemctl daemon-reload
systemctl enable netpulse
systemctl start netpulse
echo "Systemd service started"

# 11. Nginx config
cp /opt/netpulse/infra/nginx.conf /etc/nginx/conf.d/netpulse.conf
nginx -t && systemctl reload nginx

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Edit /opt/netpulse/backend/.env"
echo "2. Run: certbot --nginx -d your-domain.com"
echo "3. systemctl restart netpulse"
echo "4. Visit https://your-domain.com/docs"
