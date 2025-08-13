from __future__ import annotations

import threading
import queue
import time
import sys
import math
import os
from typing import Optional, Tuple, List

import pygame
import random

from .battleship.game import BOARD_SIZE, COORDS, Board, Cell, SHIP_TYPES, ShipType, parse_coord
from .net.net import open_server, open_client, send_msg, recv_msg
from .net.protocol import PROTO_VERSION


class NetworkPeer:
    def __init__(self, mode: str, host: str | None, port: int, bind: str = "0.0.0.0") -> None:
        self.mode = mode  # 'host' or 'client'
        self.sock = None
        self.srv = None
        self.recv_thread: Optional[threading.Thread] = None
        self.recv_queue: "queue.Queue[dict]" = queue.Queue()
        self.stopped = threading.Event()
        self.connected = False

        # Start network setup in background so GUI can render immediately
        if self.mode == "host":
            threading.Thread(target=self._host_wait_for_client, args=(bind, port), daemon=True).start()
        else:
            threading.Thread(target=self._client_connect, args=(host, port), daemon=True).start()

    def _host_wait_for_client(self, bind: str, port: int) -> None:
        try:
            srv, conn, _addr = open_server(bind, port)
            if self.stopped.is_set():
                try:
                    conn.close()
                except Exception:
                    pass
                try:
                    srv.close()
                except Exception:
                    pass
                return
            self.srv = srv
            self.sock = conn
            send_msg(self.sock, {"type": "hello", "role": "host", "proto": PROTO_VERSION})
            hello = recv_msg(self.sock)
            if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
                raise RuntimeError("protocol mismatch")
            # Send lobby with available games
            send_msg(self.sock, {"type": "lobby", "games": ["Battleship", "Snake"]})
            self.connected = True
            self._start_recv_loop()
        except Exception:
            # On failure, leave not connected; caller may quit
            pass

    def _client_connect(self, host: Optional[str], port: int) -> None:
        try:
            self.sock = open_client(host or "localhost", port)
            # handshake
            hello = recv_msg(self.sock)
            if hello.get("type") != "hello" or hello.get("proto") != PROTO_VERSION:
                raise RuntimeError("protocol mismatch")
            send_msg(self.sock, {"type": "hello", "role": "client", "proto": PROTO_VERSION})
            self.connected = True
            self._start_recv_loop()
        except Exception:
            # connection failed; leave not connected so GUI can show status
            pass

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
        if self.sock is None or not self.connected:
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
        pygame.display.set_caption("Versus - 1v1 Games")
        total_width = (CELL_SIZE * BOARD_SIZE) * 2 + BOARD_GAP + PANEL_PADDING * 2
        total_height = TOP_BAR + (CELL_SIZE * BOARD_SIZE) + BOTTOM_BAR
        self.screen = pygame.display.set_mode((total_width, total_height))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 22)
        self.font_small = pygame.font.SysFont("Arial", 18)
        self.font_big = pygame.font.SysFont("Arial", 48, bold=True)

        self.peer = NetworkPeer(mode, host, port, bind)
        self.mode = mode
        
        # Game state
        self.state = "waiting"  # "waiting", "lobby", "battleship", "snake"
        self.available_games = []
        self.selected_game = None
        self.my_choice = None
        self.peer_choice = None
        self.chosen_game = None
        
        self.running = True
        self.info_message = "Waiting for player to connect..." if mode == "host" else "Connecting..."
        self.message_timer: float = 0.0
        
        # Battleship-specific (will be initialized when game starts)
        self.my_board = None
        self.opp_known = None
        self.placing_index = 0
        self.horizontal = True
        self.you_start = None
        self.turn_is_mine = None
        self.awaiting_result = False
        self.game_over = None

        # Snake-specific
        self.sn_rows = 18
        self.sn_cols = 30
        self.sn_host_snake: list[tuple[int,int]] = []
        self.sn_client_snake: list[tuple[int,int]] = []
        self.sn_food: tuple[int,int] = (0, 0)
        self.sn_scores = {"host": 0, "client": 0}
        self.sn_host_dir = 'R'
        self.sn_client_dir = 'L'
        self.sn_host_desired = 'R'
        self.sn_client_desired = 'L'
        self.sn_tick = 0.10  # seconds per tick (dynamic)
        self.sn_base_tick = 0.12
        self.sn_min_tick = 0.05
        self.sn_tick_factor = 0.007  # faster per point of max score
        self.sn_next_tick = time.time() + 9999  # inactive until init
        self.sn_status = 'idle'  # 'idle'|'ongoing'|'over'
        self.sn_winner = None
        # Walls: states per side: 'hard'|'green'|'blink'
        self.sn_walls: dict[str,str] = {'top':'hard','bottom':'hard','left':'hard','right':'hard'}
        self.sn_wall_meta: dict[str,dict] = {}
        self.sn_blink_duration = 2.0
        self.sn_green_duration_range = (6.0, 10.0)
        self.sn_next_wall_event = time.time() + 9999

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
        if self.state in ("waiting", "lobby"):
            title = self.font_big.render("Versus", True, TEXT)
            self.screen.blit(title, (self.screen.get_width()//2 - title.get_width()//2, 40))
            if self.state == "waiting":
                status = self.font.render(self.info_message, True, SUBTEXT)
                self.screen.blit(status, (self.screen.get_width()//2 - status.get_width()//2, 140))
            else:
                # lobby
                y = 160
                self.screen.blit(self.font.render("Choose a game (click)", True, TEXT), (280, y))
                y += 40
                buttons = []
                for g in self.available_games:
                    rect = pygame.Rect(300, y, 200, 48)
                    pygame.draw.rect(self.screen, GRID_BG, rect, border_radius=8)
                    label = self.font.render(g, True, TEXT)
                    self.screen.blit(label, (rect.x + rect.width//2 - label.get_width()//2, rect.y + 10))
                    buttons.append((rect, g))
                    y += 70
                # store for click handling
                self._lobby_buttons = buttons
                # show both choices if available
                if self.my_choice:
                    txt = self.font.render(f"You chose: {self.my_choice}", True, SUBTEXT)
                    self.screen.blit(txt, (280, y))
                    y += 30
                if self.peer_choice:
                    txt = self.font.render(f"Opponent chose: {self.peer_choice}", True, SUBTEXT)
                    self.screen.blit(txt, (280, y))
                    y += 30
                if self.chosen_game:
                    status = self.font.render(f"Selected: {self.chosen_game}", True, SUBTEXT)
                    self.screen.blit(status, (280, y))
            pygame.display.flip()
            return

        if self.state == "snake":
            self.draw_snake_scene()
            pygame.display.flip()
            return

        # Battleship draw
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

    # ------------ Snake helpers ------------
    def start_snake(self) -> None:
        if self.mode == "host":
            # center rows
            r = self.sn_rows // 2
            self.sn_host_snake = [(r, 2), (r, 1), (r, 0), (r, 0)]
            self.sn_client_snake = [(r, self.sn_cols - 3), (r, self.sn_cols - 2), (r, self.sn_cols - 1), (r, self.sn_cols - 1)]
            self.sn_host_dir = 'R'
            self.sn_client_dir = 'L'
            self.sn_host_desired = 'R'
            self.sn_client_desired = 'L'
            self.sn_food = self._snake_spawn_food()
            self.sn_scores = {'host': 0, 'client': 0}
            # walls initial
            self.sn_walls = {'top':'hard','bottom':'hard','left':'hard','right':'hard'}
            self.sn_wall_meta = {}
            self.sn_next_wall_event = time.time() + random.uniform(*self.sn_green_duration_range)
            self._snake_update_tick()
            # send init
            self.peer.send({
                'type': 'snake_init',
                'rows': self.sn_rows,
                'cols': self.sn_cols,
                'h_snake': self.sn_host_snake,
                'c_snake': self.sn_client_snake,
                'food': list(self.sn_food),
            })
            self.sn_status = 'ongoing'
            self.sn_next_tick = time.time() + self.sn_tick
            self.state = 'snake'
        else:
            # client waits for snake_init in message loop
            self.info_message = "Waiting for snake init..."
            self.state = 'snake'

    def _snake_spawn_food(self) -> tuple[int,int]:
        occupied = set(self.sn_host_snake) | set(self.sn_client_snake)
        choices = [(r, c) for r in range(self.sn_rows) for c in range(self.sn_cols) if (r, c) not in occupied]
        return random.choice(choices) if choices else (0, 0)

    def _snake_wrap(self, r: int, c: int) -> tuple[int,int]:
        # wrapping kept for position compute; wall death is handled separately in tick using prev->new crosses
        return (r % self.sn_rows, c % self.sn_cols)

    def _snake_apply_dir(self, head: tuple[int,int], d: str) -> tuple[int,int]:
        drdc = {'U': (-1, 0), 'D': (1, 0), 'L': (0, -1), 'R': (0, 1)}
        dr, dc = drdc.get(d, (0, 0))
        nr, nc = head[0] + dr, head[1] + dc
        return self._snake_wrap(nr, nc)

    def _snake_update_tick(self) -> None:
        # Tick speed scales with max score
        mx = max(self.sn_scores.get('host',0), self.sn_scores.get('client',0))
        self.sn_tick = max(self.sn_min_tick, self.sn_base_tick - self.sn_tick_factor * mx)

    def _snake_update_walls_lifecycle(self) -> None:
        now = time.time()
        # possibly change wall states
        # Ensure at most 2 green walls simultaneously. Use blink before reverting to hard.
        # Any green wall that exceeded duration enters blink; after blink it's hard.
        to_hard = []
        for side, meta in list(self.sn_wall_meta.items()):
            state = self.sn_walls.get(side, 'hard')
            start = meta.get('start', now)
            duration = meta.get('duration', 0)
            if state == 'green' and now - start >= duration:
                # go blink
                self.sn_walls[side] = 'blink'
                meta['start'] = now
            elif state == 'blink' and now - start >= self.sn_blink_duration:
                to_hard.append(side)
        for side in to_hard:
            self.sn_walls[side] = 'hard'
            self.sn_wall_meta.pop(side, None)
        # Possibly turn new walls green if less than 2 are active
        active_green = [s for s in self.sn_walls if self.sn_walls[s] in ('green','blink')]
        if len(active_green) < 2 and now >= self.sn_next_wall_event:
            choices = [s for s in self.sn_walls if self.sn_walls[s] == 'hard']
            if choices:
                side = random.choice(choices)
                self.sn_walls[side] = 'green'
                self.sn_wall_meta[side] = {'start': now, 'duration': random.uniform(*self.sn_green_duration_range)}
            # schedule next event
            self.sn_next_wall_event = now + random.uniform(*self.sn_green_duration_range)

    def _snake_block_reverse(self, current: str, desired: str) -> str:
        opp = {'U':'D','D':'U','L':'R','R':'L'}
        if desired and desired in opp and opp[desired] == current:
            return current
        return desired or current

    def _snake_cut_at(self, snake: list[tuple[int,int]], hit_pos: tuple[int,int]) -> list[tuple[int,int]]:
        # keep from head up to the segment just before hit_pos; remove from hit_pos to tail
        if hit_pos in snake:
            idx = snake.index(hit_pos)
            # ensure at least length 1 remains
            new_snake = snake[:idx]
            return new_snake if new_snake else snake[:1]
        return snake

    def snake_tick_host(self) -> None:
        if self.sn_status != 'ongoing':
            return
        # update directions with anti-reverse
        self.sn_host_dir = self._snake_block_reverse(self.sn_host_dir, self.sn_host_desired)
        self.sn_client_dir = self._snake_block_reverse(self.sn_client_dir, self.sn_client_desired)

        # compute new heads
        new_h = self._snake_apply_dir(self.sn_host_snake[0], self.sn_host_dir)
        new_c = self._snake_apply_dir(self.sn_client_snake[0], self.sn_client_dir)

        # fruit check
        h_eat = (new_h == self.sn_food)
        c_eat = (new_c == self.sn_food)

        # move: insert heads
        self.sn_host_snake.insert(0, new_h)
        self.sn_client_snake.insert(0, new_c)

        # if ate, grow (do not pop tail), else pop
        if h_eat:
            self.sn_scores['host'] += 1
        else:
            self.sn_host_snake.pop()
        if c_eat:
            self.sn_scores['client'] += 1
        else:
            self.sn_client_snake.pop()

        # dynamic speed: based on max score
        self._snake_update_tick()

        # if any ate, spawn new food not on snakes
        if h_eat or c_eat:
            self.sn_food = self._snake_spawn_food()

        # collisions
        # wall collisions (hard walls): wrap changed to death unless wall segment is green
        def wall_hit(pos: tuple[int,int], prev: tuple[int,int]) -> bool:
            r, c = pos
            # detect if crossing a wall: compare prev and pos with boundaries
            if prev[0] == 0 and r == self.sn_rows - 1:  # crossed top wall
                return self.sn_walls['top'] == 'hard'
            if prev[0] == self.sn_rows - 1 and r == 0:  # crossed bottom
                return self.sn_walls['bottom'] == 'hard'
            if prev[1] == 0 and c == self.sn_cols - 1:  # crossed left
                return self.sn_walls['left'] == 'hard'
            if prev[1] == self.sn_cols - 1 and c == 0:  # crossed right
                return self.sn_walls['right'] == 'hard'
            return False

        h_wall = wall_hit(new_h, self.sn_host_snake[1])
        c_wall = wall_hit(new_c, self.sn_client_snake[1])

        # self-collision: if head appears elsewhere in same snake
        def self_hit(snk: list[tuple[int,int]]) -> bool:
            return snk[0] in snk[1:]

        h_self = h_wall or self_hit(self.sn_host_snake)
        c_self = c_wall or self_hit(self.sn_client_snake)

        # opponent body hit (exclude head-on-head)
        head_on = (new_h == new_c)
        if not head_on:
            if new_h in self.sn_client_snake:
                # cut opponent at hit
                self.sn_client_snake = self._snake_cut_at(self.sn_client_snake, new_h)
            if new_c in self.sn_host_snake:
                self.sn_host_snake = self._snake_cut_at(self.sn_host_snake, new_c)

        # check lose only for self-collision (including wall death)
        if h_self and c_self:
            # both crashed into themselves -> draw
            self.sn_status = 'over'
            self.sn_winner = 'draw'
        elif h_self:
            self.sn_status = 'over'
            self.sn_winner = 'client'
        elif c_self:
            self.sn_status = 'over'
            self.sn_winner = 'host'

        # walls lifecycle (host controls)
        self._snake_update_walls_lifecycle()

        # send state to client
        self.peer.send({
            'type': 'snake_state',
            'h_snake': self.sn_host_snake,
            'c_snake': self.sn_client_snake,
            'food': list(self.sn_food),
            'scores': self.sn_scores,
            'status': self.sn_status,
            'winner': self.sn_winner,
            'walls': self.sn_walls,
            'tick': self.sn_tick,
        })

    def draw_snake_scene(self) -> None:
        # Compute cell size to fit
        w, h = self.screen.get_width(), self.screen.get_height()
        avail_w = w - 2 * PANEL_PADDING
        avail_h = h - (TOP_BAR + BOTTOM_BAR)
        cell = int(min(avail_w / self.sn_cols, avail_h / self.sn_rows))
        grid_w = cell * self.sn_cols
        grid_h = cell * self.sn_rows
        x0 = (w - grid_w) // 2
        y0 = TOP_BAR
        # background
        pygame.draw.rect(self.screen, GRID_BG, (x0, y0, grid_w, grid_h), border_radius=8)
        # grid lines subtle
        for r in range(self.sn_rows + 1):
            y = y0 + r * cell
            pygame.draw.line(self.screen, (45, 52, 66), (x0, y), (x0 + grid_w, y))
        for c in range(self.sn_cols + 1):
            x = x0 + c * cell
            pygame.draw.line(self.screen, (45, 52, 66), (x, y0), (x, y0 + grid_h))
        # draw walls as colored borders (green=passable, red=deadly, blink flickers)
        def wall_color(state: str) -> tuple[int,int,int]:
            if state == 'green':
                return (90, 200, 120)
            if state == 'blink':
                return (120, 200, 120) if (time.time()*4) % 2 < 1 else (200, 80, 80)
            return (200, 80, 80)
        thick = max(4, cell // 6)
        # top
        pygame.draw.rect(self.screen, wall_color(self.sn_walls.get('top','hard')), (x0, y0 - thick//2, grid_w, thick))
        # bottom
        pygame.draw.rect(self.screen, wall_color(self.sn_walls.get('bottom','hard')), (x0, y0 + grid_h - thick//2, grid_w, thick))
        # left
        pygame.draw.rect(self.screen, wall_color(self.sn_walls.get('left','hard')), (x0 - thick//2, y0, thick, grid_h))
        # right
        pygame.draw.rect(self.screen, wall_color(self.sn_walls.get('right','hard')), (x0 + grid_w - thick//2, y0, thick, grid_h))
        # food
        fr, fc = self.sn_food
        fx = x0 + fc * cell + cell // 2
        fy = y0 + fr * cell + cell // 2
        pygame.draw.circle(self.screen, (250, 210, 90), (fx, fy), max(4, cell // 4))
        # snakes
        def draw_snake(snk: list[tuple[int,int]], head_color: tuple[int,int,int], body_color: tuple[int,int,int]):
            for i, (r, c) in enumerate(snk):
                xx = x0 + c * cell
                yy = y0 + r * cell
                col = head_color if i == 0 else body_color
                pygame.draw.rect(self.screen, col, (xx + 2, yy + 2, cell - 4, cell - 4), border_radius=6 if i == 0 else 4)
        draw_snake(self.sn_host_snake, (90, 200, 120), (60, 140, 90))
        draw_snake(self.sn_client_snake, (90, 160, 245), (60, 110, 170))
        # scores and wall indicators
        score_txt = self.font.render(f"A(host): {self.sn_scores['host']}   B(client): {self.sn_scores['client']}", True, TEXT)
        self.screen.blit(score_txt, (PANEL_PADDING, 20))
        # wall state indicators
        wx = w - PANEL_PADDING - 220
        states = []
        for side in ('top','bottom','left','right'):
            st = self.sn_walls.get(side, 'hard')
            if st == 'green':
                col = (90, 200, 120)
            elif st == 'blink':
                # blink color between green and red
                t = (time.time() * 4) % 2
                col = (120, 200, 120) if t < 1 else (200, 100, 100)
            else:
                col = (200, 80, 80)
            txt = self.font_small.render(f"{side}: {st}", True, col)
            self.screen.blit(txt, (wx, 20 + len(states)*20))
            states.append(side)
        if self.sn_status == 'over':
            if self.sn_winner == 'host':
                msg = "Snake: Host wins!"
            elif self.sn_winner == 'client':
                msg = "Snake: Client wins!"
            else:
                msg = "Snake: Draw"
            surf = self.font_big.render(msg, True, VICTORY if self.sn_winner in ('host','client') else TEXT)
            self.screen.blit(surf, (w//2 - surf.get_width()//2, 40))

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
        placement_done_local = False
        placement_done_remote = False

        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    try:
                        self.peer.send({"type": "quit"})
                    except Exception:
                        pass
                    self.running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.state == "lobby":
                        # click on a lobby button
                        for rect, name in getattr(self, "_lobby_buttons", []):
                            if rect.collidepoint(event.pos):
                                self.my_choice = name
                                self.peer.send({"type": "game_select", "game": name})
                    elif self.state == "battleship" and self.game_over is None:
                        # in battleship gameplay
                        if self.placing_index < len(SHIP_TYPES):
                            if event.button == 1:
                                self.place_ships_handle_click(event.pos)
                            elif event.button == 3:
                                self.horizontal = not self.horizontal
                        else:
                            if event.button == 1:
                                self.click_fire(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        try:
                            self.peer.send({"type": "quit"})
                        except Exception:
                            pass
                        self.running = False
                    if self.state == "battleship" and event.key == pygame.K_r and self.placing_index < len(SHIP_TYPES):
                        self.horizontal = not self.horizontal
                    if self.state == 'snake':
                        # local input: WASD arrows
                        keymap = {
                            pygame.K_w: 'U', pygame.K_UP: 'U',
                            pygame.K_s: 'D', pygame.K_DOWN: 'D',
                            pygame.K_a: 'L', pygame.K_LEFT: 'L',
                            pygame.K_d: 'R', pygame.K_RIGHT: 'R',
                        }
                        if event.key in keymap:
                            d = keymap[event.key]
                            if self.mode == 'host':
                                self.sn_host_desired = d
                            else:
                                self.sn_client_desired = d
                                # client sends desired dir to host
                                self.peer.send({'type': 'snake_dir', 'dir': d})

            # If hosting and connected, move to lobby immediately
            if self.mode == 'host' and self.state == 'waiting' and self.peer.connected:
                self.available_games = ["Battleship", "Snake"]
                self.state = 'lobby'

            # Poll incoming
            msg = self.peer.try_get(0.0)
            while msg is not None:
                mtype = msg.get("type")
                if self.state == "waiting":
                    if mtype == "lobby":
                        self.available_games = list(msg.get("games", []))
                        self.state = "lobby"
                elif self.state == "lobby":
                    if mtype == "game_select":
                        # peer's choice arrived; track it
                        self.peer_choice = msg.get("game")
                    elif mtype == "game_chosen":
                        self.chosen_game = str(msg.get("game"))
                        if self.chosen_game == "Battleship":
                            # Battleship setup
                            self.my_board = Board()
                            self.opp_known = Board()
                            self.placing_index = 0
                            self.horizontal = True
                            # Host decides turn after placement with start message; we keep logic same
                            if self.mode == "host":
                                # Tell client that they do not start (host starts)
                                self.peer.send({"type": "start", "youStart": False})
                                self.turn_is_mine = True
                            else:
                                self.turn_is_mine = None
                            self.state = "battleship"
                            self.info_message = "Place your fleet"
                        elif self.chosen_game == "Snake":
                            # Initialize snake game shared state
                            self.start_snake()
                elif self.state == "snake":
                    # Client receives initialization and subsequent ticks
                    if mtype == 'snake_init' and self.mode == 'client':
                        self.sn_rows = int(msg.get('rows', self.sn_rows))
                        self.sn_cols = int(msg.get('cols', self.sn_cols))
                        self.sn_host_snake = [tuple(x) for x in msg.get('h_snake', [])]
                        self.sn_client_snake = [tuple(x) for x in msg.get('c_snake', [])]
                        food = msg.get('food')
                        if food:
                            self.sn_food = (int(food[0]), int(food[1]))
                        self.sn_scores = {'host': 0, 'client': 0}
                        self.sn_status = 'ongoing'
                        self.state = 'snake'
                    elif mtype == 'snake_dir' and self.mode == 'host':
                        d = str(msg.get('dir',''))
                        if d in ('U','D','L','R'):
                            self.sn_client_desired = d
                    elif mtype == 'snake_state':
                        self.sn_host_snake = [tuple(x) for x in msg.get('h_snake', [])]
                        self.sn_client_snake = [tuple(x) for x in msg.get('c_snake', [])]
                        food = msg.get('food')
                        if food:
                            self.sn_food = (int(food[0]), int(food[1]))
                        sc = msg.get('scores') or {}
                        self.sn_scores['host'] = int(sc.get('host', self.sn_scores['host']))
                        self.sn_scores['client'] = int(sc.get('client', self.sn_scores['client']))
                        self.sn_status = msg.get('status', self.sn_status)
                        self.sn_winner = msg.get('winner')
                        # sync walls/tick info if present
                        walls = msg.get('walls')
                        if walls:
                            self.sn_walls = walls
                        t = msg.get('tick')
                        if t:
                            self.sn_tick = float(t)
                elif self.state == "battleship":

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

            # If we are host and in lobby and both made a choice, decide and notify
            if self.mode == "host" and self.state == "lobby" and self.my_choice is not None:
                # If client also chose, resolve; otherwise wait until they do
                if self.peer_choice is not None:
                    chosen = self.my_choice if (self.peer_choice == self.my_choice) else random.choice([self.my_choice, self.peer_choice])
                    self.peer.send({"type": "game_chosen", "game": chosen})
                    self.chosen_game = chosen
                    # Locally dispatch immediately (host won't receive its own message)
                    if chosen == "Battleship":
                        self.my_board = Board()
                        self.opp_known = Board()
                        self.placing_index = 0
                        self.horizontal = True
                        # Tell client they don't start; host begins
                        self.peer.send({"type": "start", "youStart": False})
                        self.turn_is_mine = True
                        self.state = "battleship"
                        self.info_message = "Place your fleet"
                    elif chosen == "Snake":
                        self.start_snake()
                    self.my_choice = None

            # Battleship transitions: after placement
            if self.state == "battleship":
                if self.placing_index >= len(SHIP_TYPES) and not placement_done_local:
                    placement_done_local = True
                    self.peer.send({"type": "place_done"})
                    self.info_message = "Waiting for opponent to finish placement..."
                if placement_done_local and placement_done_remote and (self.mode == "host" or self.turn_is_mine is not None):
                    if self.turn_is_mine:
                        self.info_message = "Your turn: click on the right board to fire."
                    else:
                        self.info_message = "Waiting for opponent..."

            # Snake tick (host authoritative)
            if self.state == 'snake' and self.mode == 'host' and self.sn_status == 'ongoing':
                now = time.time()
                if now >= self.sn_next_tick:
                    self.sn_next_tick = now + self.sn_tick
                    self.snake_tick_host()

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


def run_host_gui_main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LAN Battleship GUI - Host")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--bind", type=str, default="0.0.0.0")
    args = parser.parse_args()
    run_host_gui(port=args.port, bind=args.bind)


def run_client_gui_main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="LAN Battleship GUI - Join")
    parser.add_argument("host", type=str, help="Host IP or name")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    run_client_gui(host=args.host, port=args.port)
