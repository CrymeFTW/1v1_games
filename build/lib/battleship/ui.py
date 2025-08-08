from __future__ import annotations

import os
import sys
from typing import List, Optional, Tuple
from .game import BOARD_SIZE, COORDS, Cell, Board, ShipType, SHIP_TYPES, parse_coord

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()


def draw_board(board: Board, reveal: bool = True) -> str:
    # Top header
    lines: List[str] = []
    header = "   " + " ".join(f"{i+1:>2}" for i in range(BOARD_SIZE))
    lines.append(header)
    for r in range(BOARD_SIZE):
        row_cells: List[str] = [f"{COORDS[r]}  "]
        for c in range(BOARD_SIZE):
            cell = board.grid[r][c]
            ch: str
            if cell == Cell.EMPTY:
                ch = DIM + "." + RESET
            elif cell == Cell.SHIP:
                ch = (BLUE + "■" + RESET) if reveal else DIM + "." + RESET
            elif cell == Cell.MISS:
                ch = YELLOW + "×" + RESET
            elif cell == Cell.HIT:
                ch = RED + "✹" + RESET
            else:
                ch = "?"
            row_cells.append(ch)
        lines.append(" ".join(row_cells))
    return "\n".join(lines)


def draw_dual(my_board: Board, opp_board: Board) -> str:
    my = draw_board(my_board, reveal=True).splitlines()
    opp = draw_board(opp_board, reveal=False).splitlines()
    width = max(len(s) for s in my)
    lines = []
    title = BOLD + "Your Board" + RESET
    title2 = BOLD + "Their Board" + RESET
    lines.append(f"{title:<{width}}    {title2}")
    for i in range(len(my)):
        left = my[i]
        right = opp[i] if i < len(opp) else ""
        lines.append(f"{left:<{width}}    {right}")
    return "\n".join(lines)


def prompt(text: str) -> str:
    sys.stdout.write(BOLD + text + RESET + " ")
    sys.stdout.flush()
    return sys.stdin.readline().strip()


def place_ships_interactive(board: Board) -> None:
    clear_screen()
    print(BOLD + "Place your fleet" + RESET)
    print("Ships: " + ", ".join(f"{s.name}({s.size})" for s in SHIP_TYPES))
    horizontal = True
    for s in SHIP_TYPES:
        while True:
            clear_screen()
            print(BOLD + f"Placing {s.name} ({s.size})" + RESET + ("  [" + ("H" if horizontal else "V") + "]"))
            print(draw_board(board, reveal=True))
            ans = prompt("Enter coordinate like A1 (or R to rotate):").upper()
            if ans == "Q":
                raise KeyboardInterrupt()
            if ans == "R":
                horizontal = not horizontal
                continue
            coord = parse_coord(ans)
            if not coord:
                print(RED + "Invalid coordinate." + RESET)
                continue
            r, c = coord
            if board.place_ship(s, r, c, horizontal):
                break
            else:
                print(RED + "Cannot place there." + RESET)
    clear_screen()


def announce(text: str) -> None:
    print(BOLD + text + RESET)


def wait_key() -> None:
    prompt("Press Enter to continue...")


def draw_turn(my_board: Board, opp_known: Board, your_turn: bool) -> None:
    clear_screen()
    who = GREEN + "Your turn" + RESET if your_turn else YELLOW + "Waiting for opponent" + RESET
    announce(who)
    print(draw_dual(my_board, opp_known))


def read_target() -> Optional[Tuple[int, int]]:
    while True:
        ans = prompt("Fire at (e.g., B7) or 'q' to quit:")
        if ans.lower() == 'q':
            return None
        coord = parse_coord(ans)
        if coord is None:
            print(RED + "Invalid coordinate." + RESET)
            continue
        return coord
