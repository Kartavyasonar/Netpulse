"""
Route Tracer & Path Analyser — Feature 3
==========================================
Maps the hop-by-hop path packets take to reach a target host.
Detects routing changes by diffing against the previous run.

TECHNICAL EXPLANATION (for interviews):
  Traceroute exploits the IP TTL (Time To Live) field.
  TTL is decremented by each router. When TTL reaches 0,
  the router drops the packet and sends back ICMP Time Exceeded
  (type=11, code=0) — which reveals the router's IP address.

  Algorithm:
    Send probe with TTL=1  → first hop router replies with ICMP TTL exceeded
    Send probe with TTL=2  → second hop router replies
    ... repeat until target host replies with ICMP Echo Reply (type=0)

  We send UDP probes (like traditional traceroute) or ICMP Echo Requests.
  Each hop's RTT = time from sending probe to receiving ICMP reply.

  Path deviation detection: we store each trace in PostgreSQL as a JSON
  array of {ttl, ip, rtt_ms} objects and diff consecutive runs.
"""

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

logger = logging.getLogger("netpulse.prober.route")

MAX_HOPS = 30
PROBE_TIMEOUT = 2.0  # seconds per hop


@dataclass
class Hop:
    ttl: int
    ip: Optional[str]         # None if no reply (timeout = *)
    rtt_ms: Optional[float]
    hostname: Optional[str] = None


@dataclass
class TraceResult:
    target: str
    hops: List[Hop]
    reached_target: bool
    total_hops: int
    error: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps([asdict(h) for h in self.hops])


async def traceroute(target: str, max_hops: int = MAX_HOPS) -> TraceResult:
    """
    Perform a traceroute to `target` using system traceroute command.
    Falls back to a pure-Python TTL-incrementing approach if unavailable.
    """
    try:
        return await _system_traceroute(target, max_hops)
    except Exception as e:
        logger.warning(f"System traceroute failed for {target}: {e}, trying Python impl")
        return await _python_traceroute(target, max_hops)


async def _system_traceroute(target: str, max_hops: int) -> TraceResult:
    """
    Run system `traceroute -n -m {max_hops} {target}` and parse output.
    -n flag skips reverse DNS lookups (faster, uses raw IPs).
    """
    loop = asyncio.get_event_loop()

    def run_trace():
        try:
            result = subprocess.run(
                ["traceroute", "-n", "-m", str(max_hops), "-w", "2", target],
                capture_output=True, text=True, timeout=60
            )
            return result.stdout, result.returncode
        except FileNotFoundError:
            # Try tracepath on some Linux distros
            result = subprocess.run(
                ["tracepath", "-n", target],
                capture_output=True, text=True, timeout=60
            )
            return result.stdout, result.returncode

    output, rc = await loop.run_in_executor(None, run_trace)
    hops = _parse_traceroute_output(output)

    reached = any(
        h.ip == target or
        (h.ip and _is_same_host(h.ip, target))
        for h in hops
    )

    return TraceResult(
        target=target,
        hops=hops,
        reached_target=reached,
        total_hops=len(hops),
    )


def _parse_traceroute_output(output: str) -> List[Hop]:
    """
    Parse traceroute output lines like:
      1  192.168.1.1  1.234 ms  1.100 ms  1.050 ms
      2  10.0.0.1     5.678 ms  5.500 ms  5.600 ms
      3  * * *         (timeout, no reply)
    """
    hops = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue

        parts = line.split()
        if not parts or not parts[0].isdigit():
            continue

        ttl = int(parts[0])

        # Check for timeout (all stars)
        if len(parts) >= 2 and parts[1] == "*":
            hops.append(Hop(ttl=ttl, ip=None, rtt_ms=None))
            continue

        # Extract IP and first RTT
        ip = None
        rtt = None
        if len(parts) >= 2:
            ip = parts[1] if not parts[1].startswith("*") else None

        # Find first RTT value (look for "ms" unit)
        for i, part in enumerate(parts):
            if part == "ms" and i > 0:
                try:
                    rtt = float(parts[i - 1])
                    break
                except ValueError:
                    pass

        hops.append(Hop(ttl=ttl, ip=ip, rtt_ms=rtt))

    return hops


async def _python_traceroute(target: str, max_hops: int) -> TraceResult:
    """
    Pure Python traceroute using raw sockets (needs CAP_NET_RAW).
    Sends UDP datagrams with incrementing TTL values.
    Listens for ICMP Time Exceeded replies to identify routers.
    """
    import socket
    import struct
    import time
    import ipaddress

    # Resolve target to IP
    try:
        target_ip = socket.gethostbyname(target)
    except socket.gaierror:
        return TraceResult(
            target=target,
            hops=[],
            reached_target=False,
            total_hops=0,
            error=f"DNS resolution failed for {target}",
        )

    hops = []
    loop = asyncio.get_event_loop()

    def do_trace():
        results = []
        dest_port = 33434  # Traditional traceroute UDP port range starts here

        # Raw ICMP socket to receive Time Exceeded messages
        try:
            recv_sock = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
            recv_sock.settimeout(PROBE_TIMEOUT)
        except PermissionError:
            return []

        try:
            for ttl in range(1, max_hops + 1):
                # UDP socket with specific TTL
                send_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                send_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)

                send_time = time.perf_counter()
                try:
                    # Send empty UDP packet — TTL will expire at each router
                    send_sock.sendto(b"", (target_ip, dest_port + ttl))
                finally:
                    send_sock.close()

                # Wait for ICMP reply
                hop_ip = None
                hop_rtt = None
                try:
                    data, addr = recv_sock.recvfrom(512)
                    recv_time = time.perf_counter()
                    hop_ip = addr[0]
                    hop_rtt = round((recv_time - send_time) * 1000, 2)
                except socket.timeout:
                    pass

                results.append(Hop(ttl=ttl, ip=hop_ip, rtt_ms=hop_rtt))

                # Stop if we reached the target
                if hop_ip == target_ip:
                    break
        finally:
            recv_sock.close()

        return results

    hops = await loop.run_in_executor(None, do_trace)
    reached = any(h.ip == target_ip for h in hops if h.ip)

    return TraceResult(
        target=target,
        hops=hops,
        reached_target=reached,
        total_hops=len(hops),
    )


def _is_same_host(ip1: str, ip2: str) -> bool:
    """Check if ip2 resolves to ip1."""
    try:
        import socket
        resolved = socket.gethostbyname(ip2)
        return ip1 == resolved
    except Exception:
        return False


def diff_routes(old_hops_json: str, new_hops_json: str) -> Tuple[bool, str]:
    """
    Compare two hop sequences (stored as JSON strings).
    Returns (changed: bool, diff_summary: str).

    We compare the IP sequence of non-None hops.
    A changed hop count or different intermediate IP = routing change.
    """
    try:
        old_hops = json.loads(old_hops_json) if old_hops_json else []
        new_hops = json.loads(new_hops_json) if new_hops_json else []
    except json.JSONDecodeError:
        return False, ""

    old_ips = [h.get("ip") for h in old_hops if h.get("ip")]
    new_ips = [h.get("ip") for h in new_hops if h.get("ip")]

    if old_ips == new_ips:
        return False, ""

    # Build human-readable diff
    lines = []
    if len(old_ips) != len(new_ips):
        lines.append(f"Hop count changed: {len(old_ips)} → {len(new_ips)}")

    for i, (old_ip, new_ip) in enumerate(zip(old_ips, new_ips)):
        if old_ip != new_ip:
            lines.append(f"Hop {i+1}: {old_ip} → {new_ip}")

    # New hops beyond old length
    for i in range(len(old_ips), len(new_ips)):
        lines.append(f"New hop {i+1}: {new_ips[i]}")

    summary = "; ".join(lines) if lines else "Route structure changed"
    return True, summary
