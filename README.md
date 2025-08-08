## LAN Battleship (GUI)

Two-player Battleship over local network with a modern Pygame GUI. One player hosts; the other joins from the same LAN/Wi‑Fi.

- **Python**: 3.9+
- **Dependency**: `pygame` (installed automatically when you install the package)

## Features
- **Classic 10×10 board** with Carrier(5), Battleship(4), Cruiser(3), Submarine(3), Destroyer(2)
- **Original rule option**: extra shot on a hit (enabled)
- **Rematch support**: press `N` after a game ends to request a rematch; starts a fresh round on the same connection
- **Fast LAN networking** with a simple protocol
- **Smooth Pygame UI**: clear boards, hover previews, hit/miss markers, win/lose banner
- **Interactive placement and play** with mouse (rotate with right‑click or `R`)

## Install
Recommended (ensures `pygame` is installed and CLI entrypoints are available):

```
python3 --version
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

This installs console commands: `battleship`, `battleship-host`, and `battleship-join`.

## Run
One of you will HOST (choose who), the other JOINS.

### Option A — Using console commands (recommended)
- **Host (Player A)**
  ```
  battleship --port 5000
  # or
  battleship-host --port 5000
  ```
- **Join (Player B)**
  ```
  battleship-join 192.168.1.23 --port 5000
  ```
  Replace `192.168.1.23` with the host's LAN IP.

### Option B — Using the Python module directly
- **Host (Player A)**
  ```
  python -m battleship --port 5000
  ```
  (Module execution starts the GUI host.)

- For joining via the module, use the console command above. The join GUI is exposed via `battleship-join`.

## Controls
- **Placement**: left‑click cells on your board; rotate the ship with right‑click or press `R`
- **Firing**: left‑click cells on the opponent board
- **Extra turn on hit**: if you hit, you shoot again; if you miss, your opponent plays
- **Rematch**: after win/lose, press `N` to request a rematch; when both players request, a new round starts
- **Quit**: press `Esc` or close the window

## Networking notes
- Both players must be on the same LAN/Wi‑Fi
- The host chooses a port (default `5000`) and may need to allow incoming connections in the OS firewall
- The joiner connects using the host's LAN IP (e.g., `192.168.1.23`)

## Notes
- The project previously had a terminal‑only interface; the GUI is now the primary experience. Terminal modules remain in the codebase but are not exposed as commands.
- Package name in `setup.py`: `lan-battleship`.
