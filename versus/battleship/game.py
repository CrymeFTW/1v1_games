from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple, Dict, Optional

BOARD_SIZE = 10
COORDS = [chr(ord('A') + i) for i in range(BOARD_SIZE)]


@dataclass
class ShipType:
    name: str
    size: int


SHIP_TYPES: List[ShipType] = [
    ShipType("Carrier", 5),
    ShipType("Battleship", 4),
    ShipType("Cruiser", 3),
    ShipType("Submarine", 3),
    ShipType("Destroyer", 2),
]


class Cell:
    EMPTY = 0
    SHIP = 1
    MISS = 2
    HIT = 3


@dataclass
class Ship:
    type: ShipType
    cells: List[Tuple[int, int]]  # list of (row, col)
    hits: int = 0

    def is_sunk(self) -> bool:
        return self.hits >= self.type.size


class Board:
    def __init__(self) -> None:
        self.grid: List[List[int]] = [[Cell.EMPTY for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)]
        self.ships: List[Ship] = []

    def place_ship(self, ship_type: ShipType, row: int, col: int, horizontal: bool) -> bool:
        cells: List[Tuple[int, int]] = []
        for i in range(ship_type.size):
            r = row + (0 if horizontal else i)
            c = col + (i if horizontal else 0)
            if r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE:
                return False
            if self.grid[r][c] != Cell.EMPTY:
                return False
            cells.append((r, c))
        # place
        for r, c in cells:
            self.grid[r][c] = Cell.SHIP
        self.ships.append(Ship(ship_type, cells))
        return True

    def receive_attack(self, row: int, col: int) -> Tuple[bool, bool, Optional[str]]:
        # returns (is_hit, is_sunk, sunk_name)
        if self.grid[row][col] == Cell.EMPTY:
            self.grid[row][col] = Cell.MISS
            return False, False, None
        if self.grid[row][col] == Cell.SHIP:
            self.grid[row][col] = Cell.HIT
            # mark hit on a ship
            for ship in self.ships:
                if (row, col) in ship.cells:
                    ship.hits += 1
                    if ship.is_sunk():
                        return True, True, ship.type.name
                    return True, False, None
        # already targeted
        return False, False, None

    def all_sunk(self) -> bool:
        return all(ship.is_sunk() for ship in self.ships)


def parse_coord(text: str) -> Optional[Tuple[int, int]]:
    t = text.strip().upper()
    if len(t) < 2 or len(t) > 3:
        return None
    letter = t[0]
    if letter not in COORDS:
        return None
    try:
        num = int(t[1:])
    except ValueError:
        return None
    if num < 1 or num > BOARD_SIZE:
        return None
    row = ord(letter) - ord('A')
    col = num - 1
    return row, col
