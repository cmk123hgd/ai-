"""
Camoufox MCP Server - AI浏览器逆向工程MCP服务

让AI通过MCP协议直接控制Camoufox浏览器，进行指纹分析、JS逆向、反检测测试等。
"""

import asyncio
import json
import base64
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Camoufox Browser")

# 全局浏览器实例
_browser = None
_page = None


async def get_browser():
    """获取或创建浏览器实例"""
    global _browser, _page
    if _browser is None:
        from camoufox.async_api import AsyncCamoufox
        from camoufox.addons import DefaultAddons
        _browser = await AsyncCamoufox(
            headless='virtual',
            exclude_addons=[DefaultAddons.UBO],
        ).__aenter__()
        _page = await _browser.new_page()
    return _browser, _page


# ============================================================
# 浏览器控制工具
# ============================================================

@mcp.tool()
async def browser_navigate(url: str, wait_until: str = "domcontentloaded") -> str:
    """导航到指定URL

    Args:
        url: 要访问的网址
        wait_until: 等待条件 (domcontentloaded/load/networkidle)
    """
    _, page = await get_browser()
    await page.goto(url, wait_until=wait_until, timeout=30000)
    title = await page.title()
    return json.dumps({"success": True, "title": title, "url": url}, ensure_ascii=False)


@mcp.tool()
async def browser_screenshot(full_page: bool = False) -> str:
    """截取当前页面截图，返回base64编码的PNG图片

    Args:
        full_page: 是否截取完整页面（包括滚动区域）
    """
    _, page = await get_browser()
    screenshot = await page.screenshot(full_page=full_page, type="png")
    b64 = base64.b64encode(screenshot).decode()
    return f"data:image/png;base64,{b64}"


@mcp.tool()
async def browser_close() -> str:
    """关闭浏览器"""
    global _browser, _page
    if _browser:
        await _browser.__aexit__(None, None, None)
        _browser = None
        _page = None
    return json.dumps({"success": True})


@mcp.tool()
async def browser_click(selector: str) -> str:
    """点击页面上的元素

    Args:
        selector: CSS选择器
    """
    _, page = await get_browser()
    await page.click(selector, timeout=5000)
    return json.dumps({"success": True, "selector": selector})


@mcp.tool()
async def browser_type(selector: str, text: str) -> str:
    """在输入框中输入文字

    Args:
        selector: CSS选择器
        text: 要输入的文字
    """
    _, page = await get_browser()
    await page.fill(selector, text, timeout=5000)
    return json.dumps({"success": True})


@mcp.tool()
async def browser_scroll(direction: str = "down", amount: int = 500) -> str:
    """滚动页面

    Args:
        direction: 滚动方向 (up/down)
        amount: 滚动像素数
    """
    _, page = await get_browser()
    delta = amount if direction == "down" else -amount
    await page.evaluate(f"window.scrollBy(0, {delta})")
    return json.dumps({"success": True})


# ============================================================
# 页面内容获取
# ============================================================

@mcp.tool()
async def page_content() -> str:
    """获取当前页面的完整HTML内容"""
    _, page = await get_browser()
    content = await page.content()
    # 截断过长的内容
    if len(content) > 500000:
        content = content[:500000] + "\n... [内容过长，已截断]"
    return content


@mcp.tool()
async def page_text() -> str:
    """获取当前页面的纯文本内容"""
    _, page = await get_browser()
    text = await page.evaluate("() => document.body.innerText")
    if len(text) > 200000:
        text = text[:200000] + "\n... [内容过长，已截断]"
    return text


@mcp.tool()
async def page_urls() -> str:
    """获取当前页面中所有的链接URL"""
    _, page = await get_browser()
    urls = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: a.textContent.trim().substring(0, 100),
            href: a.href
        }));
    }""")
    return json.dumps(urls, ensure_ascii=False)


# ============================================================
# JavaScript执行
# ============================================================

@mcp.tool()
async def js_execute(code: str) -> str:
    """在页面中执行JavaScript代码并返回结果

    Args:
        code: 要执行的JS代码（会自动包裹在async函数中）
    """
    _, page = await get_browser()
    try:
        result = await page.evaluate(code)
        return json.dumps({"success": True, "result": result}, ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def js_call_stack() -> str:
    """获取当前JS调用栈信息（用于逆向分析）"""
    _, page = await get_browser()
    result = await page.evaluate("""() => {
        const stack = new Error().stack;
        return stack || 'No stack available';
    }""")
    return result


@mcp.tool()
async def page_scripts() -> str:
    """获取页面中所有<script>标签的内容"""
    _, page = await get_browser()
    scripts = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script')).map((s, i) => ({
            index: i,
            src: s.src || '(inline)',
            type: s.type || 'text/javascript',
            size: s.textContent ? s.textContent.length : 0,
            preview: s.textContent ? s.textContent.substring(0, 500) : ''
        }));
    }""")
    return json.dumps(scripts, ensure_ascii=False)


@mcp.tool()
async def page_cookies() -> str:
    """获取当前页面的所有Cookie"""
    _, page = await get_browser()
    cookies = await page.context.cookies()
    return json.dumps(cookies, ensure_ascii=False)


# ============================================================
# 指纹采集与分析
# ============================================================

@mcp.tool()
async def fingerprint_collect() -> str:
    """采集当前浏览器的完整指纹信息（Navigator、Screen、Canvas、WebGL、Audio、Fonts等）"""
    _, page = await get_browser()
    result = await page.evaluate("""() => {
        const fp = {};

        // Navigator
        fp.navigator = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: Array.from(navigator.languages || []),
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory,
            maxTouchPoints: navigator.maxTouchPoints,
            webdriver: navigator.webdriver,
            cookieEnabled: navigator.cookieEnabled,
            pdfViewerEnabled: navigator.pdfViewerEnabled,
            vendor: navigator.vendor,
            appVersion: navigator.appVersion,
        };

        // Screen
        fp.screen = {
            width: screen.width,
            height: screen.height,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
            devicePixelRatio: window.devicePixelRatio,
        };

        // Canvas 2D
        try {
            const canvas = document.createElement('canvas');
            canvas.width = 200; canvas.height = 50;
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillStyle = '#f60';
            ctx.fillRect(125, 1, 62, 20);
            ctx.fillStyle = '#069';
            ctx.fillText('Camoufox MCP', 2, 15);
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.fillText('Camoufox MCP', 4, 17);
            fp.canvas = {
                dataUrl: canvas.toDataURL().substring(0, 200) + '...',
                hash: canvas.toDataURL().split('').reduce((a, b) => { a = ((a << 5) - a) + b.charCodeAt(0); return a & a; }, 0)
            };
        } catch(e) { fp.canvas = { error: e.message }; }

        // WebGL
        try {
            const canvas = document.createElement('canvas');
            const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
            if (gl) {
                const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
                fp.webgl = {
                    supported: true,
                    vendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : null,
                    renderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : null,
                    version: gl.getParameter(gl.VERSION),
                    shadingLangVersion: gl.getParameter(gl.SHADING_LANGUAGE_VERSION),
                    maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE),
                    maxRenderbufferSize: gl.getParameter(gl.MAX_RENDERBUFFER_SIZE),
                };
            } else {
                fp.webgl = { supported: false };
            }
        } catch(e) { fp.webgl = { error: e.message }; }

        // WebGL2
        try {
            const canvas = document.createElement('canvas');
            const gl2 = canvas.getContext('webgl2');
            if (gl2) {
                const debugInfo = gl2.getExtension('WEBGL_debug_renderer_info');
                fp.webgl2 = {
                    supported: true,
                    vendor: debugInfo ? gl2.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : null,
                    renderer: debugInfo ? gl2.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : null,
                    version: gl2.getParameter(gl2.VERSION),
                };
            } else {
                fp.webgl2 = { supported: false };
            }
        } catch(e) { fp.webgl2 = { error: e.message }; }

        // Audio
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const analyser = audioCtx.createAnalyser();
            const gain = audioCtx.createGain();
            const scriptProcessor = audioCtx.createScriptProcessor(4096, 1, 1);
            fp.audio = {
                sampleRate: audioCtx.sampleRate,
                state: audioCtx.state,
                baseLatency: audioCtx.baseLatency,
            };
            audioCtx.close();
        } catch(e) { fp.audio = { error: e.message }; }

        // Fonts (basic detection)
        try {
            const testFonts = ['Arial', 'Verdana', 'Helvetica', 'Times New Roman', 'Georgia',
                'Courier New', 'Comic Sans MS', 'Impact', 'Tahoma', 'Trebuchet MS',
                'Palatino', 'Lucida Console', 'Segoe UI', 'Calibri', 'Cambria'];
            const fontDetector = (font) => {
                const testStr = 'mmmmmmmmmmlli';
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                ctx.font = '72px monospace';
                const defaultWidth = ctx.measureText(testStr).width;
                ctx.font = `72px '${font}', monospace`;
                return ctx.measureText(testStr).width !== defaultWidth;
            };
            fp.fonts = testFonts.filter(f => fontDetector(f));
        } catch(e) { fp.fonts = { error: e.message }; }

        // WebRTC
        try {
            fp.webrtc = {
                supported: !!(window.RTCPeerConnection || window.webkitRTCPeerConnection),
            };
        } catch(e) { fp.webrtc = { error: e.message }; }

        // Storage
        fp.storage = {
            localStorage: !!window.localStorage,
            sessionStorage: !!window.sessionStorage,
            indexedDB: !!window.indexedDB,
        };

        // Features
        fp.features = {
            webRTC: !!window.RTCPeerConnection,
            serviceWorker: 'serviceWorker' in navigator,
            webWorker: !!window.Worker,
            sharedWorker: !!window.SharedWorker,
            webSocket: !!window.WebSocket,
            webGL: !!document.createElement('canvas').getContext('webgl'),
            webGL2: !!document.createElement('canvas').getContext('webgl2'),
            webAssembly: !!window.WebAssembly,
            notification: !!window.Notification,
            geolocation: !!navigator.geolocation,
            mediaDevices: !!(navigator.mediaDevices),
            speechSynthesis: !!window.speechSynthesis,
        };

        return fp;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def fingerprint_analyze() -> str:
    """分析当前浏览器指纹的一致性和风险评分"""
    fp = json.loads(await fingerprint_collect())

    issues = []
    score = 100  # 满分100

    # UA vs Platform一致性
    ua = fp['navigator'].get('userAgent', '')
    platform = fp['navigator'].get('platform', '')

    if 'Windows' in ua and platform != 'Win32':
        issues.append(f"UA声称Windows但platform={platform}")
        score -= 20
    elif 'Mac' in ua and platform != 'MacIntel':
        issues.append(f"UA声称Mac但platform={platform}")
        score -= 20
    elif 'Linux' in ua and 'Linux' not in platform:
        issues.append(f"UA声称Linux但platform={platform}")
        score -= 20

    # WebDriver检测
    if fp['navigator'].get('webdriver') == True:
        issues.append("navigator.webdriver = true（被检测为自动化）")
        score -= 30

    # WebGL检测
    if not fp.get('webgl', {}).get('supported'):
        issues.append("WebGL不可用（可能被禁用）")
        score -= 10

    # Canvas检测
    if 'error' in fp.get('canvas', {}):
        issues.append("Canvas指纹获取失败")
        score -= 5

    # Audio检测
    if 'error' in fp.get('audio', {}):
        issues.append("Audio指纹获取失败")
        score -= 5

    result = {
        "score": max(0, score),
        "risk_level": "低" if score >= 80 else "中" if score >= 60 else "高",
        "issues": issues,
        "fingerprint_summary": {
            "userAgent": ua,
            "platform": platform,
            "webgl": fp.get('webgl', {}).get('renderer', 'N/A'),
            "webgl_vendor": fp.get('webgl', {}).get('vendor', 'N/A'),
            "fonts_count": len(fp.get('fonts', [])),
            "screen": f"{fp['screen']['width']}x{fp['screen']['height']}",
            "hardwareConcurrency": fp['navigator'].get('hardwareConcurrency'),
        }
    }

    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 网络请求监控
# ============================================================

@mcp.tool()
async def network_requests() -> str:
    """获取页面加载过程中的所有网络请求"""
    _, page = await get_browser()
    # 通过performance API获取
    result = await page.evaluate("""() => {
        const entries = performance.getEntriesByType('resource');
        return entries.slice(-50).map(e => ({
            name: e.name,
            type: e.initiatorType,
            duration: Math.round(e.duration),
            size: e.transferSize || 0,
        }));
    }""")
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def intercept_requests(url_pattern: str = "*", action: str = "log") -> str:
    """拦截网络请求（用于分析API调用）

    Args:
        url_pattern: URL匹配模式（*匹配所有，或指定域名如 *api.example.com*）
        action: 操作类型 (log=只记录, block=拦截)
    """
    _, page = await get_browser()
    result = await page.evaluate(f"""(pattern, action) => {{
        window.__interceptedRequests = [];
        window.__interceptEnabled = true;

        const origFetch = window.fetch;
        window.fetch = async function(...args) {{
            const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
            const matches = pattern === '*' || url.includes(pattern.replace(/\\*/g, ''));
            if (matches) {{
                const entry = {{
                    url: url,
                    method: args[1]?.method || 'GET',
                    headers: {{}},
                    timestamp: Date.now(),
                }};
                if (args[1]?.headers) {{
                    if (args[1].headers instanceof Headers) {{
                        args[1].headers.forEach((v, k) => entry.headers[k] = v);
                    }} else {{
                        entry.headers = args[1].headers;
                    }}
                }}
                window.__interceptedRequests.push(entry);
                if (action === 'block') return new Response('', {{status: 403}});
            }}
            return origFetch.apply(this, args);
        }};

        const origXHR = XMLHttpRequest.prototype.open;
        XMLHttpRequest.prototype.open = function(method, url, ...rest) {{
            const matches = pattern === '*' || url.includes(pattern.replace(/\\*/g, ''));
            if (matches && window.__interceptEnabled) {{
                this.__interceptInfo = {{ url, method, timestamp: Date.now() }};
            }}
            return origXHR.call(this, method, url, ...rest);
        }};

        return {{ success: true, pattern, action, message: 'Request interceptor installed' }};
    }}""", url_pattern, action)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def get_intercepted_requests() -> str:
    """获取被拦截的网络请求列表"""
    _, page = await get_browser()
    result = await page.evaluate("""() => {
        return window.__interceptedRequests || [];
    }""")
    return json.dumps(result, ensure_ascii=False)


# ============================================================
# 反检测测试
# ============================================================

@mcp.tool()
async def detect_automation() -> str:
    """检测当前浏览器是否被识别为自动化/机器人"""
    _, page = await get_browser()
    result = await page.evaluate("""() => {
        const checks = {};

        // Navigator checks
        checks.webdriver = navigator.webdriver;
        checks.languages = navigator.languages?.length > 0;
        checks.plugins = navigator.plugins?.length >= 0;
        checks.permissions = !!navigator.permissions;

        // Window checks
        checks.chrome = !!window.chrome;
        checks.notifications = !!window.Notification;

        // Document checks
        checks.automationAttribute = !!document.documentElement.getAttribute('webdriver');
        checks.seleniumAttribute = !!document.documentElement.getAttribute('selenium');
        checks.driverAttribute = !!document.documentElement.getAttribute('driver');
        checks.cdpAttribute = !!document.documentElement.getAttribute('cdp');

        // Feature checks
        try {
            checks.permissionsQuery = navigator.permissions?.query?.({name: 'notifications'}) !== undefined;
        } catch(e) { checks.permissionsQuery = false; }

        // Headless checks
        checks.outerWidth = window.outerWidth;
        checks.outerHeight = window.outerHeight;
        checks.innerWidth = window.innerWidth;
        checks.innerHeight = window.innerHeight;

        // CDP check
        try {
            const err = new Error();
            checks.cdpInStack = err.stack?.includes('evaluate') || false;
        } catch(e) { checks.cdpInStack = false; }

        // User agent
        checks.userAgent = navigator.userAgent;
        checks.hasHeadless = /headless/i.test(navigator.userAgent);

        // Summary
        const risks = [];
        if (checks.webdriver) risks.push('navigator.webdriver = true');
        if (checks.automationAttribute) risks.push('webdriver attribute found');
        if (checks.seleniumAttribute) risks.push('selenium attribute found');
        if (checks.hasHeadless) risks.push('headless in user agent');
        if (checks.outerWidth === 0 && checks.outerHeight === 0) risks.push('zero window size (headless)');
        if (checks.cdpInStack) risks.push('CDP evaluate in stack trace');

        checks.riskCount = risks.length;
        checks.risks = risks;
        checks.overall = risks.length === 0 ? 'CLEAN' : risks.length <= 2 ? 'LOW_RISK' : 'HIGH_RISK';

        return checks;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    mcp.run()
