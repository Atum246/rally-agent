"""
🟣 Rally Agent — Browser Control Engine
Full browser automation — navigate, click, type, screenshot, extract, automate.
"""

import os
import asyncio
import json
import base64
import time
from typing import Optional, Any
from datetime import datetime

from cli.theme import Theme


class BrowserEngine:
    """Full browser automation — Playwright-powered"""

    def __init__(self, config):
        self.config = config
        self.browser = None
        self.page = None
        self.context = None
        self.history: list[dict] = []
        self.screenshots_dir = os.path.expanduser("~/.rally-agent/data/screenshots")
        os.makedirs(self.screenshots_dir, exist_ok=True)

    async def launch(self, headless: bool = True, browser_type: str = "chromium") -> str:
        """Launch a browser instance"""
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()

            if browser_type == "firefox":
                launcher = self._playwright.firefox
            elif browser_type == "webkit":
                launcher = self._playwright.webkit
            else:
                launcher = self._playwright.chromium

            self.browser = await launcher.launch(headless=headless)
            self.context = await self.browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            self.page = await self.context.new_page()
            Theme.success(f"🌐 Browser launched ({browser_type}, headless={headless})")
            return f"Browser launched: {browser_type}"

        except ImportError:
            Theme.error("Playwright not installed. Run: pip install playwright && playwright install")
            return "Error: Playwright not installed"
        except Exception as e:
            Theme.error(f"Browser launch failed: {e}")
            return f"Error: {e}"

    async def navigate(self, url: str) -> str:
        """Navigate to a URL"""
        if not self.page:
            await self.launch()

        try:
            response = await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
            title = await self.page.title()
            self.history.append({"url": url, "title": title, "timestamp": datetime.now().isoformat()})
            return f"📄 {title}\n🌐 {url}\n📊 Status: {response.status if response else 'unknown'}"
        except Exception as e:
            return f"Navigation error: {e}"

    async def screenshot(self, name: str = None, full_page: bool = False) -> str:
        """Take a screenshot"""
        if not self.page:
            return "No browser open"

        try:
            name = name or f"screenshot_{int(time.time())}"
            path = os.path.join(self.screenshots_dir, f"{name}.png")
            await self.page.screenshot(path=path, full_page=full_page)
            return f"📸 Screenshot saved: {path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def get_content(self, max_chars: int = 10000) -> str:
        """Get page text content"""
        if not self.page:
            return "No browser open"

        try:
            content = await self.page.inner_text("body")
            return content[:max_chars]
        except Exception as e:
            return f"Content error: {e}"

    async def get_html(self, max_chars: int = 20000) -> str:
        """Get page HTML"""
        if not self.page:
            return "No browser open"

        try:
            html = await self.page.content()
            return html[:max_chars]
        except Exception as e:
            return f"HTML error: {e}"

    async def get_links(self) -> list[dict]:
        """Get all links on the page"""
        if not self.page:
            return []

        try:
            links = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('a[href]')).map(a => ({
                    text: a.innerText.trim().substring(0, 100),
                    href: a.href,
                })).filter(l => l.text && l.href)
            """)
            return links[:100]
        except Exception:
            return []

    async def get_images(self) -> list[dict]:
        """Get all images on the page"""
        if not self.page:
            return []

        try:
            images = await self.page.evaluate("""
                () => Array.from(document.querySelectorAll('img')).map(img => ({
                    src: img.src,
                    alt: img.alt || '',
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                })).filter(i => i.src)
            """)
            return images[:50]
        except Exception:
            return []

    async def click(self, selector: str) -> str:
        """Click an element"""
        if not self.page:
            return "No browser open"

        try:
            await self.page.click(selector, timeout=5000)
            return f"✅ Clicked: {selector}"
        except Exception as e:
            return f"Click error: {e}"

    async def click_text(self, text: str) -> str:
        """Click element by text content"""
        if not self.page:
            return "No browser open"

        try:
            await self.page.click(f"text={text}", timeout=5000)
            return f"✅ Clicked text: {text}"
        except Exception as e:
            return f"Click error: {e}"

    async def type_text(self, selector: str, text: str, delay: int = 50) -> str:
        """Type text into an element"""
        if not self.page:
            return "No browser open"

        try:
            await self.page.fill(selector, text)
            return f"✅ Typed into {selector}: {text[:50]}..."
        except Exception:
            try:
                await self.page.click(selector)
                await self.page.type(selector, text, delay=delay)
                return f"✅ Typed into {selector}: {text[:50]}..."
            except Exception as e:
                return f"Type error: {e}"

    async def press_key(self, key: str) -> str:
        """Press a keyboard key"""
        if not self.page:
            return "No browser open"

        try:
            await self.page.keyboard.press(key)
            return f"✅ Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        """Scroll the page"""
        if not self.page:
            return "No browser open"

        try:
            if direction == "down":
                await self.page.mouse.wheel(0, amount)
            elif direction == "up":
                await self.page.mouse.wheel(0, -amount)
            elif direction == "right":
                await self.page.mouse.wheel(amount, 0)
            elif direction == "left":
                await self.page.mouse.wheel(-amount, 0)
            return f"✅ Scrolled {direction} {amount}px"
        except Exception as e:
            return f"Scroll error: {e}"

    async def wait_for(self, selector: str = None, text: str = None, timeout: int = 10000) -> str:
        """Wait for an element or text"""
        if not self.page:
            return "No browser open"

        try:
            if selector:
                await self.page.wait_for_selector(selector, timeout=timeout)
                return f"✅ Found element: {selector}"
            elif text:
                await self.page.wait_for_selector(f"text={text}", timeout=timeout)
                return f"✅ Found text: {text}"
            return "Specify selector or text"
        except Exception as e:
            return f"Wait timeout: {e}"

    async def extract_data(self, selector: str) -> list[str]:
        """Extract text from multiple elements"""
        if not self.page:
            return []

        try:
            data = await self.page.eval_on_selector_all(selector, "els => els.map(e => e.innerText.trim())")
            return data[:100]
        except Exception:
            return []

    async def fill_form(self, fields: dict) -> str:
        """Fill multiple form fields"""
        if not self.page:
            return "No browser open"

        results = []
        for selector, value in fields.items():
            try:
                await self.page.fill(selector, str(value))
                results.append(f"✅ {selector}: {value}")
            except Exception as e:
                results.append(f"❌ {selector}: {e}")

        return "\n".join(results)

    async def submit_form(self, selector: str = "form") -> str:
        """Submit a form"""
        if not self.page:
            return "No browser open"

        try:
            await self.page.evaluate(f'document.querySelector("{selector}").submit()')
            await self.page.wait_for_load_state("domcontentloaded")
            return "✅ Form submitted"
        except Exception as e:
            return f"Submit error: {e}"

    async def execute_js(self, code: str) -> Any:
        """Execute JavaScript on the page"""
        if not self.page:
            return "No browser open"

        try:
            result = await self.page.evaluate(code)
            return json.dumps(result, indent=2) if isinstance(result, (dict, list)) else str(result)
        except Exception as e:
            return f"JS error: {e}"

    async def pdf(self, path: str = None) -> str:
        """Generate PDF of the page"""
        if not self.page:
            return "No browser open"

        try:
            path = path or os.path.join(self.screenshots_dir, f"page_{int(time.time())}.pdf")
            await self.page.pdf(path=path)
            return f"📄 PDF saved: {path}"
        except Exception as e:
            return f"PDF error: {e}"

    async def get_cookies(self) -> list[dict]:
        """Get page cookies"""
        if not self.context:
            return []
        return await self.context.cookies()

    async def set_cookie(self, name: str, value: str, domain: str = None) -> str:
        """Set a cookie"""
        if not self.context:
            return "No browser context"

        cookie = {"name": name, "value": value, "url": domain or self.page.url}
        await self.context.add_cookies([cookie])
        return f"✅ Cookie set: {name}"

    async def new_tab(self) -> str:
        """Open a new tab"""
        if not self.context:
            return "No browser context"

        self.page = await self.context.new_page()
        return "✅ New tab opened"

    async def close_tab(self) -> str:
        """Close current tab"""
        if self.page:
            await self.page.close()
            self.page = None
            return "✅ Tab closed"
        return "No tab to close"

    async def get_performance(self) -> dict:
        """Get page performance metrics"""
        if not self.page:
            return {}

        try:
            metrics = await self.page.evaluate("""
                () => {
                    const perf = performance.getEntriesByType('navigation')[0];
                    return {
                        loadTime: Math.round(perf.loadEventEnd - perf.startTime),
                        domReady: Math.round(perf.domContentLoadedEventEnd - perf.startTime),
                        firstPaint: Math.round(perf.responseEnd - perf.startTime),
                        transferSize: perf.transferSize,
                    };
                }
            """)
            return metrics
        except Exception:
            return {}

    async def intercept_requests(self, pattern: str = "**") -> list[dict]:
        """Intercept network requests"""
        requests = []

        async def handle_request(request):
            requests.append({
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
            })

        if self.page:
            self.page.on("request", handle_request)
            await asyncio.sleep(2)
            self.page.remove_listener("request", handle_request)

        return requests[:50]

    async def close(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
            self.browser = None
            self.page = None
            self.context = None
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()
        Theme.info("Browser closed")

    def get_history(self) -> list[dict]:
        return self.history[-20:]


class BrowserCommands:
    """Browser commands for the CLI"""

    def __init__(self, config):
        self.engine = BrowserEngine(config)

    async def execute(self, command: str, args: str) -> str:
        cmd_map = {
            "launch": self._launch,
            "open": self._open,
            "go": self._open,
            "screenshot": self._screenshot,
            "ss": self._screenshot,
            "content": self._content,
            "text": self._content,
            "html": self._html,
            "links": self._links,
            "images": self._images,
            "click": self._click,
            "type": self._type,
            "scroll": self._scroll,
            "wait": self._wait,
            "js": self._js,
            "pdf": self._pdf,
            "cookies": self._cookies,
            "tab": self._new_tab,
            "close": self._close,
            "history": self._history,
            "fill": self._fill,
            "extract": self._extract,
            "perf": self._perf,
        }

        handler = cmd_map.get(command)
        if handler:
            return await handler(args)
        return f"Unknown browser command: {command}. Available: {', '.join(cmd_map.keys())}"

    async def _launch(self, args: str) -> str:
        headless = "headed" not in args.lower()
        browser_type = "chromium"
        if "firefox" in args.lower():
            browser_type = "firefox"
        elif "webkit" in args.lower():
            browser_type = "webkit"
        return await self.engine.launch(headless=headless, browser_type=browser_type)

    async def _open(self, url: str) -> str:
        return await self.engine.navigate(url)

    async def _screenshot(self, args: str) -> str:
        name = args.strip() or None
        full_page = "full" in args.lower()
        return await self.engine.screenshot(name, full_page)

    async def _content(self, args: str) -> str:
        return await self.engine.get_content()

    async def _html(self, args: str) -> str:
        return await self.engine.get_html()

    async def _links(self, args: str) -> str:
        links = await self.engine.get_links()
        return "\n".join([f"🔗 {l['text'][:60]} → {l['href']}" for l in links[:20]]) or "No links found"

    async def _images(self, args: str) -> str:
        images = await self.engine.get_images()
        return "\n".join([f"🖼️ {i['alt'] or 'no alt'} → {i['src'][:80]}" for i in images[:20]]) or "No images found"

    async def _click(self, selector: str) -> str:
        return await self.engine.click(selector.strip())

    async def _type(self, args: str) -> str:
        parts = args.split(" ", 1)
        if len(parts) < 2:
            return "Usage: type <selector> <text>"
        return await self.engine.type_text(parts[0], parts[1])

    async def _scroll(self, args: str) -> str:
        direction = args.strip() or "down"
        return await self.engine.scroll(direction)

    async def _wait(self, args: str) -> str:
        return await self.engine.wait_for(selector=args.strip())

    async def _js(self, code: str) -> str:
        return await self.engine.execute_js(code)

    async def _pdf(self, args: str) -> str:
        return await self.engine.pdf()

    async def _cookies(self, args: str) -> str:
        cookies = await self.engine.get_cookies()
        return "\n".join([f"🍪 {c['name']}={c['value'][:30]}" for c in cookies]) or "No cookies"

    async def _new_tab(self, args: str) -> str:
        return await self.engine.new_tab()

    async def _close(self, args: str) -> str:
        return await self.engine.close()

    async def _history(self, args: str) -> str:
        history = self.engine.get_history()
        return "\n".join([f"📄 {h['title'][:50]} → {h['url']}" for h in history]) or "No history"

    async def _fill(self, args: str) -> str:
        try:
            fields = json.loads(args)
            return await self.engine.fill_form(fields)
        except Exception:
            return "Usage: fill '{\"selector\": \"value\"}'"

    async def _extract(self, selector: str) -> str:
        data = await self.engine.extract_data(selector.strip())
        return "\n".join(data[:20]) or "No data found"

    async def _perf(self, args: str) -> str:
        metrics = await self.engine.get_performance()
        return json.dumps(metrics, indent=2) if metrics else "No performance data"
