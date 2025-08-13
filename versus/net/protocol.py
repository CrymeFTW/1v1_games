from __future__ import annotations

# Message types exchanged over the wire
# All messages are JSON objects with a 'type' field
# Handshake:
# - hello: { type: 'hello', role: 'host'|'client', proto: 1 }
# Lobby / game selection:
# - lobby: { type: 'lobby', games: [str, ...] }
# - game_select: { type: 'game_select', game: str }
# - game_chosen: { type: 'game_chosen', game: str }
# Battleship:
# - start: { type: 'start', youStart: true|false }
# - place_done: { type: 'place_done' }
# - fire: { type: 'fire', row: int, col: int }
# - result: { type: 'result', row: int, col: int, hit: bool, sunk: str|null, gameOver: bool }
# Generic quit:
# - quit: { type: 'quit' }
# Snake (host-authoritative):
# - snake_init: { type: 'snake_init', rows: int, cols: int, h_snake: [[r,c],...], c_snake: [[r,c],...], food: [r,c] }
# - snake_dir: { type: 'snake_dir', dir: 'U'|'D'|'L'|'R' }
# - snake_state: { type: 'snake_state', h_snake: [[r,c],...], c_snake: [[r,c],...], food: [r,c], scores: {host:int, client:int}, status: 'ongoing'|'over', winner: 'host'|'client'|'draw'|null }

PROTO_VERSION = 1
