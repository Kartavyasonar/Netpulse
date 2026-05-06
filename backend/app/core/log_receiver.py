"""
Log receiver — runs on primary node to ingest logs from probe nodes.
Starts a TCP server on port 9020 that receives pickled log records
from remote Python SocketHandlers and re-emits into local logging.

Run standalone: python -m app.core.log_receiver
Or it's started automatically by the primary node on startup.
"""
import logging
import logging.handlers
import pickle
import socketserver
import struct
import threading

from app.core.logging_setup import JSONFormatter

logger = logging.getLogger("netpulse.log_receiver")


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
    """
    Handles a TCP connection from a remote SocketHandler.
    Reads 4-byte big-endian length prefix, then unpickles the log record.
    Re-emits it into the local logging system with node attribution.
    """

    def handle(self):
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = b""
            while len(chunk) < slen:
                chunk += self.connection.recv(slen - len(chunk))
            try:
                record = logging.makeLogRecord(pickle.loads(chunk))
                # Tag the record with the remote IP
                record.__dict__["remote_ip"] = self.client_address[0]
                logging.getLogger(record.name).handle(record)
            except Exception as e:
                logger.error(f"Failed to process remote log record: {e}")


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host="0.0.0.0", port=9020):
        super().__init__((host, port), LogRecordStreamHandler)


def start_log_receiver_thread(port: int = 9020) -> threading.Thread:
    """Start log receiver in a daemon thread — called by primary node startup."""
    server = LogRecordSocketReceiver(port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Log receiver listening on TCP :{port}")
    return thread


if __name__ == "__main__":
    # Standalone mode
    import sys
    from app.core.logging_setup import setup_logging
    setup_logging()
    logger.info("Starting standalone log receiver on :9020")
    server = LogRecordSocketReceiver()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
