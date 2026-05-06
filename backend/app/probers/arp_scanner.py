"""
ARP Table Scanner & Topology Mapper — Feature 2
=================================================
Reads the Linux ARP cache from /proc/net/arp to get
MAC-to-IP mappings of devices on the local network.

TECHNICAL EXPLANATION (for interviews):
  ARP (Address Resolution Protocol) operates at Layer 2/3 boundary.
  When host A wants to reach host B on the same subnet:
    1. A broadcasts: "Who has 192.168.1.10? Tell 192.168.1.1"  (ARP Request)
    2. B replies:    "192.168.1.10 is at aa:bb:cc:dd:ee:ff"    (ARP Reply)
    3. A caches this MAC-IP binding in its ARP table

  Linux stores this cache in /proc/net/arp (kernel virtual filesystem).
  Format: IP address | HW type | Flags | HW address | Mask | Device

  Flags:
    0x0 = incomplete entry
    0x2 = entry is complete (REACHABLE)
    0x4 = entry is published (proxy ARP)

  We parse this file directly — zero network traffic, reads kernel state.
  We also compare snapshots over time to detect new/disappeared devices.
"""

import subprocess
import logging
import asyncio
from dataclasses import dataclass
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger("netpulse.prober.arp")

ARP_CACHE_FILE = "/proc/net/arp"

ARP_FLAG_MAP = {
    "0x0": "INCOMPLETE",
    "0x2": "REACHABLE",
    "0x4": "PUBLISHED",
    "0x6": "PERMANENT",
}


@dataclass
class ARPRecord:
    ip_address: str
    mac_address: str
    interface: str
    state: str
    hw_type: str        # 0x1 = Ethernet
    scanned_at: datetime = None

    def __post_init__(self):
        if self.scanned_at is None:
            self.scanned_at = datetime.utcnow()


def parse_proc_arp() -> List[ARPRecord]:
    """
    Parse /proc/net/arp directly.

    File format (first line is header):
    IP address       HW type     Flags       HW address            Mask     Device
    192.168.1.1      0x1         0x2         aa:bb:cc:dd:ee:ff     *        eth0
    """
    records = []
    try:
        with open(ARP_CACHE_FILE, "r") as f:
            lines = f.readlines()

        # Skip header line
        for line in lines[1:]:
            parts = line.split()
            if len(parts) < 6:
                continue

            ip_addr, hw_type, flags, hw_addr, mask, device = parts[:6]

            # Skip incomplete entries (0x0 flag) and broadcast addresses
            if flags == "0x0" or hw_addr == "00:00:00:00:00:00":
                continue

            state = ARP_FLAG_MAP.get(flags, f"UNKNOWN({flags})")

            records.append(ARPRecord(
                ip_address=ip_addr,
                mac_address=hw_addr.upper(),
                interface=device,
                state=state,
                hw_type=hw_type,
            ))

    except FileNotFoundError:
        logger.warning(f"{ARP_CACHE_FILE} not found — not running on Linux?")
        # On non-Linux, try `arp -n` command
        records = _parse_arp_command()
    except PermissionError as e:
        logger.error(f"Cannot read {ARP_CACHE_FILE}: {e}")

    return records


def _parse_arp_command() -> List[ARPRecord]:
    """Fallback: parse `arp -n` output (works on macOS/FreeBSD too)."""
    records = []
    try:
        result = subprocess.run(
            ["arp", "-n"],
            capture_output=True, text=True, timeout=5
        )
        for line in result.stdout.splitlines()[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 3 and parts[1] not in ("(incomplete)", "at"):
                # Linux arp -n: IP, HWtype, HWaddress, Flags, Iface
                if len(parts) >= 5:
                    records.append(ARPRecord(
                        ip_address=parts[0],
                        hw_type="0x1",
                        mac_address=parts[2].upper(),
                        interface=parts[4] if len(parts) > 4 else "unknown",
                        state="REACHABLE",
                    ))
    except Exception as e:
        logger.error(f"arp command failed: {e}")
    return records


def diff_arp_tables(
    previous: List[ARPRecord],
    current: List[ARPRecord]
) -> Dict[str, List[ARPRecord]]:
    """
    Compare two ARP table snapshots.
    Returns dicts of new/disappeared/changed entries.
    """
    prev_map = {r.ip_address: r for r in previous}
    curr_map = {r.ip_address: r for r in current}

    new_hosts = [
        curr_map[ip] for ip in curr_map
        if ip not in prev_map
    ]
    disappeared_hosts = [
        prev_map[ip] for ip in prev_map
        if ip not in curr_map
    ]
    mac_changed = [
        curr_map[ip] for ip in curr_map
        if ip in prev_map and curr_map[ip].mac_address != prev_map[ip].mac_address
        # MAC change on same IP = possible ARP spoofing!
    ]

    if mac_changed:
        logger.warning(
            f"ARP SPOOFING ALERT: MAC address changed for {[r.ip_address for r in mac_changed]}"
        )

    return {
        "new": new_hosts,
        "disappeared": disappeared_hosts,
        "mac_changed": mac_changed,
    }


async def scan_arp_table() -> List[ARPRecord]:
    """Async wrapper — runs parse in thread pool to avoid blocking event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, parse_proc_arp)


def get_gateway_ip() -> Optional[str]:
    """
    Read default gateway from /proc/net/route.
    The gateway is the first hop for traffic leaving the local subnet.
    Destination=00000000 means default route (0.0.0.0/0).
    """
    try:
        with open("/proc/net/route") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) >= 3 and parts[1] == "00000000":
                    # Gateway field is hex little-endian 32-bit IP
                    gw_hex = parts[2]
                    gw_int = int(gw_hex, 16)
                    # Convert little-endian hex to dotted decimal
                    octets = [
                        (gw_int >> 0) & 0xFF,
                        (gw_int >> 8) & 0xFF,
                        (gw_int >> 16) & 0xFF,
                        (gw_int >> 24) & 0xFF,
                    ]
                    return ".".join(str(o) for o in octets)
    except Exception as e:
        logger.warning(f"Could not read gateway from /proc/net/route: {e}")

    # Fallback: parse `ip route` output
    try:
        result = subprocess.run(
            ["ip", "route", "show", "default"],
            capture_output=True, text=True, timeout=3
        )
        # Output: "default via 192.168.1.1 dev eth0 ..."
        parts = result.stdout.split()
        if "via" in parts:
            return parts[parts.index("via") + 1]
    except Exception:
        pass
    return None
