FROM python:3.11-slim

# Install system deps for scapy, icmplib, nmap, traceroute
RUN apt-get update && apt-get install -y \
    libpcap-dev \
    nmap \
    traceroute \
    iputils-ping \
    iproute2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Grant CAP_NET_RAW to Python for ICMP raw sockets
RUN setcap cap_net_raw+ep /usr/local/bin/python3.11 || true

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
