from __future__ import annotations
from pathlib import Path
from typing import Dict
import pygame
from settings import SOUND_DIR

class SoundManager:
    def __init__(self):
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.music_loaded = False

    def load_sound(self, key: str, filename: str) -> None:
        path = SOUND_DIR / filename
        if not path.exists():
            return
        self.sounds[key] = pygame.mixer.Sound(path.as_posix())

    def play(self, key: str) -> None:
        sound = self.sounds.get(key)
        if sound:
            sound.play()

    def load_music(self, filename: str) -> None:
        path = SOUND_DIR / filename
        if not path.exists():
            return
        pygame.mixer.music.load(path.as_posix())
        self.music_loaded = True

    def play_music(self, loops: int = -1) -> None:
        if self.music_loaded:
            pygame.mixer.music.play(loops=loops)

    def stop_music(self) -> None:
        pygame.mixer.music.stop()
