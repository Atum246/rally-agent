"""
🟣 Rally Agent — Real Computer Use Engine
Desktop control: screen capture, mouse/keyboard automation, GUI element detection,
OCR, window management, clipboard, workflow recording/replay.
Cross-platform: Linux (xdotool + pyautogui), macOS (pyautogui + AppleScript), Windows (pyautogui).
Graceful fallback when display unavailable (headless mode).
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from tools.registry import (
    BaseTool,
    ToolCategory,
    ToolDefinition,
    ToolParameter,
    PermissionLevel,
    ToolRegistry,
)


# ═══════════════════════════════════════════════════════════════
# Optional Dependencies — Graceful Fallbacks
# ═══════════════════════════════════════════════════════════════

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.05
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False


# ═══════════════════════════════════════════════════════════════
# Platform Detection
# ═══════════════════════════════════════════════════════════════

PLATFORM = platform.system().lower()  # "linux", "darwin", "windows"
IS_HEADLESS = not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY") and PLATFORM != "windows"


class MouseButton(str, Enum):
    LEFT = "left"
    RIGHT = "right"
    MIDDLE = "middle"


class ScrollDirection(str, Enum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


@dataclass
class ScreenRegion:
    """Defines a rectangular region on screen."""
    x: int
    y: int
    width: int
    height: int

    def to_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px <= self.x + self.width and self.y <= py <= self.y + self.height


@dataclass
class UIElement:
    """Detected UI element on screen."""
    text: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 1.0
    element_type: str = "unknown"

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "confidence": self.confidence,
            "type": self.element_type,
            "center": self.center,
        }


@dataclass
class RecordedAction:
    """A single recorded user action."""
    action_type: str  # "click", "doubleclick", "rightclick", "type", "key", "scroll", "drag", "wait"
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.action_type, "timestamp": self.timestamp, **self.data}


@dataclass
class WindowInfo:
    """Information about a window."""
    window_id: str
    title: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    pid: int = 0
    is_active: bool = False
    is_minimized: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.window_id,
            "title": self.title,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "pid": self.pid,
            "active": self.is_active,
            "minimized": self.is_minimized,
        }


@dataclass
class MonitorInfo:
    """Information about a display monitor."""
    index: int
    x: int
    y: int
    width: int
    height: int
    is_primary: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "x": self.x, "y": self.y,
            "width": self.width, "height": self.height,
            "primary": self.is_primary,
        }


# ═══════════════════════════════════════════════════════════════
# Platform-Specific Backends
# ═══════════════════════════════════════════════════════════════

class _LinuxBackend:
    """Linux-specific operations via xdotool, xclip, xdg-open."""

    @staticmethod
    def _run(cmd: list[str], timeout: int = 10) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)

    @staticmethod
    def has_display() -> bool:
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        try:
            r = subprocess.run(["xdotool", "getdisplaygeometry"], capture_output=True, text=True, timeout=5)
            w, h = r.stdout.strip().split()
            return int(w), int(h)
        except Exception:
            return (1920, 1080)

    @staticmethod
    def get_mouse_position() -> tuple[int, int]:
        try:
            r = subprocess.run(["xdotool", "getmouselocation"], capture_output=True, text=True, timeout=5)
            parts = r.stdout.split()
            x = int(parts[0].split(":")[1])
            y = int(parts[1].split(":")[1])
            return x, y
        except Exception:
            return (0, 0)

    @staticmethod
    def move_mouse(x: int, y: int, duration: float = 0.1):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(x, y, duration=duration)
        else:
            subprocess.run(["xdotool", "mousemove", str(x), str(y)], timeout=5)

    @staticmethod
    def click(x: int, y: int, button: MouseButton = MouseButton.LEFT, clicks: int = 1):
        btn_map = {MouseButton.LEFT: "1", MouseButton.RIGHT: "3", MouseButton.MIDDLE: "2"}
        if HAS_PYAUTOGUI:
            pyautogui.click(x, y, clicks=clicks, button=button.value)
        else:
            subprocess.run(["xdotool", "mousemove", str(x), str(y)], timeout=5)
            for _ in range(clicks):
                subprocess.run(["xdotool", "click", btn_map[button]], timeout=5)

    @staticmethod
    def double_click(x: int, y: int):
        _LinuxBackend.click(x, y, clicks=2)

    @staticmethod
    def right_click(x: int, y: int):
        _LinuxBackend.click(x, y, button=MouseButton.RIGHT)

    @staticmethod
    def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)
        else:
            subprocess.run(["xdotool", "mousemove", str(start_x), str(start_y)], timeout=5)
            subprocess.run(["xdotool", "mousedown", "1"], timeout=5)
            subprocess.run(["xdotool", "mousemove", str(end_x), str(end_y)], timeout=5)
            subprocess.run(["xdotool", "mouseup", "1"], timeout=5)

    @staticmethod
    def scroll(direction: ScrollDirection, amount: int = 3):
        if direction in (ScrollDirection.UP, ScrollDirection.DOWN):
            btn = "4" if direction == ScrollDirection.UP else "5"
            for _ in range(amount):
                subprocess.run(["xdotool", "click", btn], timeout=5)
        else:
            btn = "6" if direction == ScrollDirection.LEFT else "7"
            for _ in range(amount):
                subprocess.run(["xdotool", "click", btn], timeout=5)

    @staticmethod
    def type_text(text: str, interval: float = 0.02):
        if HAS_PYAUTOGUI:
            pyautogui.typewrite(text, interval=interval) if text.isascii() else pyautogui.write(text)
        else:
            # xdotool has issues with unicode; use xdotool type for ASCII
            subprocess.run(["xdotool", "type", "--clearmodifiers", text], timeout=10)

    @staticmethod
    def press_key(key: str):
        key_map = {
            "enter": "Return", "return": "Return", "tab": "Tab", "space": "space",
            "backspace": "BackSpace", "delete": "Delete", "escape": "Escape", "esc": "Escape",
            "up": "Up", "down": "Down", "left": "Left", "right": "Right",
            "home": "Home", "end": "End", "pageup": "Page_Up", "pagedown": "Page_Down",
            "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6",
            "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
            "ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "super", "win": "super",
            "capslock": "Caps_Lock", "numlock": "Num_Lock", "printscreen": "Print",
        }
        xk = key_map.get(key.lower(), key)
        subprocess.run(["xdotool", "key", xk], timeout=5)

    @staticmethod
    def hotkey(*keys: str):
        key_map = {
            "ctrl": "ctrl", "alt": "alt", "shift": "shift", "super": "super", "win": "super",
            "enter": "Return", "tab": "Tab", "space": "space", "escape": "Escape",
        }
        mapped = [key_map.get(k.lower(), k) for k in keys]
        combo = "+".join(mapped)
        subprocess.run(["xdotool", "key", combo], timeout=5)

    @staticmethod
    def get_clipboard() -> str:
        try:
            r = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5)
            return r.stdout
        except FileNotFoundError:
            try:
                r = subprocess.run(["xsel", "--clipboard", "--output"], capture_output=True, text=True, timeout=5)
                return r.stdout
            except FileNotFoundError:
                return ""

    @staticmethod
    def set_clipboard(text: str):
        try:
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text, text=True, timeout=5,
            )
        except FileNotFoundError:
            subprocess.run(
                ["xsel", "--clipboard", "--input"],
                input=text, text=True, timeout=5,
            )

    @staticmethod
    def list_windows() -> list[WindowInfo]:
        windows = []
        try:
            r = subprocess.run(
                ["xdotool", "search", "--onlyvisible", "--name", ""],
                capture_output=True, text=True, timeout=10,
            )
            for wid in r.stdout.strip().split("\n"):
                if not wid.strip():
                    continue
                try:
                    name_r = subprocess.run(
                        ["xdotool", "getwindowname", wid],
                        capture_output=True, text=True, timeout=5,
                    )
                    geo_r = subprocess.run(
                        ["xdotool", "getwindowgeometry", "--shell", wid],
                        capture_output=True, text=True, timeout=5,
                    )
                    title = name_r.stdout.strip()
                    x, y, w, h = 0, 0, 0, 0
                    for line in geo_r.stdout.strip().split("\n"):
                        if line.startswith("X="):
                            x = int(line.split("=")[1])
                        elif line.startswith("Y="):
                            y = int(line.split("=")[1])
                        elif line.startswith("WIDTH="):
                            w = int(line.split("=")[1])
                        elif line.startswith("HEIGHT="):
                            h = int(line.split("=")[1])
                    windows.append(WindowInfo(window_id=wid, title=title, x=x, y=y, width=w, height=h))
                except Exception:
                    continue
        except Exception:
            pass
        return windows

    @staticmethod
    def focus_window(window_id: str):
        subprocess.run(["xdotool", "windowactivate", "--sync", window_id], timeout=5)

    @staticmethod
    def resize_window(window_id: str, width: int, height: int):
        subprocess.run(["xdotool", "windowsize", "--sync", window_id, str(width), str(height)], timeout=5)

    @staticmethod
    def move_window(window_id: str, x: int, y: int):
        subprocess.run(["xdotool", "windowmove", "--sync", window_id, str(x), str(y)], timeout=5)

    @staticmethod
    def minimize_window(window_id: str):
        subprocess.run(["xdotool", "windowminimize", "--sync", window_id], timeout=5)

    @staticmethod
    def maximize_window(window_id: str):
        # Use wmctrl for maximize
        subprocess.run(["wmctrl", "-i", "-r", window_id, "-b", "add,maximized_vert,maximized_horz"], timeout=5)

    @staticmethod
    def get_monitors() -> list[MonitorInfo]:
        monitors = []
        try:
            r = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=5)
            idx = 0
            for line in r.stdout.split("\n"):
                if " connected " in line:
                    parts = line.split()
                    name = parts[0]
                    is_primary = "primary" in line
                    # Parse geometry like "1920x1080+0+0"
                    for part in parts:
                        if "x" in part and "+" in part:
                            geo = part.replace("primary", "").strip()
                            dims, offsets = geo.split("+")[0], geo.split("+")[1:]
                            w, h = map(int, dims.split("x"))
                            ox, oy = int(offsets[0]), int(offsets[1])
                            monitors.append(MonitorInfo(index=idx, x=ox, y=oy, width=w, height=h, is_primary=is_primary))
                            idx += 1
                            break
        except Exception:
            monitors.append(MonitorInfo(index=0, x=0, y=0, width=1920, height=1080, is_primary=True))
        return monitors

    @staticmethod
    def screenshot(region: Optional[ScreenRegion] = None) -> Optional[bytes]:
        """Capture screenshot. Returns PNG bytes."""
        if HAS_PIL and HAS_PYAUTOGUI:
            img = pyautogui.screenshot(region=region.to_tuple() if region else None)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        # Fallback: use scrot or import
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        try:
            if region:
                # scrot doesn't support region well; use import from ImageMagick
                subprocess.run(
                    ["import", "-window", "root", "-crop", f"{region.width}x{region.height}+{region.x}+{region.y}", tmp],
                    timeout=10,
                )
            else:
                subprocess.run(["scrot", tmp], timeout=10)
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp)

    @staticmethod
    def ocr_image(image_bytes: bytes, lang: str = "eng") -> str:
        if HAS_PIL and HAS_TESSERACT:
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, lang=lang)
        return ""

    @staticmethod
    def find_text_on_screen(image_bytes: bytes, search_text: str, lang: str = "eng") -> list[UIElement]:
        """OCR the screenshot and find text matches with bounding boxes."""
        if not (HAS_PIL and HAS_TESSERACT):
            return []
        img = Image.open(io.BytesIO(image_bytes))
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        except Exception:
            return []

        results = []
        n = len(data["text"])
        for i in range(n):
            word = data["text"][i].strip()
            if not word:
                continue
            if search_text.lower() in word.lower():
                results.append(UIElement(
                    text=word,
                    x=data["left"][i],
                    y=data["top"][i],
                    width=data["width"][i],
                    height=data["height"][i],
                    confidence=data["conf"][i] / 100.0 if data["conf"][i] != -1 else 0.0,
                    element_type="text",
                ))
        return results


class _DarwinBackend:
    """macOS-specific operations via pyautogui + AppleScript."""

    @staticmethod
    def has_display() -> bool:
        return True  # macOS always has a display

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        if HAS_PYAUTOGUI:
            return pyautogui.size()
        return (1920, 1080)

    @staticmethod
    def get_mouse_position() -> tuple[int, int]:
        if HAS_PYAUTOGUI:
            return pyautogui.position()
        return (0, 0)

    @staticmethod
    def move_mouse(x: int, y: int, duration: float = 0.1):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(x, y, duration=duration)

    @staticmethod
    def click(x: int, y: int, button: MouseButton = MouseButton.LEFT, clicks: int = 1):
        if HAS_PYAUTOGUI:
            pyautogui.click(x, y, clicks=clicks, button=button.value)

    @staticmethod
    def double_click(x: int, y: int):
        _DarwinBackend.click(x, y, clicks=2)

    @staticmethod
    def right_click(x: int, y: int):
        _DarwinBackend.click(x, y, button=MouseButton.RIGHT)

    @staticmethod
    def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)

    @staticmethod
    def scroll(direction: ScrollDirection, amount: int = 3):
        if HAS_PYAUTOGUI:
            if direction == ScrollDirection.UP:
                pyautogui.scroll(amount)
            elif direction == ScrollDirection.DOWN:
                pyautogui.scroll(-amount)
            elif direction == ScrollDirection.LEFT:
                pyautogui.hscroll(amount)
            elif direction == ScrollDirection.RIGHT:
                pyautogui.hscroll(-amount)

    @staticmethod
    def type_text(text: str, interval: float = 0.02):
        if HAS_PYAUTOGUI:
            pyautogui.write(text, interval=interval) if text.isascii() else _DarwinBackend._applescript_type(text)

    @staticmethod
    def _applescript_type(text: str):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        script = f'tell application "System Events" to keystroke "{escaped}"'
        subprocess.run(["osascript", "-e", script], timeout=10)

    @staticmethod
    def press_key(key: str):
        if HAS_PYAUTOGUI:
            pyautogui.press(key)

    @staticmethod
    def hotkey(*keys: str):
        if HAS_PYAUTOGUI:
            pyautogui.hotkey(*keys)

    @staticmethod
    def get_clipboard() -> str:
        try:
            r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
            return r.stdout
        except Exception:
            return ""

    @staticmethod
    def set_clipboard(text: str):
        subprocess.run(["pbcopy"], input=text, text=True, timeout=5)

    @staticmethod
    def _run_applescript(script: str) -> str:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
        return r.stdout.strip()

    @staticmethod
    def list_windows() -> list[WindowInfo]:
        windows = []
        try:
            script = '''
            tell application "System Events"
                set windowList to {}
                repeat with proc in (every process whose visible is true)
                    set procName to name of proc
                    repeat with win in (every window of proc)
                        set end of windowList to procName & "|||" & (name of win) & "|||" & (position of win as string) & "|||" & (size of win as string)
                    end repeat
                end repeat
                set AppleScript's text item delimiters to ";;;"
                return windowList as string
            end tell
            '''
            result = _DarwinBackend._run_applescript(script)
            for entry in result.split(";;;"):
                parts = entry.split("|||")
                if len(parts) >= 4:
                    title = parts[1] if len(parts) > 1 else ""
                    pos = parts[2].split(",") if len(parts) > 2 else ["0", "0"]
                    size = parts[3].split(",") if len(parts) > 3 else ["0", "0"]
                    windows.append(WindowInfo(
                        window_id=parts[0],
                        title=title,
                        x=int(pos[0].strip()), y=int(pos[1].strip()),
                        width=int(size[0].strip()), height=int(size[1].strip()),
                    ))
        except Exception:
            pass
        return windows

    @staticmethod
    def focus_window(window_id: str):
        try:
            subprocess.run(["osascript", "-e", f'tell application "{window_id}" to activate'], timeout=5)
        except Exception:
            pass

    @staticmethod
    def resize_window(window_id: str, width: int, height: int):
        try:
            script = f'''
            tell application "System Events"
                tell process "{window_id}"
                    set size of front window to {{{width}, {height}}}
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def move_window(window_id: str, x: int, y: int):
        try:
            script = f'''
            tell application "System Events"
                tell process "{window_id}"
                    set position of front window to {{{x}, {y}}}
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def minimize_window(window_id: str):
        try:
            script = f'''
            tell application "System Events"
                tell process "{window_id}"
                    set miniaturized of front window to true
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def maximize_window(window_id: str):
        try:
            script = f'''
            tell application "System Events"
                tell process "{window_id}"
                    set position of front window to {{0, 0}}
                    set size of front window to {{1920, 1080}}
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def get_monitors() -> list[MonitorInfo]:
        try:
            script = '''
            tell application "Finder"
                set bounds of window of desktop to {0, 0, 1920, 1080}
            end tell
            '''
            # macOS doesn't expose multi-monitor easily via AppleScript
            # Default to primary
            return [MonitorInfo(index=0, x=0, y=0, width=1920, height=1080, is_primary=True)]
        except Exception:
            return [MonitorInfo(index=0, x=0, y=0, width=1920, height=1080, is_primary=True)]

    @staticmethod
    def screenshot(region: Optional[ScreenRegion] = None) -> Optional[bytes]:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        try:
            cmd = ["screencapture", "-x"]
            if region:
                cmd.extend(["-R", f"{region.x},{region.y},{region.width},{region.height}"])
            cmd.append(tmp)
            subprocess.run(cmd, timeout=10)
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp)

    @staticmethod
    def ocr_image(image_bytes: bytes, lang: str = "eng") -> str:
        if HAS_PIL and HAS_TESSERACT:
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, lang=lang)
        return ""

    @staticmethod
    def find_text_on_screen(image_bytes: bytes, search_text: str, lang: str = "eng") -> list[UIElement]:
        if not (HAS_PIL and HAS_TESSERACT):
            return []
        img = Image.open(io.BytesIO(image_bytes))
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        except Exception:
            return []
        results = []
        n = len(data["text"])
        for i in range(n):
            word = data["text"][i].strip()
            if not word:
                continue
            if search_text.lower() in word.lower():
                results.append(UIElement(
                    text=word,
                    x=data["left"][i], y=data["top"][i],
                    width=data["width"][i], height=data["height"][i],
                    confidence=data["conf"][i] / 100.0 if data["conf"][i] != -1 else 0.0,
                    element_type="text",
                ))
        return results


class _WindowsBackend:
    """Windows-specific operations via pyautogui + PowerShell."""

    @staticmethod
    def has_display() -> bool:
        return True

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        if HAS_PYAUTOGUI:
            return pyautogui.size()
        return (1920, 1080)

    @staticmethod
    def get_mouse_position() -> tuple[int, int]:
        if HAS_PYAUTOGUI:
            return pyautogui.position()
        return (0, 0)

    @staticmethod
    def move_mouse(x: int, y: int, duration: float = 0.1):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(x, y, duration=duration)

    @staticmethod
    def click(x: int, y: int, button: MouseButton = MouseButton.LEFT, clicks: int = 1):
        if HAS_PYAUTOGUI:
            pyautogui.click(x, y, clicks=clicks, button=button.value)

    @staticmethod
    def double_click(x: int, y: int):
        _WindowsBackend.click(x, y, clicks=2)

    @staticmethod
    def right_click(x: int, y: int):
        _WindowsBackend.click(x, y, button=MouseButton.RIGHT)

    @staticmethod
    def drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5):
        if HAS_PYAUTOGUI:
            pyautogui.moveTo(start_x, start_y)
            pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration)

    @staticmethod
    def scroll(direction: ScrollDirection, amount: int = 3):
        if HAS_PYAUTOGUI:
            if direction == ScrollDirection.UP:
                pyautogui.scroll(amount)
            elif direction == ScrollDirection.DOWN:
                pyautogui.scroll(-amount)
            elif direction == ScrollDirection.LEFT:
                pyautogui.hscroll(amount)
            elif direction == ScrollDirection.RIGHT:
                pyautogui.hscroll(-amount)

    @staticmethod
    def type_text(text: str, interval: float = 0.02):
        if HAS_PYAUTOGUI:
            pyautogui.write(text, interval=interval) if text.isascii() else pyautogui.typewrite(list(text), interval=interval)

    @staticmethod
    def press_key(key: str):
        if HAS_PYAUTOGUI:
            pyautogui.press(key)

    @staticmethod
    def hotkey(*keys: str):
        if HAS_PYAUTOGUI:
            pyautogui.hotkey(*keys)

    @staticmethod
    def get_clipboard() -> str:
        try:
            r = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=5,
            )
            return r.stdout.strip()
        except Exception:
            return ""

    @staticmethod
    def set_clipboard(text: str):
        escaped = text.replace("'", "''")
        subprocess.run(
            ["powershell", "-command", f"Set-Clipboard -Value '{escaped}'"],
            timeout=5,
        )

    @staticmethod
    def list_windows() -> list[WindowInfo]:
        windows = []
        try:
            script = '''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                using System.Text;
                public class Win32 {
                    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
                    [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);
                    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hWnd);
                    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
                    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);
                    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
                }
"@
            $windows = @()
            $callback = [Win32+EnumWindowsProc]{
                param($hWnd, $lParam)
                if ([Win32]::IsWindowVisible($hWnd)) {
                    $sb = New-Object System.Text.StringBuilder 256
                    [Win32]::GetWindowText($hWnd, $sb, 256) | Out-Null
                    $title = $sb.ToString()
                    if ($title) {
                        $rect = New-Object Win32+RECT
                        [Win32]::GetWindowRect($hWnd, [ref]$rect) | Out-Null
                        $script:windows += "$hWnd|||$title|||$($rect.Left)|||$($rect.Top)|||$($rect.Right - $rect.Left)|||$($rect.Bottom - $rect.Top)"
                    }
                }
                return $true
            }
            [Win32]::EnumWindows($callback, [IntPtr]::Zero) | Out-Null
            $windows -join ";;;"
            '''
            r = subprocess.run(
                ["powershell", "-command", script],
                capture_output=True, text=True, timeout=15,
            )
            for entry in r.stdout.strip().split(";;;"):
                parts = entry.split("|||")
                if len(parts) >= 6:
                    windows.append(WindowInfo(
                        window_id=parts[0],
                        title=parts[1],
                        x=int(parts[2]), y=int(parts[3]),
                        width=int(parts[4]), height=int(parts[5]),
                    ))
        except Exception:
            pass
        return windows

    @staticmethod
    def focus_window(window_id: str):
        try:
            script = f'''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {{
                    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hWnd);
                    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                }}
"@
            [Win32]::ShowWindow([IntPtr]::new({window_id}), 9)
            [Win32]::SetForegroundWindow([IntPtr]::new({window_id}))
            '''
            subprocess.run(["powershell", "-command", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def resize_window(window_id: str, width: int, height: int):
        try:
            script = f'''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {{
                    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
                }}
"@
            [Win32]::MoveWindow([IntPtr]::new({window_id}), 0, 0, {width}, {height}, $true)
            '''
            subprocess.run(["powershell", "-command", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def move_window(window_id: str, x: int, y: int):
        try:
            script = f'''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {{
                    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);
                    [DllImport("user32.dll")] public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);
                    [StructLayout(LayoutKind.Sequential)] public struct RECT {{ public int Left, Top, Right, Bottom; }}
                }}
"@
            $rect = New-Object Win32+RECT
            [Win32]::GetWindowRect([IntPtr]::new({window_id}), [ref]$rect) | Out-Null
            [Win32]::MoveWindow([IntPtr]::new({window_id}), {x}, {y}, $rect.Right - $rect.Left, $rect.Bottom - $rect.Top, $true)
            '''
            subprocess.run(["powershell", "-command", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def minimize_window(window_id: str):
        try:
            script = f'''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {{
                    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                }}
"@
            [Win32]::ShowWindow([IntPtr]::new({window_id}), 6)
            '''
            subprocess.run(["powershell", "-command", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def maximize_window(window_id: str):
        try:
            script = f'''
            Add-Type @"
                using System;
                using System.Runtime.InteropServices;
                public class Win32 {{
                    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
                }}
"@
            [Win32]::ShowWindow([IntPtr]::new({window_id}), 3)
            '''
            subprocess.run(["powershell", "-command", script], timeout=5)
        except Exception:
            pass

    @staticmethod
    def get_monitors() -> list[MonitorInfo]:
        monitors = []
        try:
            script = '''
            Add-Type -AssemblyName System.Windows.Forms
            $screens = [System.Windows.Forms.Screen]::AllScreens
            $i = 0
            foreach ($s in $screens) {
                $bounds = $s.Bounds
                $primary = $s.Primary
                "$i|||$($bounds.X)|||$($bounds.Y)|||$($bounds.Width)|||$($bounds.Height)|||$primary"
                $i++
            }
            '''
            r = subprocess.run(
                ["powershell", "-command", script],
                capture_output=True, text=True, timeout=10,
            )
            for line in r.stdout.strip().split("\n"):
                parts = line.strip().split("|||")
                if len(parts) >= 6:
                    monitors.append(MonitorInfo(
                        index=int(parts[0]),
                        x=int(parts[1]), y=int(parts[2]),
                        width=int(parts[3]), height=int(parts[4]),
                        is_primary=parts[5].lower() == "true",
                    ))
        except Exception:
            monitors.append(MonitorInfo(index=0, x=0, y=0, width=1920, height=1080, is_primary=True))
        return monitors

    @staticmethod
    def screenshot(region: Optional[ScreenRegion] = None) -> Optional[bytes]:
        if HAS_PIL and HAS_PYAUTOGUI:
            img = pyautogui.screenshot(region=region.to_tuple() if region else None)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        # Fallback: PowerShell screenshot
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = f.name
        try:
            script = f'''
            Add-Type -AssemblyName System.Windows.Forms
            Add-Type -AssemblyName System.Drawing
            $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
            $bmp = New-Object System.Drawing.Bitmap($bounds.Width, $bounds.Height)
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
            $bmp.Save("{tmp.replace(os.sep, '/')}")
            $g.Dispose()
            $bmp.Dispose()
            '''
            subprocess.run(["powershell", "-command", script], timeout=10)
            with open(tmp, "rb") as f:
                return f.read()
        finally:
            os.unlink(tmp)

    @staticmethod
    def ocr_image(image_bytes: bytes, lang: str = "eng") -> str:
        if HAS_PIL and HAS_TESSERACT:
            img = Image.open(io.BytesIO(image_bytes))
            return pytesseract.image_to_string(img, lang=lang)
        return ""

    @staticmethod
    def find_text_on_screen(image_bytes: bytes, search_text: str, lang: str = "eng") -> list[UIElement]:
        if not (HAS_PIL and HAS_TESSERACT):
            return []
        img = Image.open(io.BytesIO(image_bytes))
        try:
            data = pytesseract.image_to_data(img, lang=lang, output_type=pytesseract.Output.DICT)
        except Exception:
            return []
        results = []
        n = len(data["text"])
        for i in range(n):
            word = data["text"][i].strip()
            if not word:
                continue
            if search_text.lower() in word.lower():
                results.append(UIElement(
                    text=word,
                    x=data["left"][i], y=data["top"][i],
                    width=data["width"][i], height=data["height"][i],
                    confidence=data["conf"][i] / 100.0 if data["conf"][i] != -1 else 0.0,
                    element_type="text",
                ))
        return results


def _get_backend():
    """Get the platform-specific backend."""
    if PLATFORM == "darwin":
        return _DarwinBackend
    elif PLATFORM == "windows":
        return _WindowsBackend
    else:
        return _LinuxBackend


# ═══════════════════════════════════════════════════════════════
# Computer Use Engine
# ═══════════════════════════════════════════════════════════════

class ComputerUseEngine:
    """
    Real desktop computer use engine.
    Provides screen capture, mouse/keyboard control, OCR, window management,
    clipboard, multi-monitor, GUI element detection, and workflow recording/replay.
    """

    def __init__(self):
        self.backend = _get_backend()
        self._recording: list[RecordedAction] = []
        self._is_recording = False
        self._record_start_time: float = 0
        self._screenshot_cache: dict[str, bytes] = {}  # name -> png bytes
        self._data_dir = os.path.expanduser("~/.rally-agent/data/computer_use")
        os.makedirs(self._data_dir, exist_ok=True)

    @property
    def is_headless(self) -> bool:
        if PLATFORM == "linux":
            return not self.backend.has_display()
        return False

    def _check_display(self) -> Optional[str]:
        """Return error string if no display available, else None."""
        if self.is_headless:
            return "No display available (headless mode). Computer use requires a graphical display."
        return None

    def _save_screenshot(self, png_bytes: bytes, name: Optional[str] = None) -> dict[str, Any]:
        """Save screenshot to disk and return metadata."""
        name = name or f"screenshot_{int(time.time())}_{uuid.uuid4().hex[:6]}"
        path = os.path.join(self._data_dir, f"{name}.png")
        with open(path, "wb") as f:
            f.write(png_bytes)
        self._screenshot_cache[name] = png_bytes
        return {"name": name, "path": path, "size": len(png_bytes)}

    # ── Screen Capture ────────────────────────────────────────

    def take_screenshot(self, region: Optional[ScreenRegion] = None, name: Optional[str] = None) -> dict[str, Any]:
        """Capture the screen or a region. Returns file path and metadata."""
        err = self._check_display()
        if err:
            return {"error": err}
        png = self.backend.screenshot(region)
        if png is None:
            return {"error": "Screenshot capture failed"}
        result = self._save_screenshot(png, name)
        if HAS_PIL:
            img = Image.open(io.BytesIO(png))
            result["width"] = img.width
            result["height"] = img.height
        return result

    def screenshot_to_base64(self, region: Optional[ScreenRegion] = None) -> dict[str, Any]:
        """Capture screenshot and return as base64 (for AI vision)."""
        err = self._check_display()
        if err:
            return {"error": err}
        png = self.backend.screenshot(region)
        if png is None:
            return {"error": "Screenshot capture failed"}
        return {"base64": base64.b64encode(png).decode(), "size": len(png)}

    # ── Mouse Control ─────────────────────────────────────────

    def mouse_move(self, x: int, y: int, duration: float = 0.1) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.move_mouse(x, y, duration)
        self._record("move", x=x, y=y, duration=duration)
        return {"success": True, "x": x, "y": y}

    def mouse_click(self, x: int, y: int, button: str = "left", clicks: int = 1) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        btn = MouseButton(button)
        self.backend.click(x, y, button=btn, clicks=clicks)
        self._record("click", x=x, y=y, button=button, clicks=clicks)
        return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}

    def mouse_double_click(self, x: int, y: int) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.double_click(x, y)
        self._record("doubleclick", x=x, y=y)
        return {"success": True, "x": x, "y": y}

    def mouse_right_click(self, x: int, y: int) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.right_click(x, y)
        self._record("rightclick", x=x, y=y)
        return {"success": True, "x": x, "y": y}

    def mouse_drag(self, start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.drag(start_x, start_y, end_x, end_y, duration)
        self._record("drag", start_x=start_x, start_y=start_y, end_x=end_x, end_y=end_y, duration=duration)
        return {"success": True, "start": (start_x, start_y), "end": (end_x, end_y)}

    def mouse_scroll(self, direction: str = "down", amount: int = 3) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        d = ScrollDirection(direction)
        self.backend.scroll(d, amount)
        self._record("scroll", direction=direction, amount=amount)
        return {"success": True, "direction": direction, "amount": amount}

    def get_mouse_position(self) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        x, y = self.backend.get_mouse_position()
        return {"x": x, "y": y}

    # ── Keyboard Control ──────────────────────────────────────

    def type_text(self, text: str, interval: float = 0.02) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.type_text(text, interval)
        self._record("type", text=text, interval=interval)
        return {"success": True, "typed": len(text)}

    def press_key(self, key: str) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.press_key(key)
        self._record("key", key=key)
        return {"success": True, "key": key}

    def hotkey(self, *keys: str) -> dict[str, Any]:
        err = self._check_display()
        if err:
            return {"error": err}
        self.backend.hotkey(*keys)
        self._record("hotkey", keys=list(keys))
        return {"success": True, "keys": list(keys)}

    # ── Clipboard ─────────────────────────────────────────────

    def clipboard_get(self) -> dict[str, Any]:
        content = self.backend.get_clipboard()
        return {"content": content, "length": len(content)}

    def clipboard_set(self, text: str) -> dict[str, Any]:
        self.backend.set_clipboard(text)
        return {"success": True, "length": len(text)}

    # ── Window Management ─────────────────────────────────────

    def list_windows(self) -> dict[str, Any]:
        windows = self.backend.list_windows()
        return {"windows": [w.to_dict() for w in windows], "count": len(windows)}

    def focus_window(self, window_id: str) -> dict[str, Any]:
        self.backend.focus_window(window_id)
        return {"success": True, "window_id": window_id}

    def resize_window(self, window_id: str, width: int, height: int) -> dict[str, Any]:
        self.backend.resize_window(window_id, width, height)
        return {"success": True, "window_id": window_id, "width": width, "height": height}

    def move_window(self, window_id: str, x: int, y: int) -> dict[str, Any]:
        self.backend.move_window(window_id, x, y)
        return {"success": True, "window_id": window_id, "x": x, "y": y}

    def minimize_window(self, window_id: str) -> dict[str, Any]:
        self.backend.minimize_window(window_id)
        return {"success": True, "window_id": window_id, "action": "minimized"}

    def maximize_window(self, window_id: str) -> dict[str, Any]:
        self.backend.maximize_window(window_id)
        return {"success": True, "window_id": window_id, "action": "maximized"}

    # ── Multi-Monitor ─────────────────────────────────────────

    def get_monitors(self) -> dict[str, Any]:
        monitors = self.backend.get_monitors()
        return {"monitors": [m.to_dict() for m in monitors], "count": len(monitors)}

    # ── OCR ───────────────────────────────────────────────────

    def ocr_screen(self, region: Optional[ScreenRegion] = None, lang: str = "eng") -> dict[str, Any]:
        """Extract text from screen (or region) via OCR."""
        err = self._check_display()
        if err:
            return {"error": err}
        if not HAS_TESSERACT:
            return {"error": "pytesseract not installed. Run: pip install pytesseract"}
        png = self.backend.screenshot(region)
        if png is None:
            return {"error": "Screenshot failed"}
        text = self.backend.ocr_image(png, lang)
        return {"text": text, "lang": lang, "has_region": region is not None}

    def ocr_image_file(self, image_path: str, lang: str = "eng") -> dict[str, Any]:
        """Extract text from an image file."""
        if not os.path.exists(image_path):
            return {"error": f"File not found: {image_path}"}
        if not (HAS_PIL and HAS_TESSERACT):
            return {"error": "pytesseract/Pillow not installed"}
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        text = self.backend.ocr_image(image_bytes, lang)
        return {"text": text, "path": image_path, "lang": lang}

    # ── GUI Element Detection ─────────────────────────────────

    def find_text_on_screen(self, search_text: str, region: Optional[ScreenRegion] = None, lang: str = "eng") -> dict[str, Any]:
        """Find text on screen using OCR. Returns matching elements with positions."""
        err = self._check_display()
        if err:
            return {"error": err}
        if not (HAS_PIL and HAS_TESSERACT):
            return {"error": "pytesseract/Pillow not installed"}
        png = self.backend.screenshot(region)
        if png is None:
            return {"error": "Screenshot failed"}
        elements = self.backend.find_text_on_screen(png, search_text, lang)
        return {
            "search": search_text,
            "found": len(elements),
            "elements": [e.to_dict() for e in elements],
        }

    def find_and_click_text(self, search_text: str, region: Optional[ScreenRegion] = None, lang: str = "eng") -> dict[str, Any]:
        """Find text on screen and click its center."""
        err = self._check_display()
        if err:
            return {"error": err}
        result = self.find_text_on_screen(search_text, region, lang)
        if result.get("error"):
            return result
        if not result["elements"]:
            return {"error": f"Text '{search_text}' not found on screen", "found": 0}
        # Click the first match
        el = result["elements"][0]
        cx, cy = el["center"]
        offset_x = region.x if region else 0
        offset_y = region.y if region else 0
        self.backend.click(cx + offset_x, cy + offset_y)
        self._record("click", x=cx + offset_x, y=cy + offset_y, reason=f"find_and_click_text:{search_text}")
        return {"success": True, "clicked": el, "position": (cx + offset_x, cy + offset_y)}

    def find_visual_element(self, template_path: str, confidence: float = 0.8, region: Optional[ScreenRegion] = None) -> dict[str, Any]:
        """Find a UI element by visual template matching (requires Pillow)."""
        err = self._check_display()
        if err:
            return {"error": err}
        if not (HAS_PIL and HAS_PYAUTOGUI):
            return {"error": "Pillow and pyautogui required for visual search"}
        if not os.path.exists(template_path):
            return {"error": f"Template not found: {template_path}"}
        try:
            location = pyautogui.locateOnScreen(template_path, confidence=confidence, region=region.to_tuple() if region else None)
            if location:
                center = pyautogui.center(location)
                return {
                    "found": True,
                    "x": location.left, "y": location.top,
                    "width": location.width, "height": location.height,
                    "center": (center.x, center.y),
                    "confidence": confidence,
                }
            return {"found": False, "template": template_path}
        except Exception as e:
            return {"error": f"Visual search failed: {e}"}

    # ── Screen Info ───────────────────────────────────────────

    def get_screen_size(self) -> dict[str, Any]:
        w, h = self.backend.get_screen_size()
        return {"width": w, "height": h}

    # ── Workflow Recording & Replay ───────────────────────────

    def start_recording(self) -> dict[str, Any]:
        """Start recording user actions."""
        self._recording.clear()
        self._is_recording = True
        self._record_start_time = time.time()
        return {"success": True, "message": "Recording started"}

    def stop_recording(self) -> dict[str, Any]:
        """Stop recording and return the recorded actions."""
        self._is_recording = False
        actions = [a.to_dict() for a in self._recording]
        return {"success": True, "actions": actions, "count": len(actions), "duration_s": time.time() - self._record_start_time}

    def save_recording(self, name: str) -> dict[str, Any]:
        """Save recorded actions to a file."""
        if not self._recording:
            return {"error": "No recording to save"}
        path = os.path.join(self._data_dir, f"workflow_{name}.json")
        data = {
            "name": name,
            "created": time.time(),
            "actions": [a.to_dict() for a in self._recording],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return {"success": True, "path": path, "actions": len(self._recording)}

    def load_recording(self, name: str) -> dict[str, Any]:
        """Load a saved workflow."""
        path = os.path.join(self._data_dir, f"workflow_{name}.json")
        if not os.path.exists(path):
            return {"error": f"Workflow not found: {name}"}
        with open(path) as f:
            data = json.load(f)
        return {"success": True, "name": data["name"], "actions": data["actions"], "count": len(data["actions"])}

    def replay_recording(self, name: Optional[str] = None, speed: float = 1.0, actions: Optional[list[dict]] = None) -> dict[str, Any]:
        """Replay a recorded workflow or a provided action list."""
        err = self._check_display()
        if err:
            return {"error": err}

        if actions is None:
            if not name:
                return {"error": "Provide 'name' or 'actions'"}
            loaded = self.load_recording(name)
            if loaded.get("error"):
                return loaded
            actions = loaded["actions"]

        replayed = 0
        errors = []
        for i, action in enumerate(actions):
            try:
                action_type = action.get("type", action.get("action_type", ""))
                delay = action.get("delay", 0)
                if delay > 0 and speed > 0:
                    time.sleep(delay / speed)

                if action_type == "move":
                    self.backend.move_mouse(action["x"], action["y"])
                elif action_type == "click":
                    btn = MouseButton(action.get("button", "left"))
                    self.backend.click(action["x"], action["y"], button=btn, clicks=action.get("clicks", 1))
                elif action_type == "doubleclick":
                    self.backend.double_click(action["x"], action["y"])
                elif action_type == "rightclick":
                    self.backend.right_click(action["x"], action["y"])
                elif action_type == "type":
                    self.backend.type_text(action["text"], action.get("interval", 0.02))
                elif action_type == "key":
                    self.backend.press_key(action["key"])
                elif action_type == "hotkey":
                    self.backend.hotkey(*action["keys"])
                elif action_type == "scroll":
                    d = ScrollDirection(action.get("direction", "down"))
                    self.backend.scroll(d, action.get("amount", 3))
                elif action_type == "drag":
                    self.backend.drag(action["start_x"], action["start_y"], action["end_x"], action["end_y"])
                elif action_type == "wait":
                    time.sleep(action.get("duration", 1.0))
                else:
                    errors.append(f"Unknown action type: {action_type}")
                    continue
                replayed += 1
            except Exception as e:
                errors.append(f"Action {i} ({action_type}): {e}")

        return {"success": True, "replayed": replayed, "total": len(actions), "errors": errors}

    def list_recordings(self) -> dict[str, Any]:
        """List saved workflow recordings."""
        recordings = []
        for fname in os.listdir(self._data_dir):
            if fname.startswith("workflow_") and fname.endswith(".json"):
                try:
                    with open(os.path.join(self._data_dir, fname)) as f:
                        data = json.load(f)
                    recordings.append({
                        "name": data.get("name", fname),
                        "actions": len(data.get("actions", [])),
                        "created": data.get("created"),
                    })
                except Exception:
                    continue
        return {"recordings": recordings, "count": len(recordings)}

    def _record(self, action_type: str, **data):
        """Record an action if recording is active."""
        if self._is_recording:
            self._recording.append(RecordedAction(
                action_type=action_type,
                timestamp=time.time() - self._record_start_time,
                data=data,
            ))

    # ── Capabilities Check ────────────────────────────────────

    def get_capabilities(self) -> dict[str, Any]:
        """Check which capabilities are available."""
        return {
            "platform": PLATFORM,
            "headless": self.is_headless,
            "has_display": not self.is_headless if PLATFORM == "linux" else True,
            "pyautogui": HAS_PYAUTOGUI,
            "pillow": HAS_PIL,
            "tesseract": HAS_TESSERACT,
            "screen_capture": not self.is_headless,
            "mouse_control": HAS_PYAUTOGUI or PLATFORM == "linux",
            "keyboard_control": HAS_PYAUTOGUI or PLATFORM == "linux",
            "ocr": HAS_PIL and HAS_TESSERACT,
            "visual_search": HAS_PIL and HAS_PYAUTOGUI,
            "window_management": not self.is_headless,
            "clipboard": True,
            "multi_monitor": not self.is_headless,
            "workflow_recording": True,
        }


# ═══════════════════════════════════════════════════════════════
# Tool Definitions for Registry
# ═══════════════════════════════════════════════════════════════

class ScreenCaptureTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="screen_capture",
            description="Capture a screenshot of the entire screen or a region. Returns file path and metadata.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("name", "string", "Screenshot filename (auto-generated if omitted)"),
                ToolParameter("x", "integer", "Region X offset"),
                ToolParameter("y", "integer", "Region Y offset"),
                ToolParameter("width", "integer", "Region width"),
                ToolParameter("height", "integer", "Region height"),
                ToolParameter("base64", "boolean", "Return as base64 instead of saving to file"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["screenshot", "screen", "capture", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        region = None
        if all(k in arguments for k in ("x", "y", "width", "height")):
            region = ScreenRegion(arguments["x"], arguments["y"], arguments["width"], arguments["height"])

        if arguments.get("base64"):
            return json.dumps(self.engine.screenshot_to_base64(region))
        return json.dumps(self.engine.take_screenshot(region, arguments.get("name")))


class MouseControlTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="mouse_control",
            description="Control the mouse: move, click, double-click, right-click, drag, scroll, or get position.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Mouse action", required=True,
                    enum=["move", "click", "doubleclick", "rightclick", "drag", "scroll", "position"]),
                ToolParameter("x", "integer", "X coordinate"),
                ToolParameter("y", "integer", "Y coordinate"),
                ToolParameter("end_x", "integer", "End X coordinate (for drag)"),
                ToolParameter("end_y", "integer", "End Y coordinate (for drag)"),
                ToolParameter("button", "string", "Mouse button", enum=["left", "right", "middle"]),
                ToolParameter("clicks", "integer", "Number of clicks (1 or 2)"),
                ToolParameter("direction", "string", "Scroll direction", enum=["up", "down", "left", "right"]),
                ToolParameter("amount", "integer", "Scroll amount (default 3)"),
                ToolParameter("duration", "number", "Action duration in seconds"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["mouse", "click", "scroll", "drag", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "move":
            return json.dumps(self.engine.mouse_move(arguments["x"], arguments["y"], arguments.get("duration", 0.1)))
        elif action == "click":
            return json.dumps(self.engine.mouse_click(
                arguments["x"], arguments["y"],
                arguments.get("button", "left"), arguments.get("clicks", 1),
            ))
        elif action == "doubleclick":
            return json.dumps(self.engine.mouse_double_click(arguments["x"], arguments["y"]))
        elif action == "rightclick":
            return json.dumps(self.engine.mouse_right_click(arguments["x"], arguments["y"]))
        elif action == "drag":
            return json.dumps(self.engine.mouse_drag(
                arguments["x"], arguments["y"],
                arguments["end_x"], arguments["end_y"],
                arguments.get("duration", 0.5),
            ))
        elif action == "scroll":
            return json.dumps(self.engine.mouse_scroll(arguments.get("direction", "down"), arguments.get("amount", 3)))
        elif action == "position":
            return json.dumps(self.engine.get_mouse_position())
        return json.dumps({"error": f"Unknown action: {action}"})


class KeyboardControlTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="keyboard_control",
            description="Control the keyboard: type text, press keys, or execute hotkeys.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Keyboard action", required=True,
                    enum=["type", "press", "hotkey"]),
                ToolParameter("text", "string", "Text to type (for 'type' action)"),
                ToolParameter("key", "string", "Key to press (for 'press' action, e.g. 'enter', 'tab', 'f5')"),
                ToolParameter("keys", "array", "Keys for hotkey combo (for 'hotkey' action, e.g. ['ctrl', 'c'])"),
                ToolParameter("interval", "number", "Interval between keystrokes in seconds"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            dangerous=True,
            tags=["keyboard", "type", "hotkey", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "type":
            return json.dumps(self.engine.type_text(arguments["text"], arguments.get("interval", 0.02)))
        elif action == "press":
            return json.dumps(self.engine.press_key(arguments["key"]))
        elif action == "hotkey":
            return json.dumps(self.engine.hotkey(*arguments["keys"]))
        return json.dumps({"error": f"Unknown action: {action}"})


class ClipboardTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="clipboard",
            description="Get or set the system clipboard contents.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Clipboard action", required=True, enum=["get", "set"]),
                ToolParameter("text", "string", "Text to copy to clipboard (for 'set' action)"),
            ],
            tags=["clipboard", "copy", "paste", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]
        if action == "get":
            return json.dumps(self.engine.clipboard_get())
        elif action == "set":
            return json.dumps(self.engine.clipboard_set(arguments["text"]))
        return json.dumps({"error": f"Unknown action: {action}"})


class WindowManageTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="window_manage",
            description="Manage windows: list, focus, resize, move, minimize, maximize.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Window action", required=True,
                    enum=["list", "focus", "resize", "move", "minimize", "maximize"]),
                ToolParameter("window_id", "string", "Window ID (from list action)"),
                ToolParameter("x", "integer", "X position (for move)"),
                ToolParameter("y", "integer", "Y position (for move)"),
                ToolParameter("width", "integer", "Width (for resize)"),
                ToolParameter("height", "integer", "Height (for resize)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["window", "manage", "focus", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "list":
            return json.dumps(self.engine.list_windows())
        elif action == "focus":
            return json.dumps(self.engine.focus_window(arguments["window_id"]))
        elif action == "resize":
            return json.dumps(self.engine.resize_window(arguments["window_id"], arguments["width"], arguments["height"]))
        elif action == "move":
            return json.dumps(self.engine.move_window(arguments["window_id"], arguments["x"], arguments["y"]))
        elif action == "minimize":
            return json.dumps(self.engine.minimize_window(arguments["window_id"]))
        elif action == "maximize":
            return json.dumps(self.engine.maximize_window(arguments["window_id"]))
        return json.dumps({"error": f"Unknown action: {action}"})


class MonitorTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="monitor_info",
            description="Get information about connected display monitors.",
            category=ToolCategory.AUTOMATION,
            parameters=[],
            tags=["monitor", "display", "screen", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return json.dumps(self.engine.get_monitors())


class OCRTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="ocr",
            description="Extract text from the screen or an image file using OCR.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("source", "string", "Source: 'screen' for live capture, or path to image file"),
                ToolParameter("x", "integer", "Region X offset (screen only)"),
                ToolParameter("y", "integer", "Region Y offset (screen only)"),
                ToolParameter("width", "integer", "Region width (screen only)"),
                ToolParameter("height", "integer", "Region height (screen only)"),
                ToolParameter("lang", "string", "OCR language (default 'eng')"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["ocr", "text", "recognition", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        source = arguments.get("source", "screen")
        lang = arguments.get("lang", "eng")

        if source == "screen":
            region = None
            if all(k in arguments for k in ("x", "y", "width", "height")):
                region = ScreenRegion(arguments["x"], arguments["y"], arguments["width"], arguments["height"])
            return json.dumps(self.engine.ocr_screen(region, lang))
        else:
            return json.dumps(self.engine.ocr_image_file(source, lang))


class FindElementTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="find_element",
            description="Find UI elements on screen by text (OCR) or visual template matching.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("method", "string", "Detection method", required=True, enum=["text", "visual"]),
                ToolParameter("search", "string", "Text to search for (text method)"),
                ToolParameter("template", "string", "Path to template image (visual method)"),
                ToolParameter("confidence", "number", "Match confidence threshold (0-1, default 0.8)"),
                ToolParameter("click", "boolean", "Click the found element"),
                ToolParameter("x", "integer", "Search region X offset"),
                ToolParameter("y", "integer", "Search region Y offset"),
                ToolParameter("width", "integer", "Search region width"),
                ToolParameter("height", "integer", "Search region height"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["find", "element", "ocr", "visual", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        method = arguments["method"]
        region = None
        if all(k in arguments for k in ("x", "y", "width", "height")):
            region = ScreenRegion(arguments["x"], arguments["y"], arguments["width"], arguments["height"])

        if method == "text":
            search = arguments.get("search", "")
            if arguments.get("click"):
                return json.dumps(self.engine.find_and_click_text(search, region))
            return json.dumps(self.engine.find_text_on_screen(search, region))
        elif method == "visual":
            template = arguments.get("template", "")
            confidence = arguments.get("confidence", 0.8)
            result = self.engine.find_visual_element(template, confidence, region)
            if result.get("found") and arguments.get("click"):
                cx, cy = result["center"]
                self.engine.backend.click(cx, cy)
                result["clicked"] = True
            return json.dumps(result)
        return json.dumps({"error": f"Unknown method: {method}"})


class WorkflowTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="workflow",
            description="Record, save, load, and replay GUI automation workflows.",
            category=ToolCategory.AUTOMATION,
            parameters=[
                ToolParameter("action", "string", "Workflow action", required=True,
                    enum=["start_recording", "stop_recording", "save", "load", "replay", "list"]),
                ToolParameter("name", "string", "Workflow name (for save/load/replay)"),
                ToolParameter("speed", "number", "Replay speed multiplier (default 1.0)"),
                ToolParameter("actions", "array", "Custom action list to replay (instead of loading)"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["workflow", "record", "replay", "automation", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "start_recording":
            return json.dumps(self.engine.start_recording())
        elif action == "stop_recording":
            return json.dumps(self.engine.stop_recording())
        elif action == "save":
            return json.dumps(self.engine.save_recording(arguments["name"]))
        elif action == "load":
            return json.dumps(self.engine.load_recording(arguments["name"]))
        elif action == "replay":
            return json.dumps(self.engine.replay_recording(
                name=arguments.get("name"),
                speed=arguments.get("speed", 1.0),
                actions=arguments.get("actions"),
            ))
        elif action == "list":
            return json.dumps(self.engine.list_recordings())
        return json.dumps({"error": f"Unknown action: {action}"})


class ScreenSizeTool(BaseTool):
    def __init__(self, engine: ComputerUseEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="screen_size",
            description="Get the screen resolution and capabilities.",
            category=ToolCategory.AUTOMATION,
            parameters=[],
            tags=["screen", "size", "resolution", "computer-use"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        size = self.engine.get_screen_size()
        caps = self.engine.get_capabilities()
        return json.dumps({**size, "capabilities": caps})


# ═══════════════════════════════════════════════════════════════
# Registration Helper
# ═══════════════════════════════════════════════════════════════

def register_computer_use_tools(registry: ToolRegistry) -> ComputerUseEngine:
    """Create a shared ComputerUseEngine and register all computer-use tools."""
    engine = ComputerUseEngine()

    tools = [
        ScreenCaptureTool(engine),
        MouseControlTool(engine),
        KeyboardControlTool(engine),
        ClipboardTool(engine),
        WindowManageTool(engine),
        MonitorTool(engine),
        OCRTool(engine),
        FindElementTool(engine),
        WorkflowTool(engine),
        ScreenSizeTool(engine),
    ]

    for tool in tools:
        registry.register(tool)

    return engine
