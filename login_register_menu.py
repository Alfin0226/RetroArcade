from __future__ import annotations
import pygame
import asyncio
import re
import subprocess
from typing import Optional, Callable, TYPE_CHECKING
from user import register_user_async, login_user_async, UserSession

if TYPE_CHECKING:
    from database import DatabaseManager
    from settings import Settings


class TextInputField:
    """A text input field for pygame with cursor and focus support."""
    
    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        font: pygame.font.Font,
        label: str = "",
        placeholder: str = "",
        is_password: bool = False,
        max_length: int = 50
    ):
        self.rect = pygame.Rect(x, y, width, height)
        self.font = font
        self.label = label
        self.placeholder = placeholder
        self.is_password = is_password
        self.max_length = max_length
        
        self.text = ""
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0
        
        # Track held keys to prevent key repeat
        self.keys_held: set[int] = set()
        
        # Show password toggle (only for password fields)
        self.show_password = False
        self.show_password_rect: Optional[pygame.Rect] = None
        if self.is_password:
            # Button positioned at the right end of the input field
            btn_size = height - 8
            self.show_password_rect = pygame.Rect(
                x + width - btn_size - 4,
                y + 4,
                btn_size,
                btn_size
            )
        
        # Colors
        self.color_inactive = (80, 90, 130)
        self.color_active = (100, 120, 200)
        self.color_text = (255, 255, 255)
        self.color_placeholder = (120, 130, 160)
        self.color_label = (200, 210, 240)
        self.color_bg = (30, 35, 60)
    
    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle input events. Returns True if text changed."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            # Check if clicking show password button
            if self.is_password and self.show_password_rect and self.show_password_rect.collidepoint(event.pos):
                self.show_password = not self.show_password
                return False
            
            self.active = self.rect.collidepoint(event.pos)
            return False
        
        # Track key releases to allow the key to be pressed again
        if event.type == pygame.KEYUP:
            self.keys_held.discard(event.key)
            return False
        
        if event.type == pygame.KEYDOWN and self.active:
            # Get modifier keys
            mods = pygame.key.get_mods()
            ctrl_held = mods & pygame.KMOD_CTRL
            
            # Handle Ctrl shortcuts (don't block these)
            if ctrl_held:
                if event.key == pygame.K_a:
                    # Select all - clear and prepare for new input
                    return False
                elif event.key == pygame.K_c:
                    # Copy to clipboard using Windows clip command
                    try:
                        process = subprocess.Popen(
                            ['clip'],
                            stdin=subprocess.PIPE,
                            shell=True
                        )
                        process.communicate(self.text.encode('utf-8'))
                    except:
                        pass
                    return False
                elif event.key == pygame.K_v:
                    # Paste from clipboard using Windows PowerShell
                    try:
                        result = subprocess.run(
                            ['powershell', '-command', 'Get-Clipboard'],
                            capture_output=True,
                            text=True,
                            shell=True
                        )
                        if result.returncode == 0:
                            paste_text = result.stdout.strip()
                            # Filter to printable characters only
                            paste_text = ''.join(c for c in paste_text if c.isprintable())
                            # Respect max length
                            remaining = self.max_length - len(self.text)
                            if remaining > 0 and paste_text:
                                self.text += paste_text[:remaining]
                                return True
                    except:
                        pass
                    return False
            
            # Allow backspace to repeat (don't add to keys_held)
            if event.key == pygame.K_BACKSPACE:
                if self.text:
                    self.text = self.text[:-1]
                    return True
                return False
            
            # Check if key is already held (prevent key repeat for other keys)
            if event.key in self.keys_held:
                return False
            self.keys_held.add(event.key)
            
            if event.key == pygame.K_TAB:
                return False  # Let parent handle tab
            elif event.key == pygame.K_RETURN:
                return False  # Let parent handle enter
            elif event.unicode and len(self.text) < self.max_length:
                # Filter out control characters
                if event.unicode.isprintable():
                    self.text += event.unicode
                    return True
        return False
    
    def update(self, dt: float) -> None:
        """Update cursor blink."""
        self.cursor_timer += dt
        if self.cursor_timer >= 0.5:
            self.cursor_timer = 0
            self.cursor_visible = not self.cursor_visible
    
    def draw(self, screen: pygame.Surface) -> None:
        """Draw the input field."""
        # Draw label above field
        if self.label:
            label_surf = self.font.render(self.label, True, self.color_label)
            screen.blit(label_surf, (self.rect.x, self.rect.y - 28))
        
        # Draw background
        pygame.draw.rect(screen, self.color_bg, self.rect, border_radius=6)
        
        # Draw border
        border_color = self.color_active if self.active else self.color_inactive
        pygame.draw.rect(screen, border_color, self.rect, width=2, border_radius=6)
        
        # Determine display text
        if self.text:
            # Show password if toggle is on, otherwise show asterisks for password fields
            if self.is_password and not self.show_password:
                display_text = "*" * len(self.text)
            else:
                display_text = self.text
            text_color = self.color_text
        else:
            display_text = self.placeholder
            text_color = self.color_placeholder
        
        # Render text
        text_surf = self.font.render(display_text, True, text_color)
        text_x = self.rect.x + 12
        text_y = self.rect.y + (self.rect.height - text_surf.get_height()) // 2
        
        # Clip text to fit in field (leave space for show password button)
        clip_width = self.rect.width - 20
        if self.is_password and self.show_password_rect:
            clip_width = self.rect.width - self.show_password_rect.width - 24
        clip_rect = pygame.Rect(self.rect.x + 10, self.rect.y, clip_width, self.rect.height)
        screen.set_clip(clip_rect)
        screen.blit(text_surf, (text_x, text_y))
        screen.set_clip(None)
        
        # Draw cursor
        if self.active and self.cursor_visible and self.text:
            cursor_x = min(text_x + text_surf.get_width() + 2, self.rect.x + clip_width)
            cursor_y1 = self.rect.y + 8
            cursor_y2 = self.rect.y + self.rect.height - 8
            pygame.draw.line(screen, self.color_text, (cursor_x, cursor_y1), (cursor_x, cursor_y2), 2)
        elif self.active and self.cursor_visible and not self.text:
            cursor_x = text_x
            cursor_y1 = self.rect.y + 8
            cursor_y2 = self.rect.y + self.rect.height - 8
            pygame.draw.line(screen, self.color_text, (cursor_x, cursor_y1), (cursor_x, cursor_y2), 2)
        
        # Draw show password button for password fields
        if self.is_password and self.show_password_rect:
            mouse_pos = pygame.mouse.get_pos()
            hovered = self.show_password_rect.collidepoint(*mouse_pos)
            
            # Button background
            btn_color = (60, 70, 100) if hovered else (45, 50, 75)
            pygame.draw.rect(screen, btn_color, self.show_password_rect, border_radius=4)
            
            # Draw eye icon (simple representation)
            eye_cx = self.show_password_rect.centerx
            eye_cy = self.show_password_rect.centery
            eye_color = (200, 210, 240) if hovered else (150, 160, 190)
            
            # Eye shape - outer ellipse
            pygame.draw.ellipse(screen, eye_color, 
                               (eye_cx - 10, eye_cy - 5, 20, 10), 2)
            # Pupil
            pygame.draw.circle(screen, eye_color, (eye_cx, eye_cy), 3)
            
            # If password is hidden, draw a line through the eye
            if not self.show_password:
                pygame.draw.line(screen, eye_color, 
                               (eye_cx - 8, eye_cy + 6), 
                               (eye_cx + 8, eye_cy - 6), 2)
    
    def clear(self) -> None:
        """Clear the input field."""
        self.text = ""


class LoginRegisterMenu:
    """Login and registration menu for the arcade game."""
    
    def __init__(
        self,
        screen: pygame.Surface,
        cfg: "Settings",
        font: pygame.font.Font,
        db: "DatabaseManager"
    ):
        self.screen = screen
        self.cfg = cfg
        self.font = font
        self.db = db
        
        # Session
        self.session = UserSession()
        
        # Mode: "login" or "register"
        self.mode = "login"
        
        # Message display
        self.message = ""
        self.message_color = (255, 255, 255)
        self.message_timer = 0
        
        # Processing state
        self.processing = False
        
        # Click cooldown to prevent rapid clicking
        self.click_cooldown = 0.0
        self.click_cooldown_duration = 1  # 1s cooldown
        
        # Input fields - will be built on first draw
        self.fields_built = False
        self.username_field: Optional[TextInputField] = None
        self.email_field: Optional[TextInputField] = None
        self.password_field: Optional[TextInputField] = None
        self.confirm_password_field: Optional[TextInputField] = None
        
        # Buttons
        self.submit_button_rect: Optional[pygame.Rect] = None
        self.toggle_mode_rect: Optional[pygame.Rect] = None
        self.guest_button_rect: Optional[pygame.Rect] = None
    
    def build_fields(self) -> None:
        """Build input fields based on current screen size."""
        field_width = 360
        field_height = 44
        center_x = self.cfg.width // 2 - field_width // 2
        
        if self.mode == "register":
            # Registration: username, email, password, confirm password
            start_y = self.cfg.height // 2 - 140
            spacing = 80
            
            self.username_field = TextInputField(
                center_x, start_y, field_width, field_height,
                self.font, label="Username", placeholder="Enter username"
            )
            self.email_field = TextInputField(
                center_x, start_y + spacing, field_width, field_height,
                self.font, label="Email", placeholder="Enter email"
            )
            self.password_field = TextInputField(
                center_x, start_y + spacing * 2, field_width, field_height,
                self.font, label="Password", placeholder="Enter password", is_password=True
            )
            self.confirm_password_field = TextInputField(
                center_x, start_y + spacing * 3, field_width, field_height,
                self.font, label="Confirm Password", placeholder="Confirm password", is_password=True
            )
        else:
            # Login: username/email, password
            start_y = self.cfg.height // 2 - 80
            spacing = 80
            
            self.username_field = TextInputField(
                center_x, start_y, field_width, field_height,
                self.font, label="Username or Email", placeholder="Enter username or email"
            )
            self.email_field = None
            self.password_field = TextInputField(
                center_x, start_y + spacing, field_width, field_height,
                self.font, label="Password", placeholder="Enter password", is_password=True
            )
            self.confirm_password_field = None
        
        # Build buttons
        button_width = 360
        button_height = 48
        button_x = self.cfg.width // 2 - button_width // 2
        
        if self.mode == "register":
            button_y = self.cfg.height // 2 + 200
        else:
            button_y = self.cfg.height // 2 + 100
        
        self.submit_button_rect = pygame.Rect(button_x, button_y, button_width, button_height)
        self.toggle_mode_rect = pygame.Rect(button_x, button_y + 60, button_width, button_height)
        self.guest_button_rect = pygame.Rect(button_x, button_y + 120, button_width, button_height)
        
        self.fields_built = True
    
    def get_all_fields(self) -> list[TextInputField]:
        """Get list of all active input fields."""
        fields = []
        if self.username_field:
            fields.append(self.username_field)
        if self.email_field:
            fields.append(self.email_field)
        if self.password_field:
            fields.append(self.password_field)
        if self.confirm_password_field:
            fields.append(self.confirm_password_field)
        return fields
    
    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """
        Handle input events.
        Returns "logged_in" if login successful, "guest" for guest mode, None otherwise.
        """
        if self.processing:
            return None
        
        if not self.fields_built:
            self.build_fields()
        
        # Handle tab to cycle through fields
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            fields = self.get_all_fields()
            active_idx = -1
            for i, field in enumerate(fields):
                if field.active:
                    active_idx = i
                    field.active = False
                    break
            
            # Move to next field
            next_idx = (active_idx + 1) % len(fields)
            fields[next_idx].active = True
            return None
        
        # Handle enter to submit
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
            return self.submit()
        
        # Handle field events
        for field in self.get_all_fields():
            field.handle_event(event)
        
        # Handle button clicks
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check cooldown to prevent rapid clicking
            if self.click_cooldown > 0:
                return None
            
            mx, my = event.pos
            
            if self.submit_button_rect and self.submit_button_rect.collidepoint(mx, my):
                self.click_cooldown = self.click_cooldown_duration
                return self.submit()
            
            if self.toggle_mode_rect and self.toggle_mode_rect.collidepoint(mx, my):
                self.click_cooldown = self.click_cooldown_duration
                self.toggle_mode()
                return None
            
            if self.guest_button_rect and self.guest_button_rect.collidepoint(mx, my):
                self.click_cooldown = self.click_cooldown_duration
                self.session.username = "Guest"
                self.session.is_logged_in = False
                return "guest"
        
        return None
    
    def toggle_mode(self) -> None:
        """Toggle between login and register mode."""
        self.mode = "register" if self.mode == "login" else "login"
        self.fields_built = False
        self.message = ""
        self.build_fields()
    
    def submit(self) -> Optional[str]:
        """Submit the form. Returns "logged_in" on success."""
        if self.processing:
            return None
        
        if self.mode == "register":
            return self.do_register()
        else:
            return self.do_login()
    
    def do_register(self) -> Optional[str]:
        """Handle registration."""
        username = self.username_field.text.strip() if self.username_field else ""
        email = self.email_field.text.strip() if self.email_field else ""
        password = self.password_field.text if self.password_field else ""
        confirm = self.confirm_password_field.text if self.confirm_password_field else ""
        
        # Validation
        if not username:
            self.show_message("Username is required", error=True)
            return None
        
        if len(username) < 3:
            self.show_message("Username must be at least 3 characters", error=True)
            return None
        
        if not email:
            self.show_message("Email is required", error=True)
            return None
        
        # Simple email validation
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            self.show_message("Invalid email format", error=True)
            return None
        
        if not password:
            self.show_message("Password is required", error=True)
            return None
        
        if len(password) < 4:
            self.show_message("Password must be at least 4 characters", error=True)
            return None
        
        if password != confirm:
            self.show_message("Passwords do not match", error=True)
            return None
        
        # Try to register
        self.processing = True
        try:
            user_id = asyncio.run(register_user_async(self.db, username, email, password))
            if user_id:
                self.show_message("Registration successful! Please login.", error=False)
                # Switch to login mode
                self.mode = "login"
                self.fields_built = False
                self.build_fields()
                # Pre-fill username
                if self.username_field:
                    self.username_field.text = username
            else:
                self.show_message("Username or email already exists", error=True)
        except Exception as e:
            self.show_message(f"Registration failed: {str(e)[:30]}", error=True)
        finally:
            self.processing = False
        
        return None
    
    def do_login(self) -> Optional[str]:
        """Handle login."""
        identifier = self.username_field.text.strip() if self.username_field else ""
        password = self.password_field.text if self.password_field else ""
        
        # Validation
        if not identifier:
            self.show_message("Username or email is required", error=True)
            return None
        
        if not password:
            self.show_message("Password is required", error=True)
            return None
        
        # Try to login
        self.processing = True
        try:
            user = asyncio.run(login_user_async(self.db, identifier, password))
            if user:
                self.session.login(user)
                self.show_message(f"Welcome back, {self.session.username}!", error=False)
                return "logged_in"
            else:
                self.show_message("Invalid username/email or password", error=True)
        except Exception as e:
            self.show_message(f"Login failed: {str(e)[:30]}", error=True)
        finally:
            self.processing = False
        
        return None
    
    def show_message(self, msg: str, error: bool = False) -> None:
        """Show a message to the user."""
        self.message = msg
        self.message_color = (255, 100, 100) if error else (100, 255, 150)
        self.message_timer = 4.0
    
    def update(self, dt: float) -> None:
        """Update menu state."""
        # Update message timer
        if self.message_timer > 0:
            self.message_timer -= dt
            if self.message_timer <= 0:
                self.message = ""
        
        # Update click cooldown
        if self.click_cooldown > 0:
            self.click_cooldown -= dt
        
        # Update field cursors
        for field in self.get_all_fields():
            field.update(dt)
    
    def draw(self) -> None:
        """Draw the login/register menu."""
        if not self.fields_built:
            self.build_fields()
        
        # Background
        self.screen.fill((20, 25, 45))
        
        # Title
        title_text = "Create Account" if self.mode == "register" else "Login"
        title_surf = self.font.render(title_text, True, (255, 255, 255))
        title_x = self.cfg.width // 2 - title_surf.get_width() // 2
        title_y = 60 if self.mode == "register" else 100
        self.screen.blit(title_surf, (title_x, title_y))
        
        # Subtitle
        if self.mode == "login":
            subtitle = "Enter your username or email to login"
        else:
            subtitle = "Fill in the details to create an account"
        subtitle_surf = self.font.render(subtitle, True, (150, 160, 190))
        sub_x = self.cfg.width // 2 - subtitle_surf.get_width() // 2
        sub_y = title_y + 45
        self.screen.blit(subtitle_surf, (sub_x, sub_y))
        
        # Draw input fields
        for field in self.get_all_fields():
            field.draw(self.screen)
        
        # Draw buttons
        mouse_pos = pygame.mouse.get_pos()
        
        # Submit button
        if self.submit_button_rect:
            self.draw_button(
                self.submit_button_rect,
                "Register" if self.mode == "register" else "Login",
                mouse_pos,
                primary=True
            )
        
        # Toggle mode button
        if self.toggle_mode_rect:
            toggle_text = "Already have an account? Login" if self.mode == "register" else "Don't have an account? Register"
            self.draw_button(self.toggle_mode_rect, toggle_text, mouse_pos, primary=False)
        
        # Guest button
        if self.guest_button_rect:
            self.draw_button(self.guest_button_rect, "Continue as Guest", mouse_pos, primary=False)
        
        # Draw message
        if self.message:
            msg_surf = self.font.render(self.message, True, self.message_color)
            msg_x = self.cfg.width // 2 - msg_surf.get_width() // 2
            msg_y = self.cfg.height - 80
            self.screen.blit(msg_surf, (msg_x, msg_y))
        
        # Processing indicator
        if self.processing:
            proc_surf = self.font.render("Processing...", True, (200, 200, 100))
            proc_x = self.cfg.width // 2 - proc_surf.get_width() // 2
            proc_y = self.cfg.height - 40
            self.screen.blit(proc_surf, (proc_x, proc_y))
    
    def draw_button(
        self,
        rect: pygame.Rect,
        text: str,
        mouse_pos: tuple[int, int],
        primary: bool = True
    ) -> None:
        """Draw a button."""
        hovered = rect.collidepoint(*mouse_pos)
        
        if primary:
            fill = (80, 100, 180) if hovered else (60, 80, 150)
            border = (150, 170, 255) if hovered else (100, 120, 200)
        else:
            fill = (50, 55, 80) if hovered else (40, 45, 70)
            border = (120, 130, 160) if hovered else (90, 100, 130)
        
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, border, rect, width=2, border_radius=8)
        
        text_surf = self.font.render(text, True, (255, 255, 255))
        text_x = rect.x + (rect.width - text_surf.get_width()) // 2
        text_y = rect.y + (rect.height - text_surf.get_height()) // 2
        self.screen.blit(text_surf, (text_x, text_y))
    
    def reset(self) -> None:
        """Reset the menu to initial state."""
        self.mode = "login"
        self.fields_built = False
        self.message = ""
        self.processing = False
        self.click_cooldown = 0.0
        self.session.logout()
