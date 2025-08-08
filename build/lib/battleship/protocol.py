from __future__ import annotations

# Message types exchanged over the wire
# All messages are JSON objects with a 'type' field
# - hello: { type: 'hello', role: 'host'|'client', proto: 1 }
# - start: { type: 'start', youStart: true|false }
# - place_done: { type: 'place_done' }
# - fire: { type: 'fire', row: int, col: int }
# - result: { type: 'result', row: int, col: int, hit: bool, sunk: str|null, gameOver: bool }
# - quit: { type: 'quit' }

PROTO_VERSION = 1
