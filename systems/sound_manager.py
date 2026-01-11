from __future__ import annotations
from pathlib import Path
from typing import Dict
import pygame
from settings import SOUND_DIR

class SoundManager:
    """
    Centralized sound manager for all game audio.
    
    Sound assets organized by game:
    - Tetris: line_clear, game_over
    - Snake: eat, crash
    - Pac-Man: chomp, siren, eat_ghost
    - Space Invaders: shoot, explosion
    - General: power_up, menu_select
    """
    
    # Default sound file mappings (key -> filename)
    DEFAULT_SOUNDS = {
        # Tetris sounds
        "line_clear": "line_clear.wav",
        "game_over": "game_over.wav",
        # Snake sounds
        "eat": "eat.mp3",
        "crash": "crash.wav",
        # Pac-Man sounds
        "chomp": "chomp.wav",
        "siren": "siren.wav",
        "eat_ghost": "eat_ghost.wav",
        # Space Invaders sounds
        "shoot": "shoot.wav",
        "explosion": "explosion.wav",
        # General sounds
        "power_up": "power_up.wav",
        "menu_select": "menu_select.wav",
    }

    def __init__(self):
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.music_loaded = False
        self._volume: float = 0.7  # Default volume (0.0 to 1.0)
        self._music_volume: float = 0.5  # Separate music volume
        self._muted: bool = False
        
        # Initialize mixer if not already done
        if not pygame.mixer.get_init():
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)

    def load_assets(self) -> None:
        """
        Load all default sound assets.
        Uses try/except to prevent crashes if files are missing.
        """
        for key, filename in self.DEFAULT_SOUNDS.items():
            self.load_sound(key, filename)

    def load_sound(self, key: str, filename: str) -> None:
        """Load a single sound file with error handling."""
        path = SOUND_DIR / filename
        try:
            if not path.exists():
                print(f"[SoundManager] Warning: Sound file not found: {filename}")
                return
            sound = pygame.mixer.Sound(path.as_posix())
            sound.set_volume(self._volume)
            self.sounds[key] = sound
        except pygame.error as e:
            print(f"[SoundManager] Error loading {filename}: {e}")
        except Exception as e:
            print(f"[SoundManager] Unexpected error loading {filename}: {e}")

    def play(self, key: str) -> None:
        """Play a sound effect by key name."""
        if self._muted:
            return
        sound = self.sounds.get(key)
        if sound:
            sound.play()

    def stop(self, key: str) -> None:
        """Stop a specific sound."""
        sound = self.sounds.get(key)
        if sound:
            sound.stop()

    def stop_all(self) -> None:
        """Stop all sound effects."""
        for sound in self.sounds.values():
            sound.stop()

    def load_music(self, filename: str) -> None:
        """Load background music with error handling."""
        path = SOUND_DIR / filename
        try:
            if not path.exists():
                print(f"[SoundManager] Warning: Music file not found: {filename}")
                return
            pygame.mixer.music.load(path.as_posix())
            pygame.mixer.music.set_volume(self._music_volume)
            self.music_loaded = True
        except pygame.error as e:
            print(f"[SoundManager] Error loading music {filename}: {e}")
        except Exception as e:
            print(f"[SoundManager] Unexpected error loading music {filename}: {e}")

    def play_music(self, loops: int = -1) -> None:
        """Play background music (loops=-1 for infinite loop)."""
        if self.music_loaded and not self._muted:
            pygame.mixer.music.play(loops=loops)

    def stop_music(self) -> None:
        """Stop background music."""
        pygame.mixer.music.stop()

    def pause_music(self) -> None:
        """Pause background music."""
        pygame.mixer.music.pause()

    def unpause_music(self) -> None:
        """Resume paused background music."""
        if not self._muted:
            pygame.mixer.music.unpause()

    @property
    def volume(self) -> float:
        """Get current sound effect volume (0.0 to 1.0)."""
        return self._volume

    def set_volume(self, val: float) -> None:
        """
        Set volume for all sound effects.
        
        Args:
            val: Volume level from 0.0 (silent) to 1.0 (max)
        """
        self._volume = max(0.0, min(1.0, val))
        for sound in self.sounds.values():
            sound.set_volume(self._volume)

    @property
    def music_volume(self) -> float:
        """Get current music volume (0.0 to 1.0)."""
        return self._music_volume

    def set_music_volume(self, val: float) -> None:
        """
        Set volume for background music.
        
        Args:
            val: Volume level from 0.0 (silent) to 1.0 (max)
        """
        self._music_volume = max(0.0, min(1.0, val))
        pygame.mixer.music.set_volume(self._music_volume)

    @property
    def muted(self) -> bool:
        """Check if audio is muted."""
        return self._muted

    def toggle_mute(self) -> bool:
        """Toggle mute state. Returns new muted state."""
        self._muted = not self._muted
        if self._muted:
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()
        return self._muted

    def set_muted(self, muted: bool) -> None:
        """Set mute state directly."""
        self._muted = muted
        if self._muted:
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()
