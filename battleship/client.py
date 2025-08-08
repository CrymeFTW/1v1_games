from __future__ import annotations

from .game import Board, Cell
from .net import open_client, send_msg, recv_msg
from .protocol import PROTO_VERSION
from .ui import place_ships_interactive, draw_turn, read_target, announce, clear_screen


def run_client(host: str, port: int) -> None:
    clear_screen()
    print(f"Connecting to {host}:{port} ...")
    sock = open_client(host, port)
    try:
        # handshake
        hello = recv_msg(sock)
        if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
            raise RuntimeError("protocol mismatch")
        send_msg(sock, {"type": "hello", "role": "client", "proto": PROTO_VERSION})

        start = recv_msg(sock)
        if start.get("type") != "start":
            raise RuntimeError("expected start")
        you_start = bool(start.get("youStart"))

        my_board = Board()
        opp_known = Board()

        # placement
        place_ships_interactive(my_board)
        send_msg(sock, {"type": "place_done"})
        msg = recv_msg(sock)
        if msg.get("type") != "place_done":
            raise RuntimeError("unexpected during placement")

        your_turn = you_start
        while True:
            draw_turn(my_board, opp_known, your_turn)
            if your_turn:
                # keep asking until a fresh, unfired coordinate is chosen
                while True:
                    target = read_target()
                    if target is None:
                        send_msg(sock, {"type": "quit"})
                        print("You quit the game.")
                        return
                    r, c = target
                    if opp_known.grid[r][c] in (Cell.MISS, Cell.HIT):
                        announce("You already fired there. Try another tile.")
                        continue
                    break
                send_msg(sock, {"type": "fire", "row": r, "col": c})
                res = recv_msg(sock)
                if res.get("type") != "result":
                    raise RuntimeError("expected result")
                hit = bool(res.get("hit"))
                opp_known.grid[r][c] = (Cell.HIT if hit else Cell.MISS)
                draw_turn(my_board, opp_known, your_turn)
                if res.get("sunk"):
                    announce(f"You sunk their {res['sunk']}!")
                if res.get("gameOver"):
                    announce("You win! 🎉")
                    break
                your_turn = False
            else:
                msg = recv_msg(sock)
                if msg.get("type") == "quit":
                    print("Opponent left the game.")
                    return
                if msg.get("type") != "fire":
                    raise RuntimeError("expected fire")
                r = int(msg.get("row"))
                c = int(msg.get("col"))
                if my_board.grid[r][c] in (Cell.MISS, Cell.HIT):
                    hit = False
                    sunk = False
                    sunk_name = None
                else:
                    hit, sunk, sunk_name = my_board.receive_attack(r, c)
                game_over = my_board.all_sunk()
                send_msg(sock, {"type": "result", "row": r, "col": c, "hit": hit, "sunk": sunk_name, "gameOver": game_over})
                if game_over:
                    announce("You lose.")
                    break
                your_turn = True
    finally:
        try:
            sock.close()
        except Exception:
            pass
