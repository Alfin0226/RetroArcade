from __future__ import annotations
import sys
import pygame
import asyncio
from settings import Settings, ensure_directories, init_pygame_window
from systems.sound_manager import SoundManager
from games import GAME_REGISTRY
from leaderboard import LeaderboardView
from user import login_user, register_user
from database import DatabaseManager, db as global_db

MENU_OPTIONS = ["snake", "tetris", "pac_man", "space_invaders", "hybrid", "leaderboard", "quit"]

class ArcadeApp:
    def __init__(self):
        ensure_directories()
        pygame.init()
        pygame.mixer.init()
        self.cfg = Settings()
        self.screen = init_pygame_window(self.cfg)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 28)
        self.sounds = SoundManager()
        self.load_sounds()
        self.state = "menu"
        self.menu_index = 0
        self.active_game = None
        self.username = ""
        self.leaderboard = LeaderboardView(self.screen, self.cfg, self.font)
        self.menu_button_rects: list[tuple[str, pygame.Rect]] = []
        # Pause state
        self.paused: bool = False
        self.pause_button_rects: list[tuple[str, pygame.Rect]] = []
        # Settings UI
        self.menu_settings_rect: pygame.Rect | None = None
        self.settings_button_rects: list[tuple[str, pygame.Rect]] = []
        self.settings_return_state: str = "menu"  # "menu" or "pause"
        # Remember last windowed size when toggling fullscreen
        self.windowed_size = self.cfg.screen_size
        self.db: DatabaseManager | None = None
        asyncio.run(self._init_database())

    async def _init_database(self):
        """Initialize database connection asynchronously."""
        self.db = DatabaseManager(self.cfg.db)
        await self.db.connect()
        global global_db
        global_db = self.db

    def load_sounds(self) -> None:
        self.sounds.load_sound("eat", "eat.wav")
        self.sounds.load_sound("shoot", "shoot.wav")
        self.sounds.load_sound("power_up", "power_up.wav")
        self.sounds.load_sound("line_clear", "line_clear.wav")
        self.sounds.load_sound("game_over", "game_over.wav")
        self.sounds.load_music("bg_music.mp3")
        self.sounds.play_music()

    def cleanup(self):
        """Clean up resources before exit."""
        if self.db:
            asyncio.run(self.db.disconnect())
        pygame.quit()

    def run(self) -> None:
        try:
            while True:
                dt = self.clock.tick(self.cfg.fps) / 1000.0
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        pygame.quit()
                        sys.exit()
                    self.handle_event(event)
                self.update(dt)
                self.draw()
                pygame.display.flip()
        finally:
            self.cleanup()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "menu":
            self.handle_menu_event(event)
        elif self.state == "game" and self.active_game:
            # Toggle pause on ESC
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.paused = not self.paused
                return
            # From games: request to go back to menu
            if event.type == pygame.USEREVENT and getattr(event, "action", None) == "back_to_menu":
                self.active_game.stop()
                self.active_game = None
                self.paused = False
                self.state = "menu"
                return
            # While paused, handle pause/settings only
            if self.paused:
                self.handle_pause_event(event)
            else:
                self.active_game.handle_event(event)
        elif self.state == "leaderboard":
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.state = "menu"
        elif self.state == "settings":
            self.handle_settings_event(event)

    def handle_menu_event(self, event: pygame.event.Event) -> None:
        # Ensure rects exist for hit-testing
        if not self.menu_button_rects:
            self.build_menu_buttons()
        # Build settings button rect for hit-testing
        if not self.menu_settings_rect:
            self.menu_settings_rect = self.build_menu_settings_button()

        if event.type == pygame.MOUSEMOTION:
            mx, my = event.pos
            for idx, (option, rect) in enumerate(self.menu_button_rects):
                if rect.collidepoint(mx, my):
                    self.menu_index = idx
                    break
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # Top-right settings button
            if self.menu_settings_rect and self.menu_settings_rect.collidepoint(mx, my):
                self.settings_return_state = "menu"
                self.state = "settings"
                return
            # Menu buttons
            for option, rect in self.menu_button_rects:
                if rect.collidepoint(mx, my):
                    if option == "leaderboard":
                        self.state = "leaderboard"
                    elif option == "quit":
                        pygame.quit()
                        sys.exit()
                    else:
                        self.start_game(option)
                    break

    def start_game(self, key: str) -> None:
        GameClass = GAME_REGISTRY[key]
        self.active_game = GameClass(self.screen, self.cfg, self.sounds)
        self.active_game.start()
        self.state = "game"

    def update(self, dt: float) -> None:
        if self.state == "game" and self.active_game:
            if not self.paused:
                self.active_game.update(dt)

    def draw(self) -> None:
        if self.state == "menu":
            self.draw_menu()
        elif self.state == "game" and self.active_game:
            self.screen.fill((10, 10, 24))
            self.active_game.draw()
            if self.paused:
                self.draw_pause_menu()
        elif self.state == "leaderboard":
            self.screen.fill((8, 8, 16))
            self.leaderboard.draw()
        elif self.state == "settings":
            # Draw underlying context, then overlay settings
            if self.settings_return_state == "menu":
                self.draw_menu()
            else:
                self.screen.fill((10, 10, 24))
                if self.active_game:
                    self.active_game.draw()
                # If coming from pause, keep it dimmed similarly
            self.draw_settings_menu()

    # ----- Display mode helpers (already present earlier) -----
    def toggle_fullscreen(self) -> None:
        if not self.cfg.fullscreen:
            # Entering fullscreen: remember windowed size
            self.windowed_size = self.cfg.screen_size
            self.cfg.fullscreen = True
        else:
            # Leaving fullscreen: restore windowed size
            self.cfg.fullscreen = False
            self.cfg.width, self.cfg.height = self.windowed_size
        self.apply_display_mode()

    def apply_display_mode(self) -> None:
        # Recreate display surface based on current cfg
        self.screen = init_pygame_window(self.cfg)
        # Update references that draw onto the screen
        self.leaderboard.screen = self.screen
        if self.active_game:
            self.active_game.screen = self.screen
            self.active_game.cfg = self.cfg

    # ----- Pause menu helpers -----
    def handle_pause_event(self, event: pygame.event.Event) -> None:
        if not self.pause_button_rects:
            self.build_pause_buttons()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for key, rect in self.pause_button_rects:
                if rect.collidepoint(mx, my):
                    if key == "resume":
                        self.paused = False
                    elif key == "restart":
                        self.active_game.reset()
                        self.paused = False
                    elif key == "settings":
                        self.settings_return_state = "pause"
                        self.state = "settings"
                    elif key == "back":
                        self.active_game.stop()
                        self.active_game = None
                        self.paused = False
                        self.state = "menu"
                    break

    def build_pause_buttons(self) -> None:
        self.pause_button_rects.clear()
        labels = [("resume", "Resume"), ("settings", "Settings"), ("restart", "Restart"), ("back", "Back To Main Menu")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 360
        total_h = len(labels) * spacing
        start_y = self.cfg.height // 2 - total_h // 2
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.pause_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def draw_pause_menu(self) -> None:
        # Dim background
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        # Title
        title = self.font.render("Paused", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 140))

        # Buttons
        self.build_pause_buttons()
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.pause_button_rects:
            label = {
                "resume": "Resume",
                "settings": "Settings",
                "restart": "Restart",
                "back": "Back To Main Menu",
            }[key]
            hovered = rect.collidepoint(*mouse_pos)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.font.render(label, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))

    # ----- Settings overlay -----
    def handle_settings_event(self, event: pygame.event.Event) -> None:
        if not self.settings_button_rects:
            self.build_settings_buttons()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            for key, rect in self.settings_button_rects:
                if rect.collidepoint(mx, my):
                    if key == "toggle_fullscreen":
                        self.toggle_fullscreen()
                        # Rebuild button rects after potential size change
                        self.settings_button_rects.clear()
                    elif key == "back":
                        # Return to previous context
                        if self.settings_return_state == "menu":
                            self.state = "menu"
                        else:
                            self.state = "game"
                            self.paused = True
                    break

    def build_settings_buttons(self) -> None:
        self.settings_button_rects.clear()
        labels = [("toggle_fullscreen", "Toggle Fullscreen"), ("back", "Back")]
        spacing = 64
        padding_x, padding_y = 22, 12
        button_width = 420
        total_h = len(labels) * spacing
        start_y = self.cfg.height // 2 - total_h // 2 + 20
        for i, (key, text) in enumerate(labels):
            surf = self.font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            y = start_y + i * spacing
            self.settings_button_rects.append((key, pygame.Rect(x, y, w, h)))

    def draw_settings_menu(self) -> None:
        # Dim background overlay
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Title
        title = self.font.render("Settings", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 140))

        # Buttons
        self.build_settings_buttons()
        mouse_pos = pygame.mouse.get_pos()
        for key, rect in self.settings_button_rects:
            label = "Toggle Fullscreen" if key == "toggle_fullscreen" else "Back"
            hovered = rect.collidepoint(*mouse_pos)
            fill = (70, 80, 120) if hovered else (40, 45, 85)
            border = (255, 255, 255) if hovered else (140, 150, 190)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
            text_surf = self.font.render(label, True, (255, 255, 255))
            tx = rect.x + (rect.width - text_surf.get_width()) // 2
            ty = rect.y + (rect.height - text_surf.get_height()) // 2
            self.screen.blit(text_surf, (tx, ty))

    # ----- Menu drawing with top-right settings button -----
    def build_menu_settings_button(self) -> pygame.Rect:
        # Size and position for top-right settings button
        padding = 14
        label = "Settings"
        text_surf = self.font.render(label, True, (255, 255, 255))
        tw, th = text_surf.get_size()
        w, h = max(140, tw + 24), th + 14
        x = self.cfg.width - w - padding
        y = padding
        return pygame.Rect(x, y, w, h)

    def draw_menu(self) -> None:
        self.screen.fill((20, 20, 50))
        title = self.font.render("Retro Arcade Game", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, 80))

        # Rebuild each frame to adapt to window size/font metrics
        self.build_menu_buttons()
        mouse_pos = pygame.mouse.get_pos()

        for idx, (option, rect) in enumerate(self.menu_button_rects):
            label = option.replace("_", " ").title()
            text_surf = self.font.render(label, True, (255, 255, 255))
            text_w, text_h = text_surf.get_size()

            hovered = rect.collidepoint(*mouse_pos)
            if hovered:
                self.menu_index = idx

            fill_color = (60, 70, 120) if hovered else (35, 40, 80)
            border_color = (255, 255, 255) if hovered else (120, 130, 180)

            pygame.draw.rect(self.screen, fill_color, rect, border_radius=8)
            pygame.draw.rect(self.screen, border_color, rect, width=2, border_radius=8)

            text_x = rect.x + (rect.width - text_w) // 2
            text_y = rect.y + (rect.height - text_h) // 2
            self.screen.blit(text_surf, (text_x, text_y))

        # Draw or update menu settings button
        self.menu_settings_rect = self.build_menu_settings_button()
        hovered = self.menu_settings_rect.collidepoint(*pygame.mouse.get_pos())
        fill = (70, 80, 120) if hovered else (40, 45, 85)
        border = (255, 255, 255) if hovered else (140, 150, 190)
        pygame.draw.rect(self.screen, fill, self.menu_settings_rect, border_radius=8)
        pygame.draw.rect(self.screen, border, self.menu_settings_rect, width=2, border_radius=8)
        text = self.font.render("Settings", True, (255, 255, 255))
        tx = self.menu_settings_rect.x + (self.menu_settings_rect.width - text.get_width()) // 2
        ty = self.menu_settings_rect.y + (self.menu_settings_rect.height - text.get_height()) // 2
        self.screen.blit(text, (tx, ty))

    def build_menu_buttons(self) -> None:
        # Compute and cache menu button rects for mouse hit-testing
        self.menu_button_rects.clear()
        base_y = 180
        spacing = 52
        padding_x = 18
        padding_y = 10
        button_width = 320
        for idx, option in enumerate(MENU_OPTIONS):
            label = option.replace("_", " ").title()
            text_surf = self.font.render(label, True, (255, 255, 255))
            tw, th = text_surf.get_size()
            btn_w = max(button_width, tw + padding_x * 2)
            btn_h = th + padding_y * 2
            x = self.cfg.width // 2 - btn_w // 2
            y = base_y + idx * spacing
            self.menu_button_rects.append((option, pygame.Rect(x, y, btn_w, btn_h)))

if __name__ == "__main__":
    ArcadeApp().run()
