"""Local MCP browser server. Configure using BROWSER_MCP_* environment variables."""
import os
import asyncio
import time
from pathlib import Path
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.utilities.types import Image
from playwright.async_api import async_playwright
from .chrome import default_profile

@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        await close_browser()

mcp = FastMCP('Liberty Browser', lifespan=lifespan)

context = None
pw = None
attached_browser = None
current = 0
browser_lock = asyncio.Lock()

async def _ensure_cdp_chrome(port: int) -> None:
    """Start the dedicated Chrome profile on demand and wait for its CDP port."""
    from .chrome import launch_chrome
    from .session import _verify_chrome

    profile = default_profile()
    if _verify_chrome(port, profile):
        return

    try:
        launch_chrome('attach', profile=profile, port=port)
    except Exception as exc:
        raise RuntimeError(
            'Liberty Browser could not start its dedicated Chrome session. '
            'Close Chrome windows using the Liberty Browser profile, then retry.'
        ) from exc

    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection('127.0.0.1', port), timeout=0.4
            )
            writer.close()
            await writer.wait_closed()
            if _verify_chrome(port, profile):
                return
        except (OSError, asyncio.TimeoutError):
            pass
        await asyncio.sleep(0.2)
    raise RuntimeError(
        f'Chrome did not open the Liberty Browser CDP port 127.0.0.1:{port} within 20 seconds.'
    )

def on_context_closed(closed):
    global context
    if context is closed:
        context = None

async def browser():
    global context, pw, attached_browser
    async with browser_lock:
        if context is None:
            if pw is not None:
                await pw.stop()
            attached_browser = None
            pw = await async_playwright().start()
            try:
                endpoint = os.environ.get('BROWSER_MCP_CDP_URL')
                if endpoint:
                    parsed = urlparse(endpoint)
                    if parsed.scheme not in ('http', 'ws') or parsed.hostname not in ('127.0.0.1', 'localhost', '::1'):
                        raise ValueError('CDP endpoint must be a local HTTP or WebSocket address')
                    if os.name == 'nt' and os.environ.get('BROWSER_MCP_CDP_PORT'):
                        # Recover automatically if Chrome was closed or is still
                        # starting, then verify the expected profile before attaching.
                        port = int(os.environ['BROWSER_MCP_CDP_PORT'])
                        last_error = None
                        for attempt in range(3):
                            await _ensure_cdp_chrome(port)
                            try:
                                attached_browser = await pw.chromium.connect_over_cdp(endpoint, timeout=5000)
                                break
                            except Exception as exc:
                                last_error = exc
                                if attempt == 2:
                                    raise
                                await asyncio.sleep(0.4 * (attempt + 1))
                        if attached_browser is None:
                            raise RuntimeError('Could not attach to the Liberty Browser Chrome session.') from last_error
                    else:
                        attached_browser = await pw.chromium.connect_over_cdp(endpoint, timeout=10000)
                    if not attached_browser.contexts:
                        raise RuntimeError('No default browser context available at CDP endpoint')
                    context = attached_browser.contexts[0]
                else:
                    engine = os.environ.get('BROWSER_MCP_ENGINE', 'chromium')
                    if engine not in ('chromium', 'firefox'):
                        raise ValueError('BROWSER_MCP_ENGINE must be chromium or firefox')
                    default_profile_name = 'profile' if engine == 'chromium' else 'profile-firefox'
                    profile = Path(os.environ.get('BROWSER_MCP_PROFILE', str(default_profile().parent / default_profile_name))).expanduser().resolve()
                    profile.mkdir(parents=True, exist_ok=True)
                    channel = os.environ.get('BROWSER_MCP_CHANNEL') or None
                    if engine == 'firefox' and channel:
                        raise ValueError('BROWSER_MCP_CHANNEL is supported only with chromium')
                    browser_type = pw.chromium if engine == 'chromium' else pw.firefox
                    options = {'headless': os.environ.get('BROWSER_MCP_HEADLESS','0') == '1'}
                    if channel:
                        options['channel'] = channel
                    context = await browser_type.launch_persistent_context(str(profile), **options)
            except Exception:
                await pw.stop()
                pw = None
                attached_browser = None
                raise
            context.on('close', on_context_closed)
            context.set_default_timeout(int(os.environ.get('BROWSER_MCP_TIMEOUT_MS','10000')))
        return context

async def page():
    global current
    ctx = await browser()
    if not ctx.pages: await ctx.new_page()
    if current >= len(ctx.pages): current = 0
    return ctx.pages[current]

@mcp.tool()
async def navigate(url: str) -> dict:
    """Navigate to an HTTP(S) URL. A human may complete any verification in the visible browser."""
    if not url.startswith(('http://','https://')): raise ValueError('Only HTTP(S) URLs are allowed')
    p=await page(); response=await p.goto(url,wait_until='domcontentloaded'); return {'url':p.url,'title':await p.title(),'status':response.status if response else None}

@mcp.tool()
async def history(action: str) -> dict:
    """Navigate browser history: back, forward, or reload."""
    p=await page()
    if action == 'back': response=await p.go_back(wait_until='domcontentloaded')
    elif action == 'forward': response=await p.go_forward(wait_until='domcontentloaded')
    elif action == 'reload': response=await p.reload(wait_until='domcontentloaded')
    else: raise ValueError('action must be back, forward, or reload')
    return {'url':p.url, 'status':response.status if response else None, 'title':await p.title()}

@mcp.tool()
async def tabs(action: str = 'list', index: int = 0) -> dict:
    """List, create, select, or close tabs; index refers to the current tab list."""
    global current
    ctx=await browser()
    if action=='new': await ctx.new_page(); current=len(ctx.pages)-1
    elif action in ('select','close'):
        if index < 0 or index >= len(ctx.pages): raise ValueError('Invalid tab index')
        if action=='close': await ctx.pages[index].close(); current=0
        else: current=index
    elif action!='list': raise ValueError('action must be list, new, select, or close')
    return {'current':current,'tabs':[{'index':i,'url':p.url,'title':await p.title()} for i,p in enumerate(ctx.pages)]}

@mcp.tool()
async def inspect_page() -> dict:
    """Return page text and visible interactive elements with CSS selectors and accessible labels."""
    p=await page()
    elements=await p.locator('a,button,input,select,textarea,[role=button]').evaluate_all('''els => els.filter(e => e.getClientRects().length).slice(0,200).map(e => ({tag:e.tagName, id:e.id, name:e.getAttribute('name'), role:e.getAttribute('role'), type:e.getAttribute('type'), label:e.getAttribute('aria-label') || e.innerText || e.placeholder || '', selector:e.id && document.querySelectorAll('#'+CSS.escape(e.id)).length === 1 ? '#'+CSS.escape(e.id) : (() => {let a=[], n=e; while(n && n.nodeType===1 && n!==document.documentElement){let i=1, s=n; while(s=s.previousElementSibling) if(s.tagName===n.tagName)i++; a.unshift(n.tagName.toLowerCase()+':nth-of-type('+i+')');n=n.parentElement;} return 'html > '+a.join(' > ');})(), href:e.getAttribute('href')}))''')
    return {'url':p.url,'title':await p.title(),'text':(await p.locator('body').inner_text())[:30000], 'elements':elements}

@mcp.tool()
async def click(selector: str) -> dict:
    """Click a CSS selector or Playwright selector."""
    p=await page(); await p.locator(selector).first.click(); return {'url':p.url,'title':await p.title()}

@mcp.tool()
async def scroll(x: int = 0, y: int = 600) -> dict:
    """Scroll the current page by the given CSS pixel offsets."""
    if abs(x) > 10000 or abs(y) > 10000:
        raise ValueError('Scroll offset is too large')
    p = await page()
    await p.mouse.wheel(x, y)
    await p.wait_for_timeout(150)
    return {'url': p.url, 'scroll': await p.evaluate('({x: window.scrollX, y: window.scrollY})')}

@mcp.tool()
async def media_info() -> dict:
    """Inspect video and audio playback state without exposing media source URLs."""
    p = await page()
    media = await p.locator('video,audio').evaluate_all('''els => els.map((e, i) => ({
        index:i, type:e.tagName.toLowerCase(), paused:e.paused, currentTime:e.currentTime,
        duration:Number.isFinite(e.duration) ? e.duration : null,
        readyState:e.readyState, muted:e.muted, ended:e.ended
    }))''')
    return {'url': p.url, 'media': media}

@mcp.tool()
async def canvas_info() -> dict:
    """List canvases with dimensions, visibility, and rendered position on the current page."""
    p = await page()
    canvases = await p.locator('canvas').evaluate_all('''els => els.map((e, i) => {
        const r = e.getBoundingClientRect();
        return {index:i, id:e.id, width:e.width, height:e.height,
                x:r.x, y:r.y, display_width:r.width, display_height:r.height,
                visible:r.width > 0 && r.height > 0};
    })''')
    return {'url': p.url, 'canvases': canvases}

@mcp.tool()
async def canvas_click(index: int, x: float, y: float) -> dict:
    """Click a canvas at CSS pixel coordinates relative to its upper-left corner."""
    p = await page()
    elements = p.locator('canvas')
    if index < 0 or index >= await elements.count():
        raise ValueError('Invalid canvas index')
    canvas = elements.nth(index)
    box = await canvas.bounding_box()
    if not box or x < 0 or y < 0 or x >= box['width'] or y >= box['height']:
        raise ValueError('Canvas is not visible or coordinates are outside its bounds')
    await canvas.click(position={'x': x, 'y': y})
    return {'url': p.url, 'clicked': {'index': index, 'x': x, 'y': y}}

@mcp.tool()
async def fill(selector: str, value: str) -> dict:
    """Fill an editable field; values are not logged by this server."""
    p=await page(); await p.locator(selector).first.fill(value); return {'ok':True}

@mcp.tool()
async def inspect_frames() -> dict:
    """List frame URLs and titles for diagnosing embedded content and challenges."""
    p = await page()
    return {'frames': [{'url': f.url, 'name': f.name} for f in p.frames]}

@mcp.tool()
async def page_diagnostics() -> dict:
    """Identify common visible sign-in rejection and challenge indicators; do not solve challenges."""
    p = await page()
    body = (await p.locator('body').inner_text()).lower()
    frames = [f.url.lower() for f in p.frames]
    checks = [
        ('browser_rejected', ('esse navegador ou app pode não ser seguro',
                              'este navegador ou app pode não ser seguro',
                              'this browser or app may not be secure')),
        ('captcha_frame', ('recaptcha/api', 'hcaptcha.com', 'challenges.cloudflare.com')),
    ]
    indicators = []
    for kind, patterns in checks:
        source = frames if kind == 'captcha_frame' else [body]
        if any(pattern in value for pattern in patterns for value in source):
            indicators.append(kind)
    return {'url': p.url, 'indicators': indicators,
            'note': 'Indicators are heuristic, not proof of successful authentication or a complete security assessment.'}

@mcp.tool()
async def frame_inspect(frame_selector: str) -> dict:
    """Read visible text and checkbox state in an iframe."""
    p = await page(); frame = p.frame_locator(frame_selector)
    text = await frame.locator('body').inner_text()
    boxes = await frame.locator('[role=checkbox],input[type=checkbox]').evaluate_all("els => els.map(e => ({id:e.id, checked:e.getAttribute('aria-checked') ?? e.checked}))")
    return {'text': text[:10000], 'checkboxes': boxes}

@mcp.tool()
async def frame_click(frame_selector: str, selector: str) -> dict:
    """Click an element in an iframe selected by CSS; challenges may require the user's participation."""
    p = await page()
    await p.frame_locator(frame_selector).locator(selector).first.click()
    return {'url': p.url}

@mcp.tool()
async def press(selector: str, key: str) -> dict:
    """Press a key on an element, for example Enter or Tab."""
    p=await page(); await p.locator(selector).first.press(key); return {'url':p.url}

@mcp.tool()
async def select_option(selector: str, value: str) -> dict:
    """Select an option by value."""
    p=await page(); return {'selected':await p.locator(selector).first.select_option(value)}

@mcp.tool()
async def wait_for(selector: str, timeout_ms: int = 30000) -> dict:
    """Wait for an element after a manual login or other user action; timeout is bounded."""
    if not 1 <= timeout_ms <= 300000: raise ValueError('timeout_ms must be between 1 and 300000')
    p=await page(); await p.locator(selector).first.wait_for(state='visible', timeout=timeout_ms); return {'url':p.url, 'visible':True}

@mcp.tool()
async def screenshot(path: str = 'screenshot.png') -> dict:
    """Save a screenshot locally at the given path."""
    p=await page(); target=Path(path).resolve(); target.parent.mkdir(parents=True,exist_ok=True); await p.screenshot(path=str(target),full_page=True); return {'path':str(target)}

@mcp.tool()
async def screenshot_image(full_page: bool = False) -> Image:
    """Return the current browser screenshot as MCP image content for visual inspection."""
    p = await page()
    png = await p.screenshot(full_page=full_page, type='png')
    return Image(data=png, format='png')

@mcp.tool()
async def close_browser() -> dict:
    """Close the owned browser, or disconnect from an externally managed browser."""
    global context, pw, current, attached_browser
    async with browser_lock:
        if attached_browser:
            await attached_browser.close()
            attached_browser = None
            context = None
        elif context: await context.close(); context=None
        if pw: await pw.stop(); pw=None
        current=0
    return {'ok':True}

def main() -> None:
    """Start the Liberty Browser MCP server over stdio."""
    mcp.run(transport='stdio')


if __name__ == '__main__':
    main()
