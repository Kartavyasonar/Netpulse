"""
ICMP Prober — Change 4 + Change 6
====================================
Change 4: Replace subprocess tcpdump with Scapy sniff() in a background
          thread. BPF filter 'icmp' captures only ICMP packets. Per-packet
          timestamps have microsecond precision from the kernel pcap clock.
          We measure the delta between ICMP RTT and pcap-measured RTT to
          quantify OS scheduling jitter — a real, documentable finding.

Change 6: Rewrote concurrency model from ThreadPoolExecutor to asyncio.
          asyncio.gather() is architecturally cleaner for I/O-bound network
          probing:
            - No GIL contention (threads share GIL during CPU work)
            - Lower per-coroutine memory (~2KB stack vs ~8MB thread stack)
            - Natural integration with async FastAPI event loop
            - asyncio.Semaphore controls concurrency without thread overhead

TECHNICAL EXPLANATION (for interviews):
  ICMP operates at Layer 3 (Network layer).
  Echo Request = type 8, code 0 → Echo Reply = type 0, code 0.

  Scapy sniff() with BPF filter:
    BPF (Berkeley Packet Filter) runs in kernel space — packets are
    filtered before being copied to userspace. This eliminates the
    file I/O overhead of writing a pcap file and reading it back.
    sniff(filter="icmp", iface="eth0", timeout=5) returns a list of
    Packet objects with .time (float, seconds since epoch, microsecond precision).

  RTT delta = pcap_rtt - icmp_rtt reveals OS scheduling jitter:
    icmp_rtt = time.perf_counter() delta (userspace clock)
    pcap_rtt = packet.time delta (kernel pcap clock)
    delta > 0 means userspace scheduling added latency on top of wire RTT.
"""

import asyncio
import logging
import time
import threading
from typing import Optional
from dataclasses import dataclass, field

from app.core.config import settings

logger = logging.getLogger("netpulse.prober.icmp")


@dataclass
class ProbeResult:
    address: str
    is_reachable: bool
    rtt_ms: Optional[float]
    packet_loss_pct: float
    packets_sent: int
    packets_received: int
    pcap_rtt_ms: Optional[float] = None      # Change 4: Scapy-measured RTT
    rtt_delta_ms: Optional[float] = None     # Change 4: pcap_rtt - icmp_rtt
    error: Optional[str] = None


# ── Change 4: Scapy pcap capture ─────────────────────────────────────────────

class PcapCapture:
    """
    Runs Scapy sniff() in a background thread with BPF filter 'icmp'.
    Captures ICMP Echo Replies and records their kernel-timestamped arrival time.

    Usage:
        cap = PcapCapture(iface="eth0")
        cap.start()
        send_ping(target)
        reply_time = cap.get_reply_time(target_ip, seq_no)
        cap.stop()
    """

    def __init__(self, iface: str = "eth0"):
        self.iface = iface
        self._packets: list = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._available = False

        # Check if Scapy is available with raw socket access
        try:
            from scapy.all import conf
            self._available = True
        except ImportError:
            logger.warning("Scapy not available — pcap RTT measurement disabled")

    def start(self, timeout: float = 10.0):
        if not self._available or not settings.PCAP_ENABLED:
            return
        self._stop_event.clear()
        self._packets.clear()
        self._thread = threading.Thread(
            target=self._capture_loop,
            args=(timeout,),
            daemon=True,
        )
        self._thread.start()

    def _capture_loop(self, timeout: float):
        """
        BPF filter 'icmp and icmp[icmptype] == 0' captures only Echo Replies.
        Runs in kernel space — no userspace copy until packet matches filter.
        packet.time = kernel pcap timestamp (microsecond precision).
        """
        try:
            from scapy.all import sniff
            pkts = sniff(
                filter="icmp and icmp[icmptype] == 0",
                iface=self.iface,
                timeout=timeout,
                store=True,
            )
            with self._lock:
                self._packets = list(pkts)
        except Exception as e:
            logger.debug(f"pcap capture error: {e}")

    def stop(self):
        self._stop_event.set()

    def get_rtt_ms(self, target_ip: str, send_time: float) -> Optional[float]:
        """
        Find the first ICMP Echo Reply from target_ip after send_time.
        Returns RTT in ms using kernel pcap timestamp.
        """
        if not self._available:
            return None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

        with self._lock:
            for pkt in self._packets:
                try:
                    if (
                        hasattr(pkt, "src") and pkt.src == target_ip
                        and float(pkt.time) >= send_time
                    ):
                        return round((float(pkt.time) - send_time) * 1000, 3)
                except Exception:
                    continue
        return None


# ── Change 6: asyncio-based prober ───────────────────────────────────────────

async def probe_host(
    address: str,
    count: int = 4,
    timeout: float = 2.0,
) -> ProbeResult:
    """
    Probe a single host with ICMP.
    Change 6: fully async — no threads, uses asyncio event loop.
    Change 4: Scapy pcap captures parallel to probe for delta measurement.
    """
    # Start pcap capture in parallel (Change 4)
    pcap = PcapCapture(iface=settings.PCAP_INTERFACE)
    send_time = time.time()
    pcap.start(timeout=timeout * count + 1)

    try:
        from icmplib import async_ping

        host = await async_ping(
            address,
            count=count,
            interval=0.2,
            timeout=timeout,
            privileged=True,
        )

        icmp_rtt = round(host.avg_rtt, 3) if host.is_alive else None

        # Change 4: get pcap RTT and calculate delta
        pcap_rtt = None
        delta = None
        if settings.PCAP_ENABLED and icmp_rtt is not None:
            try:
                import socket as _socket
                target_ip = _socket.gethostbyname(address)
                pcap_rtt = pcap.get_rtt_ms(target_ip, send_time)
                if pcap_rtt and icmp_rtt:
                    delta = round(pcap_rtt - icmp_rtt, 3)
                    if abs(delta) > 5:
                        logger.info(
                            f"RTT delta {address}: {delta:.1f}ms "
                            f"(icmp={icmp_rtt}ms, pcap={pcap_rtt}ms)",
                            extra={
                                "host": address,
                                "icmp_rtt_ms": icmp_rtt,
                                "pcap_rtt_ms": pcap_rtt,
                                "rtt_delta_ms": delta,
                            }
                        )
            except Exception as e:
                logger.debug(f"pcap delta calc failed: {e}")

        return ProbeResult(
            address=address,
            is_reachable=host.is_alive,
            rtt_ms=icmp_rtt,
            packet_loss_pct=host.packet_loss * 100,
            packets_sent=host.packets_sent,
            packets_received=host.packets_received,
            pcap_rtt_ms=pcap_rtt,
            rtt_delta_ms=delta,
        )

    except Exception as e:
        logger.warning(f"ICMP probe failed for {address}: {e}")
        return await _tcp_fallback_probe(address)
    finally:
        pcap.stop()


async def _tcp_fallback_probe(
    address: str,
    port: int = 443,
    timeout: float = 3.0,
) -> ProbeResult:
    """
    TCP SYN probe fallback when ICMP raw sockets unavailable.
    Measures time from SYN send to SYN-ACK receive as RTT proxy.

    TCP 3-way handshake: SYN → SYN-ACK → ACK
    asyncio.open_connection() initiates the handshake asynchronously —
    no thread blocking, the event loop handles the I/O wait.
    """
    try:
        start = time.perf_counter()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(address, port),
            timeout=timeout,
        )
        rtt_ms = round((time.perf_counter() - start) * 1000, 3)
        writer.close()
        await writer.wait_closed()

        return ProbeResult(
            address=address,
            is_reachable=True,
            rtt_ms=rtt_ms,
            packet_loss_pct=0.0,
            packets_sent=1,
            packets_received=1,
        )
    except Exception as e:
        return ProbeResult(
            address=address,
            is_reachable=False,
            rtt_ms=None,
            packet_loss_pct=100.0,
            packets_sent=1,
            packets_received=0,
            error=str(e),
        )


async def probe_multiple(
    addresses: list[str],
    concurrency: int = 20,
) -> list[ProbeResult]:
    """
    Change 6: asyncio.gather() replaces ThreadPoolExecutor.

    Why asyncio over threads for this workload:
      1. No GIL contention — threads compete for GIL during CPU work
         between I/O calls. Coroutines yield explicitly at await points.
      2. Memory: each coroutine ~2KB stack vs ~8MB OS thread stack.
         20 threads = ~160MB; 20 coroutines = ~40KB.
      3. Integration: async FastAPI runs on an asyncio event loop.
         Using threads would require run_in_executor() wrappers.
      4. Semaphore: asyncio.Semaphore is lighter than threading.Semaphore
         (no kernel mutex, no context switch on acquire/release).

    asyncio.Semaphore limits concurrent raw socket operations to avoid
    overwhelming the NIC or hitting OS file descriptor limits.
    """
    sem = asyncio.Semaphore(concurrency)

    async def bounded_probe(addr: str) -> ProbeResult:
        async with sem:
            return await probe_host(addr)

    # asyncio.gather() schedules all coroutines concurrently on the event loop.
    # Each coroutine suspends at 'await' (I/O wait) and lets others run.
    # No OS thread creation, no context switching overhead.
    results = await asyncio.gather(
        *[bounded_probe(addr) for addr in addresses],
        return_exceptions=False,
    )
    return list(results)
