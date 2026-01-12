from __future__ import annotations
import sys
import pygame
import asyncio
from settings import Settings, ensure_directories, init_pygame_window
from systems.sound_manager import SoundManager
from systems.rules import set_difficulty, get_difficulty
from games import GAME_REGISTRY
from leaderboard import LeaderboardView
from user import UserSession
import database
from database import DatabaseManager
from login_register_menu import LoginRegisterMenu
from async_helper import run_async, stop_async_loop

MENU_OPTIONS = ["snake", "tetris", "pac_man", "space_invaders", "hybrid", "leaderboard", "quit"]
DIFFICULTY_OPTIONS = ["easy", "intermediate", "hard"]

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
        self.state = "login"  # Start with login screen
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
        self.menu_login_rect: pygame.Rect | None = None  # Top-left login/logout button
        self.settings_button_rects: list[tuple[str, pygame.Rect]] = []
        self.settings_slider_rects: dict[str, tuple[pygame.Rect, pygame.Rect]] = {}  # label_rect, slider_rect
        self.settings_return_state: str = "menu"  # "menu" or "pause"
        self.dragging_slider: str | None = None  # Which slider is being dragged
        # Remember last windowed size when toggling fullscreen
        self.windowed_size = self.cfg.screen_size
        self.db: DatabaseManager | None = None
        run_async(self._init_database())
        # Login/Register menu
        self.login_menu: LoginRegisterMenu | None = None
        self.session: UserSession = UserSession()
        self._init_login_menu()

    async def _init_database(self):
        """Initialize database connection asynchronously."""
        self.db = DatabaseManager(self.cfg.db)
        await self.db.connect()
        # Update the module-level db variable so games can access it
        database.db = self.db

    def _init_login_menu(self):
        """Initialize the login/register menu."""
        if self.db:
            self.login_menu = LoginRegisterMenu(self.screen, self.cfg, self.font, self.db)

    def load_sounds(self) -> None:
        # Load all default sounds
        self.sounds.load_assets()
        # Also load specific sounds that might have different filenames
        self.sounds.load_sound("eat", "eat.mp3")
        self.sounds.load_sound("shoot", "shoot.wav")
        self.sounds.load_sound("power_up", "power_up.wav")
        self.sounds.load_sound("line_clear", "line_clear.wav")
        self.sounds.load_sound("game_over", "game_over.wav")
        self.sounds.load_music("bg_music.mp3")
        # Apply initial volume settings
        self.sounds.set_volume(self.cfg.audio.sfx_volume)
        self.sounds.set_music_volume(self.cfg.audio.music_volume)
        self.sounds.set_muted(self.cfg.audio.muted)
        self.sounds.play_music()

    def _draw_fps(self) -> None:
        """Draw FPS counter in bottom-left corner."""
        fps = int(self.clock.get_fps())
        fps_text = self.font.render(f"FPS: {fps}", True, (0, 255, 0))
        # Position in bottom-left corner
        x = 14
        y = self.cfg.height - fps_text.get_height() - 14
        # Draw background for readability
        bg_rect = pygame.Rect(x - 4, y - 2, fps_text.get_width() + 8, fps_text.get_height() + 4)
        pygame.draw.rect(self.screen, (0, 0, 0, 150), bg_rect, border_radius=4)
        self.screen.blit(fps_text, (x, y))

    def cleanup(self):
        """Clean up resources before exit."""
        if self.db:
            run_async(self.db.disconnect())
        stop_async_loop()
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
                if self.cfg.show_fps:
                    self._draw_fps()
                pygame.display.flip()
        finally:
            self.cleanup()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.state == "login":
            self.handle_login_event(event)
        elif self.state == "menu":
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
            result = self.leaderboard.handle_event(event)
            if result == "back":
                self.state = "menu"
        elif self.state == "settings":
            self.handle_settings_event(event)

    def handle_login_event(self, event: pygame.event.Event) -> None:
        """Handle events for the login/register menu."""
        if self.login_menu:
            result = self.login_menu.handle_event(event)
            if result == "logged_in":
                # User logged in successfully
                self.session = self.login_menu.session
                self.username = self.session.username or ""
                self.state = "menu"
            elif result == "guest":
                # Continue as guest
                self.session = self.login_menu.session
                self.username = "Guest"
                self.state = "menu"

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
            # Top-left login/logout button
            if self.menu_login_rect and self.menu_login_rect.collidepoint(mx, my):
                if self.session.is_logged_in:
                    self.do_logout()
                else:
                    # Guest mode - go to login screen
                    self.state = "login"
                    if self.login_menu:
                        self.login_menu.reset()
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

    def do_logout(self) -> None:
        """Log out the current user and return to login screen."""
        self.session.logout()
        self.username = ""
        if self.login_menu:
            self.login_menu.reset()
        self.state = "login"

    def start_game(self, key: str) -> None:
        GameClass = GAME_REGISTRY[key]
        # Pass user_id for score tracking (None for guests)
        user_id = self.session.user_id if self.session.is_logged_in else None
        self.active_game = GameClass(self.screen, self.cfg, self.sounds, user_id=user_id)
        self.active_game.start()
        self.state = "game"

    def update(self, dt: float) -> None:
        if self.state == "login" and self.login_menu:
            self.login_menu.update(dt)
        elif self.state == "game" and self.active_game:
            if not self.paused:
                self.active_game.update(dt)

    def draw(self) -> None:
        if self.state == "login":
            if self.login_menu:
                self.login_menu.draw()
        elif self.state == "menu":
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
        if self.login_menu:
            self.login_menu.screen = self.screen
            self.login_menu.cfg = self.cfg
            self.login_menu.fields_built = False  # Rebuild fields for new size
        if self.active_game:
            self.active_game.screen = self.screen
            self.active_game.cfg = self.cfg

    def handle_pause_event(self, event: pygame.event.Event) -> None:
        if not self.pause_button_rects: # if esc is pressed call the build pause buttons
            self.build_pause_buttons()
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: #find which button is clicked
            mx, my = event.pos
            for key, rect in self.pause_button_rects: # perform button actions
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
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        self.screen.blit(overlay, (0, 0))

        title = self.font.render("Paused", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 200))

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
        
        # Handle slider dragging
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            mx, my = event.pos
            # Check if clicking on a slider
            for slider_key, (label_rect, slider_rect) in self.settings_slider_rects.items():
                if slider_rect.collidepoint(mx, my):
                    self.dragging_slider = slider_key
                    self._update_slider_value(slider_key, mx, slider_rect)
                    return
            
            # Check buttons
            for key, rect in self.settings_button_rects:
                if rect.collidepoint(mx, my):
                    if key == "toggle_fullscreen":
                        self.toggle_fullscreen()
                        self.settings_button_rects.clear()
                        self.settings_slider_rects.clear()
                    elif key == "toggle_mute":
                        self.cfg.audio.muted = not self.cfg.audio.muted
                        self.sounds.set_muted(self.cfg.audio.muted)
                    elif key == "toggle_fps":
                        self.cfg.show_fps = not self.cfg.show_fps
                    elif key == "difficulty_easy":
                        self.cfg.difficulty = "easy"
                        set_difficulty("easy")
                    elif key == "difficulty_intermediate":
                        self.cfg.difficulty = "intermediate"
                        set_difficulty("intermediate")
                    elif key == "difficulty_hard":
                        self.cfg.difficulty = "hard"
                        set_difficulty("hard")
                    elif key == "back":
                        self.dragging_slider = None
                        if self.settings_return_state == "menu":
                            self.state = "menu"
                        else:
                            self.state = "game"
                            self.paused = True
                    break
        
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging_slider = None
        
        elif event.type == pygame.MOUSEMOTION and self.dragging_slider:
            mx, my = event.pos
            if self.dragging_slider in self.settings_slider_rects:
                _, slider_rect = self.settings_slider_rects[self.dragging_slider]
                self._update_slider_value(self.dragging_slider, mx, slider_rect)

    def _update_slider_value(self, slider_key: str, mouse_x: int, slider_rect: pygame.Rect) -> None:
        """Update a slider value based on mouse position."""
        # Calculate value (0.0 to 1.0)
        relative_x = mouse_x - slider_rect.x
        value = max(0.0, min(1.0, relative_x / slider_rect.width))
        
        if slider_key == "sfx_volume":
            self.cfg.audio.sfx_volume = value
            self.sounds.set_volume(value)

    def build_settings_buttons(self) -> None:
        self.settings_button_rects.clear()
        self.settings_slider_rects.clear()
        
        start_y = self.cfg.height // 2 - 160
        spacing = 50
        button_width = 420
        slider_width = 200
        padding_x, padding_y = 22, 10
        current_y = start_y
        
        # Sliders for volume
        sliders = [
            ("sfx_volume", "SFX Volume", self.cfg.audio.sfx_volume),
        ]
        
        for key, label, value in sliders:
            label_surf = self.font.render(label, True, (255, 255, 255))
            label_rect = pygame.Rect(
                self.cfg.width // 2 - 200,
                current_y,
                150,
                label_surf.get_height()
            )
            slider_rect = pygame.Rect(
                self.cfg.width // 2,
                current_y,
                slider_width,
                20
            )
            self.settings_slider_rects[key] = (label_rect, slider_rect)
            current_y += spacing
        
        # Mute button
        mute_label = "Unmute" if self.cfg.audio.muted else "Mute"
        mute_surf = self.font.render(mute_label, True, (255, 255, 255))
        mute_w = max(150, mute_surf.get_width() + padding_x * 2)
        mute_h = mute_surf.get_height() + padding_y * 2
        self.settings_button_rects.append((
            "toggle_mute",
            pygame.Rect(self.cfg.width // 2 - mute_w // 2, current_y, mute_w, mute_h)
        ))
        current_y += spacing
        
        # Show FPS button
        fps_label = "Hide FPS" if self.cfg.show_fps else "Show FPS"
        fps_surf = self.font.render(fps_label, True, (255, 255, 255))
        fps_w = max(150, fps_surf.get_width() + padding_x * 2)
        fps_h = fps_surf.get_height() + padding_y * 2
        self.settings_button_rects.append((
            "toggle_fps",
            pygame.Rect(self.cfg.width // 2 - fps_w // 2, current_y, fps_w, fps_h)
        ))
        current_y += spacing + 10
        
        # Difficulty selection
        diff_label = self.font.render("Difficulty:", True, (255, 255, 255))
        diff_y = current_y
        current_y += 35
        
        # Difficulty buttons in a row
        diff_buttons = [
            ("difficulty_easy", "Easy"),
            ("difficulty_intermediate", "Normal"),
            ("difficulty_hard", "Hard"),
        ]
        button_w = 100
        total_w = len(diff_buttons) * button_w + (len(diff_buttons) - 1) * 10
        start_x = self.cfg.width // 2 - total_w // 2
        
        for i, (key, label) in enumerate(diff_buttons):
            btn_rect = pygame.Rect(
                start_x + i * (button_w + 10),
                current_y,
                button_w,
                32
            )
            self.settings_button_rects.append((key, btn_rect))
        
        current_y += spacing + 20
        
        # Fullscreen and Back buttons
        other_buttons = [("toggle_fullscreen", "Toggle Fullscreen"), ("back", "Back")]
        for key, text in other_buttons:
            surf = self.font.render(text, True, (255, 255, 255))
            tw, th = surf.get_size()
            w = max(button_width, tw + padding_x * 2)
            h = th + padding_y * 2
            x = self.cfg.width // 2 - w // 2
            self.settings_button_rects.append((key, pygame.Rect(x, current_y, w, h)))
            current_y += spacing

    def draw_settings_menu(self) -> None:
        overlay = pygame.Surface(self.cfg.screen_size, pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Title
        title = self.font.render("Settings", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, self.cfg.height // 2 - 220))

        # Build/update UI elements
        self.build_settings_buttons()
        mouse_pos = pygame.mouse.get_pos()
        
        # Draw sliders
        for slider_key, (label_rect, slider_rect) in self.settings_slider_rects.items():
            # Draw label
            label = "SFX Volume"
            value = self.cfg.audio.sfx_volume
            
            label_surf = self.font.render(label, True, (255, 255, 255))
            self.screen.blit(label_surf, (label_rect.x, label_rect.y))
            
            # Draw slider background
            pygame.draw.rect(self.screen, (60, 60, 80), slider_rect, border_radius=4)
            pygame.draw.rect(self.screen, (100, 110, 140), slider_rect, 2, border_radius=4)
            
            # Draw slider fill
            fill_width = int(slider_rect.width * value)
            if fill_width > 0:
                fill_rect = pygame.Rect(slider_rect.x, slider_rect.y, fill_width, slider_rect.height)
                pygame.draw.rect(self.screen, (100, 150, 220), fill_rect, border_radius=4)
            
            # Draw slider handle
            handle_x = slider_rect.x + fill_width - 5
            handle_rect = pygame.Rect(handle_x, slider_rect.y - 3, 10, slider_rect.height + 6)
            pygame.draw.rect(self.screen, (255, 255, 255), handle_rect, border_radius=3)
            
            # Draw percentage
            pct_text = self.font.render(f"{int(value * 100)}%", True, (200, 200, 200))
            self.screen.blit(pct_text, (slider_rect.right + 15, slider_rect.y - 5))
        
        # Draw difficulty label
        diff_label = self.font.render("Difficulty:", True, (255, 255, 255))
        diff_y = self.cfg.height // 2 - 160 + 50 * 3 + 50 + 10  # After sliders, mute, and fps toggle
        self.screen.blit(diff_label, (self.cfg.width // 2 - diff_label.get_width() // 2, diff_y))
        
        # Draw buttons
        for key, rect in self.settings_button_rects:
            # Determine label text
            if key == "toggle_fullscreen":
                label = "Toggle Fullscreen"
            elif key == "toggle_mute":
                label = "Unmute" if self.cfg.audio.muted else "Mute"
            elif key == "toggle_fps":
                label = "Hide FPS" if self.cfg.show_fps else "Show FPS"
            elif key == "back":
                label = "Back"
            elif key == "difficulty_easy":
                label = "Easy"
            elif key == "difficulty_intermediate":
                label = "Normal"
            elif key == "difficulty_hard":
                label = "Hard"
            else:
                label = key
            
            hovered = rect.collidepoint(*mouse_pos)
            
            # Special styling for difficulty buttons
            if key.startswith("difficulty_"):
                diff_level = key.replace("difficulty_", "")
                is_selected = self.cfg.difficulty == diff_level
                if is_selected:
                    fill = (80, 140, 80)  # Green for selected
                    border = (120, 200, 120)
                elif hovered:
                    fill = (70, 80, 120)
                    border = (255, 255, 255)
                else:
                    fill = (40, 45, 85)
                    border = (140, 150, 190)
            else:
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

    def build_menu_login_button(self) -> pygame.Rect:
        # Size and position for top-left login/logout button
        padding = 14
        # Show "Logout" if logged in, "Login" if guest
        label = "Logout" if self.session.is_logged_in else "Login"
        text_surf = self.font.render(label, True, (255, 255, 255))
        tw, th = text_surf.get_size()
        w, h = max(140, tw + 24), th + 14
        x = padding
        y = padding
        return pygame.Rect(x, y, w, h)

    def draw_menu(self) -> None:
        self.screen.fill((20, 20, 50))
        title = self.font.render("Retro Arcade Game", True, (255, 255, 255))
        self.screen.blit(title, (self.cfg.width // 2 - title.get_width() // 2, 60))
        
        # Show logged-in user info
        if self.username:
            user_text = f"Welcome, {self.username}!"
            user_surf = self.font.render(user_text, True, (150, 200, 150))
            self.screen.blit(user_surf, (self.cfg.width // 2 - user_surf.get_width() // 2, 110))

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

        # Draw or update menu settings button (top-right)
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

        # Draw login/logout button (top-left)
        self.menu_login_rect = self.build_menu_login_button()
        login_label = "Logout" if self.session.is_logged_in else "Login"
        hovered = self.menu_login_rect.collidepoint(*pygame.mouse.get_pos())
        fill = (70, 80, 120) if hovered else (40, 45, 85)
        border = (255, 255, 255) if hovered else (140, 150, 190)
        pygame.draw.rect(self.screen, fill, self.menu_login_rect, border_radius=8)
        pygame.draw.rect(self.screen, border, self.menu_login_rect, width=2, border_radius=8)
        text = self.font.render(login_label, True, (255, 255, 255))
        tx = self.menu_login_rect.x + (self.menu_login_rect.width - text.get_width()) // 2
        ty = self.menu_login_rect.y + (self.menu_login_rect.height - text.get_height()) // 2
        self.screen.blit(text, (tx, ty))

    def build_menu_buttons(self) -> None:
        # Compute and cache menu button rects for mouse hit-testing
        self.menu_button_rects.clear()
        base_y = 160
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
