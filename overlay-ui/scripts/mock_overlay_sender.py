import json
import socket
import time

TARGET = ("127.0.0.1", 38485)

STATES = [
    {
        "connection": "online",
        "listening": "listening",
        "processing": "idle",
        "target": "selected",
        "level": 0.02,
        "visible": True,
        "message": None,
    },
    {
        "connection": "online",
        "listening": "listening",
        "processing": "idle",
        "target": "selected",
        "level": 0.72,
        "visible": True,
        "message": None,
    },
    {
        "connection": "online",
        "listening": "ready",
        "processing": "processing",
        "target": "selected",
        "level": 0.0,
        "visible": True,
        "message": None,
    },
]


def send(payload: dict) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(json.dumps(payload).encode("utf-8"), TARGET)


def main() -> None:
    i = 0
    while True:
        send(STATES[i % len(STATES)])
        i += 1
        time.sleep(1.4)


if __name__ == "__main__":
    main()
