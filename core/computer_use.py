"""
🟣 Rally Agent — Computer Use
Screen interaction: screenshots, clicking, typing via system tools.
"""

import asyncio
import os
import subprocess
import logging
import base64
import time
from typing import Optional

logger = logging.getLogger("rally.computer_use")


class ComputerUse:
    """Provides screen interaction capabilities: screenshots, clicks, typing."""

    def __init__(self, config=None):
        self.config = config
        self.data_dir = os.path.expanduser("~/.rally-agent/data/screenshots")
        os.makedirs(self.data_dir, exist_ok=True)

    async def screenshot(self, output_path: str = None) -> dict:
        """Take a screenshot of the current screen."""
        if not output_path:
            output_path = os.path.join(self.data_dir, f"screenshot_{int(time.time())}.png")

        try:
            # Try different screenshot tools
            for cmd in [
                ["scrot", "-o", output_path],
                ["gnome-screenshot", "-f", output_path],
                ["import", "-window", "root", output_path],
                ["screencapture", output_path],  # macOS
            ]:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    if result.returncode == 0 and os.path.exists(output_path):
                        with open(output_path, "rb") as f:
                            img_data = base64.b64encode(f.read()).decode()
                        return {
                            "status": "success",
                            "path": output_path,
                            "image_base64": img_data[:100] + "...",
                            "size_bytes": os.path.getsize(output_path),
                        }
                except FileNotFoundError:
                    continue

            return {"status": "error", "message": "No screenshot tool available. Install scrot or imagemagick."}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def click(self, x: int, y: int) -> dict:
        """Click at screen coordinates."""
        try:
            for cmd in [
                ["xdotool", "mousemove", str(x), str(y), "click", "1"],
                ["cliclick", f"c:{x},{y}"],  # macOS
            ]:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=5)
                    if result.returncode == 0:
                        return {"status": "clicked", "x": x, "y": y}
                except FileNotFoundError:
                    continue

            return {"status": "error", "message": "No click tool available. Install xdotool."}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def type_text(self, text: str) -> dict:
        """Type text at the current cursor position."""
        try:
            for cmd in [
                ["xdotool", "type", "--clearmodifiers", text],
                ["xdotool", "type", text],
            ]:
                try:
                    result = subprocess.run(cmd, capture_output=True, timeout=10)
                    if result.returncode == 0:
                        return {"status": "typed", "length": len(text)}
                except FileNotFoundError:
                    continue

            return {"status": "error", "message": "No typing tool available. Install xdotool."}

        except Exception as e:
            return {"status": "error", "message": str(e)}

    async def key_press(self, keys: str) -> dict:
        """Press keyboard keys (e.g., 'ctrl+c', 'enter')."""
        try:
            result = subprocess.run(
                ["xdotool", "key", keys],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0:
                return {"status": "pressed", "keys": keys}
            return {"status": "error", "message": result.stderr.decode()}
        except FileNotFoundError:
            return {"status": "error", "message": "xdotool not installed"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
