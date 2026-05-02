"""
🟣 Rally Agent — Browser Automation Engine
Playwright-powered browser control with smart element detection, form auto-filling,
multi-tab management, session persistence, stealth mode, page state machine,
network interception, accessibility tree, and more.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
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
# Page State Machine
# ═══════════════════════════════════════════════════════════════

class PageState(str, Enum):
    IDLE = "idle"
    NAVIGATING = "navigating"
    LOADING = "loading"
    INTERACTIVE = "interactive"
    FORM_FILLING = "form_filling"
    WAITING = "waiting"
    ERROR = "error"


@dataclass
class StateTransition:
    from_state: PageState
    to_state: PageState
    trigger: str
    timestamp: float
    metadata: dict[str, Any] = field(default_factory=dict)


class PageStateMachine:
    """Tracks the current state of the browser page and state transitions."""

    def __init__(self):
        self.current = PageState.IDLE
        self.history: list[StateTransition] = []
        self._handlers: dict[PageState, list[Callable]] = {}

    def transition(self, to: PageState, trigger: str, metadata: Optional[dict] = None):
        transition = StateTransition(
            from_state=self.current,
            to_state=to,
            trigger=trigger,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self.history.append(transition)
        self.current = to

        # Fire handlers
        for handler in self._handlers.get(to, []):
            try:
                handler(transition)
            except Exception:
                pass

    def on_state(self, state: PageState, handler: Callable):
        self._handlers.setdefault(state, []).append(handler)

    def get_history(self, limit: int = 20) -> list[dict]:
        return [
            {
                "from": t.from_state.value,
                "to": t.to_state.value,
                "trigger": t.trigger,
                "time": datetime.fromtimestamp(t.timestamp).isoformat(),
            }
            for t in self.history[-limit:]
        ]


# ═══════════════════════════════════════════════════════════════
# Browser Profile
# ═══════════════════════════════════════════════════════════════

@dataclass
class BrowserProfile:
    """Configuration for a browser instance."""
    name: str = "default"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    timezone: str = "America/New_York"
    proxy: Optional[dict[str, str]] = None  # {"server": "...", "username": "...", "password": "..."}
    stealth: bool = False
    persistent_cookies: bool = False
    storage_dir: Optional[str] = None

    def to_context_options(self) -> dict[str, Any]:
        opts = {
            "viewport": {"width": self.viewport_width, "height": self.viewport_height},
            "user_agent": self.user_agent,
            "locale": self.locale,
            "timezone_id": self.timezone,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        return opts


# Stealth scripts to inject
STEALTH_SCRIPTS = """
// Override navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Override chrome runtime
window.chrome = { runtime: {} };

// Override permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) =>
    parameters.name === 'notifications'
        ? Promise.resolve({ state: Notification.permission })
        : originalQuery(parameters);

// Override plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Override languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en'],
});

// Override WebGL vendor
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return getParameter.call(this, parameter);
};
"""


# ═══════════════════════════════════════════════════════════════
# Download Manager
# ═══════════════════════════════════════════════════════════════

class DownloadManager:
    """Manages file downloads through the browser."""

    def __init__(self, download_dir: str):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self.downloads: list[dict[str, Any]] = []

    async def handle_download(self, download) -> dict[str, Any]:
        filename = download.suggested_filename
        path = os.path.join(self.download_dir, filename)
        await download.save_as(path)

        record = {
            "filename": filename,
            "path": path,
            "size": os.path.getsize(path) if os.path.exists(path) else 0,
            "timestamp": datetime.now().isoformat(),
            "url": download.url,
        }
        self.downloads.append(record)
        return record

    def get_downloads(self) -> list[dict[str, Any]]:
        return self.downloads[-50:]


# ═══════════════════════════════════════════════════════════════
# Network Interceptor
# ═══════════════════════════════════════════════════════════════

@dataclass
class InterceptedRequest:
    url: str
    method: str
    resource_type: str
    headers: dict[str, str]
    timestamp: float
    blocked: bool = False


@dataclass
class InterceptedResponse:
    url: str
    status: int
    headers: dict[str, str]
    body_size: int
    timestamp: float


class NetworkInterceptor:
    """Intercepts and optionally modifies network requests."""

    def __init__(self):
        self.requests: list[InterceptedRequest] = []
        self.responses: list[InterceptedResponse] = []
        self.blocked_patterns: list[str] = []
        self.blocked_resource_types: set[str] = set()

    def should_block(self, url: str, resource_type: str) -> bool:
        if resource_type in self.blocked_resource_types:
            return True
        for pattern in self.blocked_patterns:
            if re.search(pattern, url):
                return True
        return False

    def add_block_pattern(self, pattern: str):
        self.blocked_patterns.append(pattern)

    def block_resource_types(self, types: list[str]):
        self.blocked_resource_types.update(types)

    def get_summary(self) -> dict[str, Any]:
        return {
            "total_requests": len(self.requests),
            "total_responses": len(self.responses),
            "blocked": sum(1 for r in self.requests if r.blocked),
            "by_type": self._count_by_type(),
            "by_status": self._count_by_status(),
        }

    def _count_by_type(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for r in self.requests:
            counts[r.resource_type] = counts.get(r.resource_type, 0) + 1
        return counts

    def _count_by_status(self) -> dict[int, int]:
        counts: dict[int, int] = {}
        for r in self.responses:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


# ═══════════════════════════════════════════════════════════════
# Tab Manager
# ═══════════════════════════════════════════════════════════════

class TabManager:
    """Manages multiple browser tabs."""

    def __init__(self):
        self.tabs: dict[str, Any] = {}  # tab_id -> page
        self.active_tab_id: Optional[str] = None
        self.tab_history: dict[str, list[str]] = {}  # tab_id -> [urls]

    def register_tab(self, tab_id: str, page: Any):
        self.tabs[tab_id] = page
        self.active_tab_id = tab_id
        self.tab_history[tab_id] = []

    def remove_tab(self, tab_id: str):
        self.tabs.pop(tab_id, None)
        self.tab_history.pop(tab_id, None)
        if self.active_tab_id == tab_id:
            remaining = list(self.tabs.keys())
            self.active_tab_id = remaining[0] if remaining else None

    def get_active_page(self) -> Optional[Any]:
        if self.active_tab_id:
            return self.tabs.get(self.active_tab_id)
        return None

    def switch_tab(self, tab_id: str) -> bool:
        if tab_id in self.tabs:
            self.active_tab_id = tab_id
            return True
        return False

    def list_tabs(self) -> list[dict[str, Any]]:
        return [
            {
                "id": tid,
                "active": tid == self.active_tab_id,
                "history_count": len(self.tab_history.get(tid, [])),
            }
            for tid in self.tabs
        ]


# ═══════════════════════════════════════════════════════════════
# Browser Engine
# ═══════════════════════════════════════════════════════════════

class BrowserEngine:
    """
    Full browser automation engine with Playwright.
    Supports smart element detection, form auto-filling, multi-tab,
    session persistence, stealth mode, network interception, accessibility tree, and more.
    """

    def __init__(self, config: Any = None, profile: Optional[BrowserProfile] = None):
        self.config = config
        self.profile = profile or BrowserProfile()
        self.browser = None
        self.context = None
        self._playwright = None

        # Subsystems
        self.state = PageStateMachine()
        self.tabs = TabManager()
        self.network = NetworkInterceptor()
        self.screenshots_dir = os.path.expanduser("~/.rally-agent/data/screenshots")
        self.downloads_dir = os.path.expanduser("~/.rally-agent/data/downloads")
        os.makedirs(self.screenshots_dir, exist_ok=True)
        os.makedirs(self.downloads_dir, exist_ok=True)
        self.downloads = DownloadManager(self.downloads_dir)
        self.history: list[dict[str, Any]] = []
        self._interception_active = False

    @property
    def page(self):
        """Get the currently active page."""
        return self.tabs.get_active_page()

    async def launch(self, headless: bool = True, browser_type: str = "chromium") -> str:
        """Launch a browser instance with the configured profile."""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            return "Error: Playwright not installed. Run: pip install playwright && playwright install"

        try:
            self._playwright = await async_playwright().start()

            launcher = {
                "firefox": self._playwright.firefox,
                "webkit": self._playwright.webkit,
            }.get(browser_type, self._playwright.chromium)

            launch_opts = {"headless": headless}
            if self.profile.proxy and "server" in self.profile.proxy:
                launch_opts["proxy"] = self.profile.proxy

            self.browser = await launcher.launch(**launch_opts)
            context_opts = self.profile.to_context_options()

            # Use persistent context if storage_dir is set
            if self.profile.persistent_cookies and self.profile.storage_dir:
                os.makedirs(self.profile.storage_dir, exist_ok=True)
                self.context = await self.browser.new_context(
                    storage_state=os.path.join(self.profile.storage_dir, "state.json")
                    if os.path.exists(os.path.join(self.profile.storage_dir, "state.json"))
                    else None,
                    **context_opts,
                )
            else:
                self.context = await self.browser.new_context(**context_opts)

            # Inject stealth scripts
            if self.profile.stealth:
                await self.context.add_init_script(STEALTH_SCRIPTS)

            # Set up download handling
            self.context.on("download", lambda d: asyncio.ensure_future(self.downloads.handle_download(d)))

            # Create initial tab
            page = await self.context.new_page()
            tab_id = f"tab-{uuid.uuid4().hex[:8]}"
            self.tabs.register_tab(tab_id, page)

            # Set up network interception
            page.on("request", lambda req: asyncio.ensure_future(self._on_request(req)))
            page.on("response", lambda resp: asyncio.ensure_future(self._on_response(resp)))

            self.state.transition(PageState.IDLE, "launch")
            return json.dumps({
                "success": True,
                "browser": browser_type,
                "headless": headless,
                "stealth": self.profile.stealth,
                "tab_id": tab_id,
            })

        except Exception as e:
            return json.dumps({"error": f"Browser launch failed: {e}"})

    async def _on_request(self, request):
        """Handle intercepted request."""
        intercepted = InterceptedRequest(
            url=request.url,
            method=request.method,
            resource_type=request.resource_type,
            headers=dict(request.headers),
            timestamp=time.time(),
        )

        if self._interception_active and self.network.should_block(request.url, request.resource_type):
            intercepted.blocked = True
            try:
                await request.abort()
            except Exception:
                pass

        self.network.requests.append(intercepted)

    async def _on_response(self, response):
        """Handle intercepted response."""
        try:
            self.network.responses.append(InterceptedResponse(
                url=response.url,
                status=response.status,
                headers=dict(response.headers),
                body_size=response.headers.get("content-length", 0),
                timestamp=time.time(),
            ))
        except Exception:
            pass

    # ── Navigation ────────────────────────────────────────────

    async def navigate(self, url: str, wait_until: str = "domcontentloaded", retry: int = 2) -> str:
        """Navigate to a URL with auto-retry on failure."""
        if not self.page:
            return json.dumps({"error": "No browser open. Call launch() first."})

        self.state.transition(PageState.NAVIGATING, "navigate", {"url": url})

        for attempt in range(retry + 1):
            try:
                response = await self.page.goto(url, wait_until=wait_until, timeout=30000)
                title = await self.page.title()
                self.history.append({
                    "url": url, "title": title,
                    "timestamp": datetime.now().isoformat(),
                    "status": response.status if response else None,
                })

                # Track in tab history
                if self.tabs.active_tab_id:
                    self.tabs.tab_history.setdefault(self.tabs.active_tab_id, []).append(url)

                self.state.transition(PageState.INTERACTIVE, "loaded", {"url": url})
                return json.dumps({
                    "success": True,
                    "url": str(self.page.url),
                    "title": title,
                    "status": response.status if response else None,
                    "attempt": attempt + 1,
                })

            except Exception as e:
                if attempt < retry:
                    await asyncio.sleep(1)
                    continue
                self.state.transition(PageState.ERROR, "navigation_failed", {"url": url, "error": str(e)})
                return json.dumps({"error": f"Navigation failed after {retry + 1} attempts: {e}"})

        return json.dumps({"error": "Navigation failed"})

    # ── Smart Element Detection ───────────────────────────────

    async def find_element(
        self,
        text: Optional[str] = None,
        role: Optional[str] = None,
        aria_label: Optional[str] = None,
        selector: Optional[str] = None,
        nth: int = 0,
    ) -> dict[str, Any]:
        """
        Smart element detection: find by text, role, aria-label, CSS selector, or visual position.
        Returns element info or error.
        """
        if not self.page:
            return {"error": "No browser open"}

        try:
            # Priority: selector > aria_label + role > text > role alone
            if selector:
                elements = await self.page.query_selector_all(selector)
                if elements and nth < len(elements):
                    el = elements[nth]
                    box = await el.bounding_box()
                    text_content = await el.inner_text()
                    return {"found": True, "text": text_content[:200], "selector": selector, "bounding_box": box}

            if aria_label:
                el = await self.page.query_selector(f'[aria-label="{aria_label}"]')
                if el:
                    box = await el.bounding_box()
                    return {"found": True, "aria_label": aria_label, "bounding_box": box}

            if role and text:
                # Use Playwright's role selector
                try:
                    el = self.page.get_by_role(role, name=text)
                    if await el.count() > nth:
                        item = el.nth(nth)
                        box = await item.bounding_box()
                        return {"found": True, "role": role, "text": text, "bounding_box": box}
                except Exception:
                    pass

            if text:
                # Try text selector
                el = await self.page.query_selector(f'text="{text}"')
                if not el:
                    el = await self.page.query_selector(f':text("{text}")')
                if el:
                    box = await el.bounding_box()
                    return {"found": True, "text": text, "bounding_box": box}

            if role:
                el = await self.page.query_selector(f'[role="{role}"]')
                if el:
                    box = await el.bounding_box()
                    return {"found": True, "role": role, "bounding_box": box}

            return {"found": False, "error": "Element not found"}

        except Exception as e:
            return {"found": False, "error": str(e)}

    # ── Interaction ───────────────────────────────────────────

    async def click_element(self, selector: Optional[str] = None, text: Optional[str] = None,
                            role: Optional[str] = None, nth: int = 0) -> str:
        """Click an element by selector, text, or role."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            if selector:
                await self.page.click(selector, timeout=5000)
                return json.dumps({"success": True, "clicked": selector})
            elif text:
                await self.page.click(f'text="{text}"', timeout=5000)
                return json.dumps({"success": True, "clicked_text": text})
            elif role:
                el = self.page.get_by_role(role)
                if await el.count() > nth:
                    await el.nth(nth).click()
                    return json.dumps({"success": True, "clicked_role": role, "nth": nth})
            return json.dumps({"error": "Provide selector, text, or role"})
        except Exception as e:
            return json.dumps({"error": f"Click failed: {e}"})

    async def type_text(self, text: str, selector: Optional[str] = None, delay: int = 50, clear: bool = True) -> str:
        """Type text into an element."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            if selector:
                if clear:
                    await self.page.fill(selector, text)
                else:
                    await self.page.click(selector)
                    await self.page.type(selector, text, delay=delay)
            else:
                await self.page.keyboard.type(text, delay=delay)
            return json.dumps({"success": True, "typed": len(text)})
        except Exception as e:
            return json.dumps({"error": f"Type failed: {e}"})

    async def press_key(self, key: str, modifiers: Optional[list[str]] = None) -> str:
        """Press a keyboard key with optional modifiers."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            if modifiers:
                for mod in modifiers:
                    await self.page.keyboard.down(mod)
                await self.page.keyboard.press(key)
                for mod in modifiers:
                    await self.page.keyboard.up(mod)
            else:
                await self.page.keyboard.press(key)
            return json.dumps({"success": True, "key": key, "modifiers": modifiers})
        except Exception as e:
            return json.dumps({"error": f"Key press failed: {e}"})

    async def scroll_page(self, direction: str = "down", amount: int = 500) -> str:
        """Scroll the page in a direction."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            deltas = {"down": (0, amount), "up": (0, -amount), "right": (amount, 0), "left": (-amount, 0)}
            dx, dy = deltas.get(direction, (0, amount))
            await self.page.mouse.wheel(dx, dy)
            return json.dumps({"success": True, "direction": direction, "amount": amount})
        except Exception as e:
            return json.dumps({"error": f"Scroll failed: {e}"})

    # ── Form Auto-Filling ─────────────────────────────────────

    async def auto_fill_form(self, data: dict[str, str]) -> str:
        """
        Auto-fill a form using AI understanding of field labels.
        Data maps human-readable labels to values, e.g. {"Email": "test@example.com", "Name": "John"}.
        """
        if not self.page:
            return json.dumps({"error": "No browser open"})

        self.state.transition(PageState.FORM_FILLING, "auto_fill")
        results = []

        for label, value in data.items():
            try:
                filled = False

                # Strategy 1: label[for] -> input[id]
                label_el = await self.page.query_selector(f'label:has-text("{label}")')
                if label_el:
                    for_id = await label_el.get_attribute("for")
                    if for_id:
                        await self.page.fill(f"#{for_id}", str(value))
                        results.append({"field": label, "status": "filled", "method": "label-for"})
                        filled = True

                # Strategy 2: aria-label
                if not filled:
                    el = await self.page.query_selector(f'[aria-label*="{label}" i]')
                    if el:
                        await el.fill(str(value))
                        results.append({"field": label, "status": "filled", "method": "aria-label"})
                        filled = True

                # Strategy 3: placeholder
                if not filled:
                    el = await self.page.query_selector(f'[placeholder*="{label}" i]')
                    if el:
                        await el.fill(str(value))
                        results.append({"field": label, "status": "filled", "method": "placeholder"})
                        filled = True

                # Strategy 4: find input near text
                if not filled:
                    js_result = await self.page.evaluate(f"""
                        () => {{
                            const labels = Array.from(document.querySelectorAll('label, span, div, td'));
                            for (const el of labels) {{
                                if (el.textContent.toLowerCase().includes('{label.lower()}')) {{
                                    // Find nearest input
                                    const parent = el.closest('tr, div, form') || el.parentElement;
                                    const input = parent.querySelector('input, textarea, select');
                                    if (input) {{
                                        input.scrollIntoView();
                                        return true;
                                    }}
                                }}
                            }}
                            return false;
                        }}
                    """)
                    if js_result:
                        # Try filling via JS
                        await self.page.evaluate(f"""
                            () => {{
                                const labels = Array.from(document.querySelectorAll('label, span, div, td'));
                                for (const el of labels) {{
                                    if (el.textContent.toLowerCase().includes('{label.lower()}')) {{
                                        const parent = el.closest('tr, div, form') || el.parentElement;
                                        const input = parent.querySelector('input, textarea, select');
                                        if (input) {{
                                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                                window.HTMLInputElement.prototype, 'value').set;
                                            nativeInputValueSetter.call(input, '{value}');
                                            input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                            input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                            return;
                                        }}
                                    }}
                                }}
                            }}
                        """)
                        results.append({"field": label, "status": "filled", "method": "js-near-text"})
                        filled = True

                if not filled:
                    results.append({"field": label, "status": "not_found", "method": None})

            except Exception as e:
                results.append({"field": label, "status": "error", "error": str(e)})

        self.state.transition(PageState.INTERACTIVE, "form_filled")
        return json.dumps({"results": results, "filled": sum(1 for r in results if r["status"] == "filled")})

    # ── Multi-Tab Management ──────────────────────────────────

    async def new_tab(self, url: Optional[str] = None) -> str:
        """Open a new browser tab."""
        if not self.context:
            return json.dumps({"error": "No browser context"})

        try:
            page = await self.context.new_page()
            tab_id = f"tab-{uuid.uuid4().hex[:8]}"
            self.tabs.register_tab(tab_id, page)

            # Set up interception on new tab
            page.on("request", lambda req: asyncio.ensure_future(self._on_request(req)))
            page.on("response", lambda resp: asyncio.ensure_future(self._on_response(resp)))

            if url:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            return json.dumps({"success": True, "tab_id": tab_id, "url": url})
        except Exception as e:
            return json.dumps({"error": f"Failed to create tab: {e}"})

    async def close_tab(self, tab_id: Optional[str] = None) -> str:
        """Close a browser tab."""
        target_id = tab_id or self.tabs.active_tab_id
        if not target_id or target_id not in self.tabs.tabs:
            return json.dumps({"error": "No tab to close"})

        try:
            await self.tabs.tabs[target_id].close()
            self.tabs.remove_tab(target_id)
            return json.dumps({"success": True, "closed": target_id, "active": self.tabs.active_tab_id})
        except Exception as e:
            return json.dumps({"error": f"Failed to close tab: {e}"})

    async def switch_tab(self, tab_id: str) -> str:
        """Switch to a different tab."""
        if self.tabs.switch_tab(tab_id):
            page = self.tabs.get_active_page()
            url = page.url if page else None
            return json.dumps({"success": True, "active_tab": tab_id, "url": url})
        return json.dumps({"error": f"Tab not found: {tab_id}"})

    def list_tabs(self) -> str:
        """List all open tabs."""
        return json.dumps({"tabs": self.tabs.list_tabs()})

    # ── Screenshot + Analysis ─────────────────────────────────

    async def screenshot(self, name: Optional[str] = None, full_page: bool = False,
                         selector: Optional[str] = None, quality: int = 90) -> str:
        """Take a screenshot of the page, element, or full page."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            name = name or f"screenshot_{int(time.time())}"
            path = os.path.join(self.screenshots_dir, f"{name}.png")

            if selector:
                el = await self.page.query_selector(selector)
                if el:
                    await el.screenshot(path=path)
                else:
                    return json.dumps({"error": f"Element not found: {selector}"})
            else:
                await self.page.screenshot(path=path, full_page=full_page)

            return json.dumps({
                "success": True, "path": path,
                "size": os.path.getsize(path),
                "full_page": full_page,
            })
        except Exception as e:
            return json.dumps({"error": f"Screenshot failed: {e}"})

    async def screenshot_as_base64(self, full_page: bool = False) -> str:
        """Take a screenshot and return as base64 (for AI vision analysis)."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            buffer = await self.page.screenshot(full_page=full_page)
            b64 = base64.b64encode(buffer).decode()
            return json.dumps({"base64": b64[:100000], "size": len(buffer)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Accessibility Tree ────────────────────────────────────

    async def get_accessibility_tree(self) -> str:
        """Extract the accessibility tree of the current page."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            snapshot = await self.page.accessibility.snapshot()
            return json.dumps({"tree": snapshot}, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"Accessibility tree error: {e}"})

    # ── JavaScript Injection ──────────────────────────────────

    async def evaluate_js(self, code: str) -> str:
        """Execute JavaScript on the page."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            result = await self.page.evaluate(code)
            if isinstance(result, (dict, list)):
                return json.dumps({"result": result}, default=str)
            return json.dumps({"result": str(result)})
        except Exception as e:
            return json.dumps({"error": f"JS error: {e}"})

    # ── Network Interception Control ──────────────────────────

    async def enable_interception(self, block_patterns: Optional[list[str]] = None,
                                   block_types: Optional[list[str]] = None) -> str:
        """Enable network request interception and optionally block patterns."""
        self._interception_active = True
        if block_patterns:
            for p in block_patterns:
                self.network.add_block_pattern(p)
        if block_types:
            self.network.block_resource_types(block_types)
        return json.dumps({"interception": True, "patterns": self.network.blocked_patterns, "types": list(self.network.blocked_resource_types)})

    async def disable_interception(self) -> str:
        self._interception_active = False
        return json.dumps({"interception": False})

    def get_network_summary(self) -> str:
        return json.dumps(self.network.get_summary())

    # ── Session Persistence ───────────────────────────────────

    async def save_session(self, path: Optional[str] = None) -> str:
        """Save cookies and storage state for session persistence."""
        if not self.context:
            return json.dumps({"error": "No browser context"})

        path = path or os.path.join(self.downloads_dir, "session_state.json")
        try:
            state = await self.context.storage_state()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump(state, f, indent=2)
            return json.dumps({"success": True, "path": path, "cookies": len(state.get("cookies", []))})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def load_session(self, path: str) -> str:
        """Load a previously saved session state."""
        if not os.path.exists(path):
            return json.dumps({"error": f"Session file not found: {path}"})
        try:
            with open(path) as f:
                state = json.load(f)
            # Close existing context and create new one with state
            if self.context:
                await self.context.close()
            context_opts = self.profile.to_context_options()
            self.context = await self.browser.new_context(storage_state=state, **context_opts)
            if self.profile.stealth:
                await self.context.add_init_script(STEALTH_SCRIPTS)
            page = await self.context.new_page()
            tab_id = f"tab-{uuid.uuid4().hex[:8]}"
            self.tabs.register_tab(tab_id, page)
            return json.dumps({"success": True, "cookies": len(state.get("cookies", []))})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Cookie Management ─────────────────────────────────────

    async def get_cookies(self) -> str:
        if not self.context:
            return json.dumps({"error": "No context"})
        cookies = await self.context.cookies()
        return json.dumps({"cookies": cookies})

    async def set_cookies(self, cookies: list[dict[str, Any]]) -> str:
        if not self.context:
            return json.dumps({"error": "No context"})
        await self.context.add_cookies(cookies)
        return json.dumps({"success": True, "cookies_set": len(cookies)})

    async def clear_cookies(self) -> str:
        if not self.context:
            return json.dumps({"error": "No context"})
        await self.context.clear_cookies()
        return json.dumps({"success": True, "message": "All cookies cleared"})

    # ── PDF Generation ────────────────────────────────────────

    async def generate_pdf(self, path: Optional[str] = None) -> str:
        """Generate a PDF of the current page."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        try:
            path = path or os.path.join(self.screenshots_dir, f"page_{int(time.time())}.pdf")
            await self.page.pdf(path=path)
            return json.dumps({"success": True, "path": path, "size": os.path.getsize(path)})
        except Exception as e:
            return json.dumps({"error": f"PDF generation failed: {e}"})

    # ── Content Extraction ────────────────────────────────────

    async def get_text(self, max_chars: int = 10000) -> str:
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            text = await self.page.inner_text("body")
            return json.dumps({"text": text[:max_chars], "truncated": len(text) > max_chars})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def get_html(self, max_chars: int = 20000) -> str:
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            html = await self.page.content()
            return json.dumps({"html": html[:max_chars], "truncated": len(html) > max_chars})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def get_links(self) -> str:
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            links = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().substring(0, 100),
                    href: a.href,
                })).filter(l => l.text && l.href)
            """)
            return json.dumps({"links": links[:100], "count": len(links)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def get_images(self) -> str:
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            images = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                })).filter(i => i.src)
            """)
            return json.dumps({"images": images[:50], "count": len(images)})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Performance ───────────────────────────────────────────

    async def get_performance(self) -> str:
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            metrics = await self.page.evaluate("""
                () => {
                    const perf = performance.getEntriesByType('navigation')[0];
                    if (!perf) return {};
                    return {
                        loadTime: Math.round(perf.loadEventEnd - perf.startTime),
                        domReady: Math.round(perf.domContentLoadedEventEnd - perf.startTime),
                        firstByte: Math.round(perf.responseStart - perf.startTime),
                        transferSize: perf.transferSize,
                        domElements: document.querySelectorAll('*').length,
                    };
                }
            """)
            return json.dumps({"performance": metrics})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Visual Highlighting (Debug) ───────────────────────────

    async def highlight(self, selector: str, color: str = "red", duration: int = 3000) -> str:
        """Visually highlight an element for debugging."""
        if not self.page:
            return json.dumps({"error": "No browser open"})
        try:
            await self.page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{selector}');
                    if (el) {{
                        const orig = el.style.outline;
                        el.style.outline = '3px solid {color}';
                        setTimeout(() => {{ el.style.outline = orig; }}, {duration});
                    }}
                }}
            """)
            return json.dumps({"success": True, "highlighted": selector, "color": color})
        except Exception as e:
            return json.dumps({"error": str(e)})

    # ── Wait ──────────────────────────────────────────────────

    async def wait_for(self, selector: Optional[str] = None, text: Optional[str] = None,
                       url_pattern: Optional[str] = None, timeout: int = 10000) -> str:
        """Wait for an element, text, or URL pattern."""
        if not self.page:
            return json.dumps({"error": "No browser open"})

        self.state.transition(PageState.WAITING, "wait_for")
        try:
            if selector:
                await self.page.wait_for_selector(selector, timeout=timeout)
                self.state.transition(PageState.INTERACTIVE, "found")
                return json.dumps({"success": True, "found": selector})
            elif text:
                await self.page.wait_for_selector(f'text="{text}"', timeout=timeout)
                self.state.transition(PageState.INTERACTIVE, "found")
                return json.dumps({"success": True, "found_text": text})
            elif url_pattern:
                await self.page.wait_for_url(f"**{url_pattern}**", timeout=timeout)
                self.state.transition(PageState.INTERACTIVE, "found")
                return json.dumps({"success": True, "url_matched": url_pattern})
            return json.dumps({"error": "Provide selector, text, or url_pattern"})
        except Exception as e:
            self.state.transition(PageState.ERROR, "wait_timeout")
            return json.dumps({"error": f"Wait timed out: {e}"})

    # ── Cleanup ───────────────────────────────────────────────

    async def close(self) -> str:
        """Close the browser and clean up."""
        # Save session if persistent
        if self.profile.persistent_cookies and self.profile.storage_dir and self.context:
            try:
                state = await self.context.storage_state()
                state_path = os.path.join(self.profile.storage_dir, "state.json")
                os.makedirs(self.profile.storage_dir, exist_ok=True)
                with open(state_path, "w") as f:
                    json.dump(state, f)
            except Exception:
                pass

        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        self.browser = None
        self.context = None
        self._playwright = None
        self.tabs = TabManager()
        self.state.transition(PageState.IDLE, "close")
        return json.dumps({"success": True, "message": "Browser closed"})


# ═══════════════════════════════════════════════════════════════
# Browser Tools (registered in the tool registry)
# ═══════════════════════════════════════════════════════════════

class BrowserLaunchTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_launch",
            description="Launch a browser instance with optional profile configuration.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("headless", "boolean", "Run in headless mode (default true)"),
                ToolParameter("browser_type", "string", "Browser engine", enum=["chromium", "firefox", "webkit"]),
                ToolParameter("stealth", "boolean", "Enable stealth mode to avoid bot detection"),
                ToolParameter("viewport_width", "integer", "Viewport width"),
                ToolParameter("viewport_height", "integer", "Viewport height"),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["browser", "launch"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        headless = arguments.get("headless", True)
        browser_type = arguments.get("browser_type", "chromium")
        if arguments.get("stealth"):
            self.engine.profile.stealth = True
        if arguments.get("viewport_width"):
            self.engine.profile.viewport_width = arguments["viewport_width"]
        if arguments.get("viewport_height"):
            self.engine.profile.viewport_height = arguments["viewport_height"]
        return await self.engine.launch(headless=headless, browser_type=browser_type)


class BrowserNavigateTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_navigate",
            description="Navigate the browser to a URL with auto-retry.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("url", "string", "URL to navigate to", required=True),
                ToolParameter("wait_until", "string", "When to consider navigation complete",
                    enum=["load", "domcontentloaded", "networkidle"]),
            ],
            tags=["browser", "navigate", "url"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        url = arguments["url"]
        wait_until = arguments.get("wait_until", "domcontentloaded")
        return await self.engine.navigate(url, wait_until=wait_until)


class BrowserClickTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_click",
            description="Click an element by CSS selector, text content, or ARIA role.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("selector", "string", "CSS selector"),
                ToolParameter("text", "string", "Text content to click"),
                ToolParameter("role", "string", "ARIA role (e.g. button, link)"),
                ToolParameter("nth", "integer", "Nth matching element (0-indexed)"),
            ],
            tags=["browser", "click", "interact"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.click_element(
            selector=arguments.get("selector"),
            text=arguments.get("text"),
            role=arguments.get("role"),
            nth=arguments.get("nth", 0),
        )


class BrowserTypeTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_type",
            description="Type text into a focused element or a specific input field.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("text", "string", "Text to type", required=True),
                ToolParameter("selector", "string", "CSS selector for the input field"),
                ToolParameter("delay", "integer", "Delay between keystrokes in ms"),
                ToolParameter("clear", "boolean", "Clear field before typing"),
            ],
            tags=["browser", "type", "input"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.type_text(
            text=arguments["text"],
            selector=arguments.get("selector"),
            delay=arguments.get("delay", 50),
            clear=arguments.get("clear", True),
        )


class BrowserFormFillTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_form_fill",
            description="Auto-fill a form using smart element detection. Maps labels to values.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("fields", "object", "Map of field labels to values (e.g. {'Email': 'test@example.com'})", required=True),
            ],
            tags=["browser", "form", "fill", "auto"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.auto_fill_form(arguments["fields"])


class BrowserScreenshotTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_screenshot",
            description="Take a screenshot of the page or a specific element.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("name", "string", "Screenshot filename"),
                ToolParameter("full_page", "boolean", "Capture the full scrollable page"),
                ToolParameter("selector", "string", "CSS selector for specific element"),
            ],
            tags=["browser", "screenshot", "capture"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.screenshot(
            name=arguments.get("name"),
            full_page=arguments.get("full_page", False),
            selector=arguments.get("selector"),
        )


class BrowserExtractTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_extract",
            description="Extract content from the page: text, HTML, links, images, accessibility tree.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("type", "string", "What to extract", required=True,
                    enum=["text", "html", "links", "images", "accessibility", "performance"]),
                ToolParameter("max_chars", "integer", "Maximum characters to return"),
            ],
            tags=["browser", "extract", "scrape"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        extract_type = arguments["type"]

        if extract_type == "text":
            return await self.engine.get_text(arguments.get("max_chars", 10000))
        elif extract_type == "html":
            return await self.engine.get_html(arguments.get("max_chars", 20000))
        elif extract_type == "links":
            return await self.engine.get_links()
        elif extract_type == "images":
            return await self.engine.get_images()
        elif extract_type == "accessibility":
            return await self.engine.get_accessibility_tree()
        elif extract_type == "performance":
            return await self.engine.get_performance()
        return json.dumps({"error": f"Unknown extract type: {extract_type}"})


class BrowserTabTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_tab",
            description="Manage browser tabs: new, close, switch, list.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("action", "string", "Tab action", required=True,
                    enum=["new", "close", "switch", "list"]),
                ToolParameter("tab_id", "string", "Tab ID (for close/switch)"),
                ToolParameter("url", "string", "URL to open in new tab"),
            ],
            tags=["browser", "tab", "multi-tab"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "new":
            return await self.engine.new_tab(arguments.get("url"))
        elif action == "close":
            return await self.engine.close_tab(arguments.get("tab_id"))
        elif action == "switch":
            tab_id = arguments.get("tab_id")
            if not tab_id:
                return json.dumps({"error": "tab_id required"})
            return await self.engine.switch_tab(tab_id)
        elif action == "list":
            return self.engine.list_tabs()
        return json.dumps({"error": f"Unknown action: {action}"})


class BrowserCookieTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_cookies",
            description="Manage browser cookies: get, set, clear, save/load session.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("action", "string", "Cookie action", required=True,
                    enum=["get", "set", "clear", "save_session", "load_session"]),
                ToolParameter("cookies", "array", "Cookies to set (list of {name, value, domain, path})"),
                ToolParameter("path", "string", "File path (for save/load session)"),
            ],
            tags=["browser", "cookies", "session"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "get":
            return await self.engine.get_cookies()
        elif action == "set":
            return await self.engine.set_cookies(arguments.get("cookies", []))
        elif action == "clear":
            return await self.engine.clear_cookies()
        elif action == "save_session":
            return await self.engine.save_session(arguments.get("path"))
        elif action == "load_session":
            path = arguments.get("path")
            if not path:
                return json.dumps({"error": "path required"})
            return await self.engine.load_session(path)
        return json.dumps({"error": f"Unknown action: {action}"})


class BrowserJSTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_js",
            description="Execute JavaScript code on the current page.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("code", "string", "JavaScript code to execute", required=True),
            ],
            permission=PermissionLevel.AUTHENTICATED,
            tags=["browser", "javascript", "execute"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.evaluate_js(arguments["code"])


class BrowserNetworkTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_network",
            description="Control network interception: enable/disable, block patterns, view summary.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("action", "string", "Action: enable, disable, summary", required=True,
                    enum=["enable", "disable", "summary"]),
                ToolParameter("block_patterns", "array", "URL patterns to block (regex)"),
                ToolParameter("block_types", "array", "Resource types to block (image, stylesheet, font, etc.)"),
            ],
            tags=["browser", "network", "intercept"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        action = arguments["action"]

        if action == "enable":
            return await self.engine.enable_interception(
                block_patterns=arguments.get("block_patterns"),
                block_types=arguments.get("block_types"),
            )
        elif action == "disable":
            return await self.engine.disable_interception()
        elif action == "summary":
            return self.engine.get_network_summary()
        return json.dumps({"error": f"Unknown action: {action}"})


class BrowserPDFTool(BaseTool):
    def __init__(self, engine: BrowserEngine):
        self.engine = engine

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="browser_pdf",
            description="Generate a PDF of the current page.",
            category=ToolCategory.WEB,
            parameters=[
                ToolParameter("path", "string", "Output PDF file path"),
            ],
            tags=["browser", "pdf", "export"],
        )

    async def execute(self, arguments: dict[str, Any], context: Optional[dict[str, Any]] = None) -> str:
        return await self.engine.generate_pdf(arguments.get("path"))


# ═══════════════════════════════════════════════════════════════
# Registration Helper
# ═══════════════════════════════════════════════════════════════

def register_browser_tools(registry: ToolRegistry, config: Any = None,
                           profile: Optional[BrowserProfile] = None) -> BrowserEngine:
    """Create a shared BrowserEngine and register all browser tools."""
    engine = BrowserEngine(config=config, profile=profile)

    tools = [
        BrowserLaunchTool(engine),
        BrowserNavigateTool(engine),
        BrowserClickTool(engine),
        BrowserTypeTool(engine),
        BrowserFormFillTool(engine),
        BrowserScreenshotTool(engine),
        BrowserExtractTool(engine),
        BrowserTabTool(engine),
        BrowserCookieTool(engine),
        BrowserJSTool(engine),
        BrowserNetworkTool(engine),
        BrowserPDFTool(engine),
    ]

    for tool in tools:
        registry.register(tool)

    return engine


# Need base64 import for screenshot_as_base64
import base64
