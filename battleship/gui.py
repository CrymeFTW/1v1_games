from __future__ import annotations

import threading
import queue
import time
import sys
import math
from typing import Optional, Tuple, List

import pygame

from .game import BOARD_SIZE, COORDS, Board, Cell, SHIP_TYPES, ShipType, parse_coord
from .net import open_server, open_client, send_msg, recv_msg
from .protocol import PROTO_VERSION


class NetworkPeer:
    def __init__(self, mode: str, host: str | None, port: int, bind: str = "0.0.0.0") -> None:
        self.mode = mode  # 'host' or 'client'
        self.sock = None
        self.srv = None
        self.recv_thread: Optional[threading.Thread] = None
        self.recv_queue: "queue.Queue[dict]" = queue.Queue()
        self.stopped = threading.Event()
        self._connect(host, port, bind)

    def _connect(self, host: Optional[str], port: int, bind: str) -> None:
        if self.mode == "host":
            self.srv, self.sock, _addr = open_server(bind, port)
            send_msg(self.sock, {"type": "hello", "role": "host", "proto": PROTO_VERSION})
            hello = recv_msg(self.sock)
            if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
                raise RuntimeError("protocol mismatch")
            # host decides who starts (host starts)
            send_msg(self.sock, {"type": "start", "youStart": False})
        else:
            self.sock = open_client(host or "localhost", port)
            # handshake
            hello = recv_msg(self.sock)
            if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
                raise RuntimeError("protocol mismatch")
            send_msg(self.sock, {"type": "hello", "role": "client", "proto": PROTO_VERSION})
        self._start_recv_loop()

    def _start_recv_loop(self) -> None:
        def loop() -> None:
            try:
                while not self.stopped.is_set():
                    msg = recv_msg(self.sock)
                    self.recv_queue.put(msg)
            except Exception:
                # Socket closed or error
                pass

        self.recv_thread = threading.Thread(target=loop, daemon=True)
        self.recv_thread.start()

    def send(self, payload: dict) -> None:
        if self.sock is None:
            return
        send_msg(self.sock, payload)

    def try_get(self, timeout: float = 0.0) -> Optional[dict]:
        try:
            return self.recv_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        self.stopped.set()
        try:
            if self.sock:
                self.sock.close()
        except Exception:
            pass
        try:
            if self.srv:
                self.srv.close()
        except Exception:
            pass


# --------------------------- Pygame rendering ---------------------------

WINDOW_BG = (15, 18, 25)
GRID_BG = (23, 28, 38)
TEXT = (230, 235, 245)
SUBTEXT = (155, 165, 185)
ACCENT = (58, 123, 213)
ACCENT_DIM = (58, 123, 213, 90)
HIT = (232, 93, 117)
MISS = (240, 190, 90)
SHIP = (60, 130, 200)
SHIP_OUTLINE = (40, 95, 160)
HOVER = (90, 160, 245)
INVALID = (210, 75, 90)
VICTORY = (90, 200, 120)
DEFEAT = (220, 60, 80)

CELL_SIZE = 40
GRID_MARGIN = 28
PANEL_PADDING = 28
BOARD_GAP = 60
TOP_BAR = 84
BOTTOM_BAR = 60


class GuiGame:
    def __init__(self, mode: str, host: Optional[str], port: int, bind: str = "0.0.0.0") -> None:
        pygame.init()
        pygame.display.set_caption("LAN Battleship")
        total_width = (CELL_SIZE * BOARD_SIZE) * 2 + BOARD_GAP + PANEL_PADDING * 2
        total_height = TOP_BAR + (CELL_SIZE * BOARD_SIZE) + BOTTOM_BAR
        self.screen = pygame.display.set_mode((total_width, total_height))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 22)
        self.font_small = pygame.font.SysFont("Arial", 18)
        self.font_big = pygame.font.SysFont("Arial", 48, bold=True)

        self.peer = NetworkPeer(mode, host, port, bind)
        self.mode = mode
        self.you_start: Optional[bool] = None

        self.my_board = Board()
        self.opp_known = Board()

        self.placing_index = 0
        self.horizontal = True

        self.running = True
        self.turn_is_mine: Optional[bool] = None
        self.info_message = "Place your fleet"
        self.message_timer: float = 0.0
        self.awaiting_result = False
        self.game_over: Optional[str] = None  # 'win' or 'lose'

        # If client, we must receive 'start' to know who begins
        if self.mode == "client":
            self.info_message = "Waiting for start signal..."

    # --------------------------- Utility ---------------------------
    def show_message(self, text: str, seconds: float = 2.0) -> None:
        self.info_message = text
        self.message_timer = time.time() + seconds

    def get_board_rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        left_x = PANEL_PADDING
        right_x = PANEL_PADDING + CELL_SIZE * BOARD_SIZE + BOARD_GAP
        y = TOP_BAR
        left_rect = pygame.Rect(left_x, y, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
        right_rect = pygame.Rect(right_x, y, CELL_SIZE * BOARD_SIZE, CELL_SIZE * BOARD_SIZE)
        return left_rect, right_rect

    def mouse_to_cell(self, rect: pygame.Rect, pos: Tuple[int, int]) -> Optional[Tuple[int, int]]:
        if not rect.collidepoint(pos):
            return None
        x, y = pos
        col = (x - rect.x) // CELL_SIZE
        row = (y - rect.y) // CELL_SIZE
        if 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE:
            return int(row), int(col)
        return None

    # --------------------------- Draw ---------------------------
    def draw(self) -> None:
        self.screen.fill(WINDOW_BG)
        left_rect, right_rect = self.get_board_rects()

        # Titles
        self.draw_title("Your Board", left_rect.x, 24)
        self.draw_title("Their Board", right_rect.x, 24)

        # Boards
        self.draw_board(left_rect, self.my_board, reveal=True)
        self.draw_board(right_rect, self.opp_known, reveal=False)

        # Phase prompts
        status_text = self.info_message
        if self.message_timer and time.time() > self.message_timer:
            self.message_timer = 0
            status_text = ""
        self.draw_status_bar(status_text)

        # If placing, show current ship ghost preview under mouse
        if self.game_over is None and self.placing_index < len(SHIP_TYPES):
            mouse = pygame.mouse.get_pos()
            cell = self.mouse_to_cell(left_rect, mouse)
            if cell:
                self.draw_placement_preview(left_rect, cell)

        # If it's my turn and not waiting for result, hint over opponent grid
        if self.game_over is None and self.turn_is_mine and not self.awaiting_result:
            mouse = pygame.mouse.get_pos()
            cell = self.mouse_to_cell(right_rect, mouse)
            if cell:
                r, c = cell
                rx = right_rect.x + c * CELL_SIZE
                ry = right_rect.y + r * CELL_SIZE
                pygame.draw.rect(self.screen, (HOVER[0], HOVER[1], HOVER[2], 40), (rx + 2, ry + 2, CELL_SIZE - 4, CELL_SIZE - 4), 2)

        # Game over banner
        if self.game_over:
            banner = "You Win!" if self.game_over == "win" else "You Lose"
            color = VICTORY if self.game_over == "win" else DEFEAT
            surf = self.font_big.render(banner, True, color)
            self.screen.blit(surf, (self.screen.get_width() // 2 - surf.get_width() // 2, 8))

        pygame.display.flip()

    def draw_title(self, text: str, x: int, y: int) -> None:
        txt = self.font.render(text, True, TEXT)
        self.screen.blit(txt, (x, y))

    def draw_status_bar(self, text: str) -> None:
        if not text:
            return
        surf = self.font.render(text, True, SUBTEXT)
        self.screen.blit(surf, (PANEL_PADDING, self.screen.get_height() - BOTTOM_BAR + 16))

    def draw_board(self, rect: pygame.Rect, board: Board, reveal: bool) -> None:
        pygame.draw.rect(self.screen, GRID_BG, rect, border_radius=8)
        # grid lines
        for i in range(BOARD_SIZE + 1):
            x = rect.x + i * CELL_SIZE
            y = rect.y + i * CELL_SIZE
            pygame.draw.line(self.screen, (50, 58, 72), (rect.x, y), (rect.right, y))
            pygame.draw.line(self.screen, (50, 58, 72), (x, rect.y), (x, rect.bottom))
        # labels
        for i in range(BOARD_SIZE):
            letter = self.font_small.render(COORDS[i], True, SUBTEXT)
            num = self.font_small.render(str(i + 1), True, SUBTEXT)
            self.screen.blit(letter, (rect.x - 18, rect.y + i * CELL_SIZE + CELL_SIZE // 2 - letter.get_height() // 2))
            self.screen.blit(num, (rect.x + i * CELL_SIZE + CELL_SIZE // 2 - num.get_width() // 2, rect.y - 22))
        # cells content
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cell = board.grid[r][c]
                cx = rect.x + c * CELL_SIZE
                cy = rect.y + r * CELL_SIZE
                if cell == Cell.SHIP and reveal:
                    pygame.draw.rect(self.screen, SHIP, (cx + 2, cy + 2, CELL_SIZE - 4, CELL_SIZE - 4))
                    pygame.draw.rect(self.screen, SHIP_OUTLINE, (cx + 2, cy + 2, CELL_SIZE - 4, CELL_SIZE - 4), 2)
                elif cell == Cell.MISS:
                    pygame.draw.circle(self.screen, MISS, (cx + CELL_SIZE // 2, cy + CELL_SIZE // 2), CELL_SIZE // 6)
                elif cell == Cell.HIT:
                    pygame.draw.circle(self.screen, HIT, (cx + CELL_SIZE // 2, cy + CELL_SIZE // 2), CELL_SIZE // 3)

    def draw_placement_preview(self, left_rect: pygame.Rect, start_cell: Tuple[int, int]) -> None:
        ship_type = SHIP_TYPES[self.placing_index]
        r0, c0 = start_cell
        valid = True
        cells: List[Tuple[int, int]] = []
        for i in range(ship_type.size):
            r = r0 + (0 if self.horizontal else i)
            c = c0 + (i if self.horizontal else 0)
            if r < 0 or r >= BOARD_SIZE or c < 0 or c >= BOARD_SIZE or self.my_board.grid[r][c] != Cell.EMPTY:
                valid = False
            cells.append((r, c))
        for r, c in cells:
            if 0 <= r < BOARD_SIZE and 0 <= c < BOARD_SIZE:
                cx = left_rect.x + c * CELL_SIZE
                cy = left_rect.y + r * CELL_SIZE
                color = HOVER if valid else INVALID
                pygame.draw.rect(self.screen, color, (cx + 2, cy + 2, CELL_SIZE - 4, CELL_SIZE - 4), 0 if valid else 2)

    # --------------------------- Interaction ---------------------------
    def place_ships_handle_click(self, pos: Tuple[int, int]) -> None:
        left_rect, _right_rect = self.get_board_rects()
        cell = self.mouse_to_cell(left_rect, pos)
        if cell is None:
            return
        ship_type = SHIP_TYPES[self.placing_index]
        r0, c0 = cell
        if self.my_board.place_ship(ship_type, r0, c0, self.horizontal):
            self.placing_index += 1
            if self.placing_index >= len(SHIP_TYPES):
                # placement done
                self.peer.send({"type": "place_done"})
                self.show_message("Waiting for opponent to finish placement...")
        else:
            self.show_message("Cannot place there.")

    def try_start_after_placement(self) -> None:
        # Host already sent 'start' during handshake; client waits to receive it
        if self.mode == "client" and self.you_start is None:
            # Look for start
            msg = self.peer.try_get(0.0)
            while msg:
                if msg.get("type") == "start":
                    self.you_start = bool(msg.get("youStart"))
                    self.turn_is_mine = self.you_start
                elif msg.get("type") == "place_done":
                    # store to process after my placement
                    self.recv_buffer.append(msg)  # type: ignore[attr-defined]
                else:
                    # buffer other messages until gameplay
                    self.recv_buffer.append(msg)  # type: ignore[attr-defined]
                msg = self.peer.try_get(0.0)

    def click_fire(self, pos: Tuple[int, int]) -> None:
        _left_rect, right_rect = self.get_board_rects()
        cell = self.mouse_to_cell(right_rect, pos)
        if cell is None or not self.turn_is_mine or self.awaiting_result:
            return
        r, c = cell
        if self.opp_known.grid[r][c] in (Cell.MISS, Cell.HIT):
            self.show_message("Already targeted that cell.")
            return
        self.peer.send({"type": "fire", "row": r, "col": c})
        self.awaiting_result = True
        # store pending coords to apply upon result
        self.pending_shot = (r, c)  # type: ignore[attr-defined]

    # --------------------------- Loop ---------------------------
    def run(self) -> None:
        self.recv_buffer: List[dict] = []
        # If host, we know we start; if client, will be set by start message
        if self.mode == "host":
            self.you_start = False  # remote 'youStart' flag is False, i.e., I start
            self.turn_is_mine = True
        else:
            self.you_start = None
            self.turn_is_mine = None

        placement_done_local = False
        placement_done_remote = False

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if not self.game_over:
                        try:
                            self.peer.send({"type": "quit"})
                        except Exception:
                            pass
                    self.running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r and self.game_over is None and self.placing_index < len(SHIP_TYPES):
                        self.horizontal = not self.horizontal
                    if event.key == pygame.K_ESCAPE:
                        if not self.game_over:
                            try:
                                self.peer.send({"type": "quit"})
                            except Exception:
                                pass
                        self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and self.game_over is None:
                    if self.placing_index < len(SHIP_TYPES):
                        if event.button == 1:
                            self.place_ships_handle_click(event.pos)
                        elif event.button == 3:
                            self.horizontal = not self.horizontal
                    else:
                        if event.button == 1:
                            self.click_fire(event.pos)

            # After sending place_done, wait for opponent's place_done too
            if self.placing_index >= len(SHIP_TYPES) and not placement_done_local:
                placement_done_local = True

            # Poll incoming messages
            msg = self.peer.try_get(0.0)
            while msg is not None:
                mtype = msg.get("type")
                if mtype == "place_done":
                    placement_done_remote = True
                elif mtype == "start":
                    # only client expects this here
                    self.you_start = bool(msg.get("youStart"))
                    self.turn_is_mine = self.you_start
                elif mtype == "result" and self.awaiting_result:
                    hit = bool(msg.get("hit"))
                    r, c = getattr(self, "pending_shot", (None, None))
                    if r is not None and c is not None:
                        self.opp_known.grid[r][c] = (Cell.HIT if hit else Cell.MISS)
                    sunk_name = msg.get("sunk")
                    if sunk_name:
                        self.show_message(f"You sunk their {sunk_name}!")
                    if msg.get("gameOver"):
                        self.game_over = "win"
                        self.turn_is_mine = False
                    self.awaiting_result = False
                    self.turn_is_mine = False if self.game_over is None else self.turn_is_mine
                elif mtype == "fire":
                    r = int(msg.get("row"))
                    c = int(msg.get("col"))
                    # Resolve attack on my board
                    if self.my_board.grid[r][c] in (Cell.MISS, Cell.HIT):
                        hit = False
                        sunk_name = None
                    else:
                        hit, sunk, sunk_name = self.my_board.receive_attack(r, c)
                    game_over = self.my_board.all_sunk()
                    self.peer.send({"type": "result", "row": r, "col": c, "hit": hit, "sunk": sunk_name, "gameOver": game_over})
                    if game_over:
                        self.game_over = "lose"
                        self.turn_is_mine = False
                    else:
                        self.turn_is_mine = True
                elif mtype == "quit":
                    self.show_message("Opponent left the game.", 4.0)
                    self.game_over = self.game_over or "win"
                    self.turn_is_mine = False
                msg = self.peer.try_get(0.0)

            # Transition to gameplay after both placed and start known
            if placement_done_local and placement_done_remote and (self.mode == "host" or self.you_start is not None):
                if self.turn_is_mine:
                    self.info_message = "Your turn: click on the right board to fire."
                else:
                    self.info_message = "Waiting for opponent..."

            self.draw()
            self.clock.tick(60)

        self.peer.close()
        pygame.quit()


# --------------------------- Entrypoints ---------------------------

def run_host_gui(port: int, bind: str = "0.0.0.0") -> None:
    game = GuiGame("host", host=None, port=port, bind=bind)
    game.run()


def run_client_gui(host: str, port: int) -> None:
    game = GuiGame("client", host=host, port=port)
    game.run()
