import argparse
from .host import run_host
from .client import run_client
from .gui import run_host_gui, run_client_gui

def main() -> None:
    parser = argparse.ArgumentParser(description="Battleship LAN (terminal)")
    subparsers = parser.add_subparsers(dest="mode", required=True)

    host_p = subparsers.add_parser("host", help="Run as host (waits for a player)")
    host_p.add_argument("--port", type=int, default=5000, help="TCP port to listen on")
    host_p.add_argument("--bind", type=str, default="0.0.0.0", help="Bind address")

    join_p = subparsers.add_parser("join", help="Join a host")
    join_p.add_argument("--host", type=str, required=True, help="Host IP or name")
    join_p.add_argument("--port", type=int, default=5000, help="TCP port to connect")

    # GUI modes
    host_gui = subparsers.add_parser("host-gui", help="Run as host with GUI")
    host_gui.add_argument("--port", type=int, default=5000, help="TCP port to listen on")
    host_gui.add_argument("--bind", type=str, default="0.0.0.0", help="Bind address")

    join_gui = subparsers.add_parser("join-gui", help="Join a host with GUI")
    join_gui.add_argument("--host", type=str, required=True, help="Host IP or name")
    join_gui.add_argument("--port", type=int, default=5000, help="TCP port to connect")

    args = parser.parse_args()

    if args.mode == "host":
        run_host(bind=args.bind, port=args.port)
    elif args.mode == "join":
        run_client(host=args.host, port=args.port)
    elif args.mode == "host-gui":
        run_host_gui(port=args.port, bind=args.bind)
    elif args.mode == "join-gui":
        run_client_gui(host=args.host, port=args.port)
