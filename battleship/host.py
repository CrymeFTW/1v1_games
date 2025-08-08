from __future__ import annotations

import socket
from typing import Optional
from .game import Board, Cell
from .net import open_server, send_msg, recv_msg
from .protocol import PROTO_VERSION
from .ui import place_ships_interactive, draw_turn, read_target, announce, clear_screen


def run_host(bind: str, port: int) -> None:
    clear_screen()
    print("Waiting for a player to connect...")
    srv, conn, addr = open_server(bind, port)
    try:
        # handshake
        send_msg(conn, {"type": "hello", "role": "host", "proto": PROTO_VERSION})
        hello = recv_msg(conn)
        if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
            raise RuntimeError("protocol mismatch")

        # decide who starts (host starts by default)
        send_msg(conn, {"type": "start", "youStart": False})

        my_board = Board()
        opp_known = Board()  # we only mark hits/misses here

        # placement (both sides place independently)
        place_ships_interactive(my_board)
        send_msg(conn, {"type": "place_done"})
        # wait for client placement done
        msg = recv_msg(conn)
        if msg.get("type") != "place_done":
            raise RuntimeError("unexpected during placement")

        your_turn = True
        while True:
            draw_turn(my_board, opp_known, your_turn)
            if your_turn:
                # keep asking until a fresh, unfired coordinate is chosen
                while True:
                    target = read_target()
                    if target is None:
                        send_msg(conn, {"type": "quit"})
                        print("You quit the game.")
                        return
                    r, c = target
                    if opp_known.grid[r][c] in (Cell.MISS, Cell.HIT):
                        announce("You already fired there. Try another tile.")
                        continue
                    break
                send_msg(conn, {"type": "fire", "row": r, "col": c})
                res = recv_msg(conn)
                if res.get("type") != "result":
                    raise RuntimeError("expected result")
                # mark on opp_known
                hit = bool(res.get("hit"))
                opp_known.grid[r][c] = (Cell.HIT if hit else Cell.MISS)
                draw_turn(my_board, opp_known, your_turn)
                if res.get("sunk"):
                    announce(f"You sunk their {res['sunk']}!")
                if res.get("gameOver"):
                    announce("You win! 🎉")
                    break
                # Keep your turn on hit, otherwise pass turn
                your_turn = hit
            else:
                msg = recv_msg(conn)
                if msg.get("type") == "quit":
                    print("Opponent left the game.")
                    return
                if msg.get("type") != "fire":
                    raise RuntimeError("expected fire")
                r = int(msg.get("row"))
                c = int(msg.get("col"))
                # if opponent fires twice at same cell, it's a miss by definition (already resolved)
                if my_board.grid[r][c] in (Cell.MISS, Cell.HIT):
                    hit = False
                    sunk = False
                    sunk_name = None
                else:
                    hit, sunk, sunk_name = my_board.receive_attack(r, c)
                game_over = my_board.all_sunk()
                send_msg(conn, {"type": "result", "row": r, "col": c, "hit": hit, "sunk": sunk_name, "gameOver": game_over})
                if game_over:
                    announce("You lose.")
                    break
                # You get the turn only if opponent missed
                your_turn = (not hit)
    finally:
        try:
            conn.close()
        except Exception:
            pass
        try:
            srv.close()
        except Exception:
            pass
