import argparse
from .gui import run_host_gui, run_client_gui


def main() -> None:
    parser = argparse.ArgumentParser(description="Versus - 1v1 LAN games with lobby selection")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    host_p = subparsers.add_parser("host", help="Host a game session")
    host_p.add_argument("--bind", type=str, default="0.0.0.0", help="Bind address")
    host_p.add_argument("--port", type=int, default=5000, help="TCP port to listen on")

    join_p = subparsers.add_parser("join", help="Join a host")
    join_p.add_argument("--address", type=str, required=True, help="Host IP or address")
    join_p.add_argument("--port", type=int, default=5000, help="TCP port to connect")

    args = parser.parse_args()

    if args.mode == "host":
        run_host_gui(port=args.port, bind=args.bind)
    elif args.mode == "join":
        run_client_gui(host=args.address, port=args.port)
