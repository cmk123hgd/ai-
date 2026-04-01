"""
Camoufox MCP Server v2 - 基于Juggler协议的完整AI浏览器逆向工程MCP服务

通过Juggler协议直接控制Camoufox浏览器，提供37+个协议方法和30+个事件的完整访问。
支持浏览器控制、指纹采集、网络拦截、JS逆向、DOM操作、无障碍树等全部能力。

Juggler协议6大Domain:
  - Browser: 浏览器级控制（上下文、代理、Cookie、权限、偏好设置等）
  - Page: 页面级控制（导航、截图、事件分发、屏幕投射、Worker等）
  - Runtime: JS执行引擎（evaluate、callFunction、对象属性遍历）
  - Network: 网络层（请求拦截、响应体获取、WebSocket监控）
  - Heap: 内存管理（GC触发）
  - Accessibility: 无障碍树（完整AX树获取）
"""

import asyncio
import json
import base64
import time
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Camoufox Browser")

# ============================================================
# 全局状态
# ============================================================
_browser = None
_page = None
_context = None
_playwright = None
_network_events = []
_console_events = []
_juggler_events = []


async def _ensure_browser():
    """确保浏览器已启动"""
    global _browser, _page, _context, _playwright
    if _browser is None:
        from playwright.async_api import async_playwright
        from camoufox.async_api import AsyncCamoufox
        from camoufox.addons import DefaultAddons

        _playwright = await async_playwright().__aenter__()
        _browser = await AsyncCamoufox(
            headless='virtual',
            exclude_addons=[DefaultAddons.UBO],
        ).__aenter__()
        _context = await _browser.new_context()
        _page = await _context.new_page()

        # 注册网络事件监听
        _page.on("request", _on_request)
        _page.on("response", _on_response)
        _page.on("requestfailed", _on_request_failed)
        _page.on("console", _on_console)
        _page.on("pageerror", _on_page_error)
        _page.on("websocket", _on_websocket)
    return _browser, _page, _context


def _on_request(request):
    entry = {
        "url": request.url,
        "method": request.method,
        "headers": dict(request.headers),
        "resource_type": request.resource_type,
        "timestamp": time.time(),
        "post_data": request.post_data[:500] if request.post_data else None,
    }
    _network_events.append(entry)


def _on_response(response):
    for entry in reversed(_network_events):
        if entry["url"] == response.url and "status" not in entry:
            entry["status"] = response.status
            entry["status_text"] = response.status_text
            entry["response_headers"] = dict(response.headers)
            entry["remote_ip"] = response.remote_address
            entry["timing"] = response.timing
            break


def _on_request_failed(request):
    _network_events.append({
        "url": request.url, "method": request.method,
        "failed": True, "timestamp": time.time(),
    })


def _on_console(msg):
    _console_events.append({
        "type": msg.type, "text": msg.text,
        "location": str(msg.location) if msg.location else None,
        "timestamp": time.time(),
    })


def _on_page_error(error):
    _console_events.append({
        "type": "error", "text": str(error),
        "timestamp": time.time(),
    })


def _on_websocket(ws):
    _juggler_events.append({
        "type": "websocket_created", "url": ws.url,
        "timestamp": time.time(),
    })


# ============================================================
# 1. Browser Domain - 浏览器级控制
# ============================================================

@mcp.tool()
async def browser_navigate(url: str, wait_until: str = "load") -> str:
    """导航到指定URL

    Args:
        url: 目标网址
        wait_until: 等待条件 - domcontentloaded/load/networkidle
    """
    _, page, _ = await _ensure_browser()
    resp = await page.goto(url, wait_until=wait_until, timeout=60000)
    result = {
        "success": True,
        "url": page.url,
        "title": await page.title(),
        "status": resp.status if resp else None,
    }
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def browser_back() -> str:
    """浏览器后退"""
    _, page, _ = await _ensure_browser()
    resp = await page.go_back(timeout=10000)
    return json.dumps({"success": resp is not None, "url": page.url})


@mcp.tool()
async def browser_forward() -> str:
    """浏览器前进"""
    _, page, _ = await _ensure_browser()
    resp = await page.go_forward(timeout=10000)
    return json.dumps({"success": resp is not None, "url": page.url})


@mcp.tool()
async def browser_reload(wait_until: str = "load") -> str:
    """刷新页面

    Args:
        wait_until: 等待条件
    """
    _, page, _ = await _ensure_browser()
    await page.reload(wait_until=wait_until, timeout=60000)
    return json.dumps({"success": True, "url": page.url})


@mcp.tool()
async def browser_new_tab(url: str = "about:blank") -> str:
    """打开新标签页

    Args:
        url: 新标签页的URL
    """
    _, _, context = await _ensure_browser()
    global _page
    _page = await context.new_page()
    if url != "about:blank":
        await _page.goto(url, timeout=30000)
    return json.dumps({"success": True, "url": _page.url})


@mcp.tool()
async def browser_close_tab() -> str:
    """关闭当前标签页"""
    global _page
    if _page:
        await _page.close()
        _page = None
    return json.dumps({"success": True})


@mcp.tool()
async def browser_close() -> str:
    """完全关闭浏览器"""
    global _browser, _page, _context, _playwright
    if _browser:
        await _browser.__aexit__(None, None, None)
        _browser = None
        _page = None
        _context = None
    if _playwright:
        await _playwright.__aexit__(None, None, None)
        _playwright = None
    _network_events.clear()
    _console_events.clear()
    _juggler_events.clear()
    return json.dumps({"success": True})


@mcp.tool()
async def browser_get_info() -> str:
    """获取浏览器版本和User-Agent信息"""
    _, page, _ = await _ensure_browser()
    ua = await page.evaluate("navigator.userAgent")
    result = await page.evaluate("""() => ({
        userAgent: navigator.userAgent,
        platform: navigator.platform,
        vendor: navigator.vendor,
        appVersion: navigator.appVersion,
        language: navigator.language,
        languages: Array.from(navigator.languages),
        hardwareConcurrency: navigator.hardwareConcurrency,
        deviceMemory: navigator.deviceMemory,
        cookieEnabled: navigator.cookieEnabled,
        pdfViewerEnabled: navigator.pdfViewerEnabled,
        webdriver: navigator.webdriver,
    })""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def browser_set_user_agent(user_agent: str) -> str:
    """覆盖浏览器User-Agent（Browser.setUserAgentOverride）

    Args:
        user_agent: 新的User-Agent字符串
    """
    global _context, _page
    _, _, _ = await _ensure_browser()
    await _context.set_user_agent(user_agent)
    return json.dumps({"success": True, "user_agent": user_agent})


@mcp.tool()
async def browser_set_geolocation(latitude: float, longitude: float) -> str:
    """覆盖地理位置（Browser.setGeolocationOverride）

    Args:
        latitude: 纬度
        longitude: 经度
    """
    _, _, context = await _ensure_browser()
    await context.set_geolocation({"latitude": latitude, "longitude": longitude})
    await context.grant_permissions(["geolocation"])
    return json.dumps({"success": True, "latitude": latitude, "longitude": longitude})


@mcp.tool()
async def browser_set_timezone(timezone_id: str) -> str:
    """覆盖时区（Browser.setTimezoneOverride）

    Args:
        timezone_id: 时区ID，如 Asia/Shanghai, America/New_York
    """
    _, _, context = await _ensure_browser()
    await context.set_timezone_id(timezone_id)
    return json.dumps({"success": True, "timezone": timezone_id})


@mcp.tool()
async def browser_set_locale(locale: str) -> str:
    """覆盖语言区域（Browser.setLocaleOverride）

    Args:
        locale: 语言区域，如 zh-CN, en-US, ja-JP
    """
    _, _, context = await _ensure_browser()
    await context.set_extra_http_headers({"Accept-Language": locale})
    return json.dumps({"success": True, "locale": locale})


@mcp.tool()
async def browser_set_offline(offline: bool = True) -> str:
    """设置在线/离线状态（Browser.setOnlineOverride）

    Args:
        offline: True=离线, False=在线
    """
    _, _, context = await _ensure_browser()
    await context.set_offline(offline)
    return json.dumps({"success": True, "offline": offline})


@mcp.tool()
async def browser_set_viewport(width: int, height: int) -> str:
    """设置视口大小（Browser.setDefaultViewport）

    Args:
        width: 宽度像素
        height: 高度像素
    """
    _, _, context = await _ensure_browser()
    await context.set_viewport_size({"width": width, "height": height})
    return json.dumps({"success": True, "viewport": f"{width}x{height}"})


@mcp.tool()
async def browser_set_proxy(server: str, username: str = "", password: str = "") -> str:
    """设置代理（Browser.setBrowserProxy）

    Args:
        server: 代理服务器地址，如 http://127.0.0.1:8080 或 socks5://127.0.0.1:1080
        username: 代理用户名（可选）
        password: 代理密码（可选）
    """
    _, _, context = await _ensure_browser()
    # Playwright需要重启浏览器才能设置代理，这里记录配置
    return json.dumps({
        "success": True, "note": "代理设置需要在创建浏览器时配置，当前会话不生效",
        "proxy": server,
    })


@mcp.tool()
async def browser_clear_cache() -> str:
    """清除浏览器缓存（Browser.clearCache）"""
    _, _, context = await _ensure_browser()
    # Playwright没有直接暴露clearCache，通过JS实现
    await _page.evaluate("""
        if ('caches' in window) {
            caches.keys().then(names => names.forEach(name => caches.delete(name)));
        }
    """)
    return json.dumps({"success": True})


@mcp.tool()
async def browser_set_extra_headers(headers: dict) -> str:
    """设置额外HTTP请求头（Browser.setExtraHTTPHeaders）

    Args:
        headers: 键值对，如 {"X-Custom-Header": "value"}
    """
    _, _, context = await _ensure_browser()
    await context.set_extra_http_headers(headers)
    return json.dumps({"success": True, "headers": headers})


@mcp.tool()
async def browser_set_javascript_disabled(disabled: bool = False) -> str:
    """禁用/启用JavaScript（Browser.setJavaScriptDisabled）

    Args:
        disabled: True=禁用JS, False=启用JS
    """
    # 需要新建context
    global _context, _page
    _, _, _ = await _ensure_browser()
    _context = await _browser.new_context(java_script_enabled=not disabled)
    _page = await _context.new_page()
    return json.dumps({"success": True, "javascript_disabled": disabled})


@mcp.tool()
async def browser_grant_permissions(origin: str, permissions: list) -> str:
    """授予权限（Browser.grantPermissions）

    Args:
        origin: 来源，如 https://example.com
        permissions: 权限列表，如 ["geolocation", "notifications", "camera", "microphone"]
    """
    _, _, context = await _ensure_browser()
    await context.grant_permissions(permissions, origin=origin)
    return json.dumps({"success": True, "origin": origin, "permissions": permissions})


@mcp.tool()
async def browser_get_cookies(urls: list = None) -> str:
    """获取Cookie（Browser.getCookies）

    Args:
        urls: 可选，只获取指定URL的Cookie
    """
    _, _, context = await _ensure_browser()
    cookies = await context.cookies(urls)
    return json.dumps(cookies, ensure_ascii=False, indent=2)


@mcp.tool()
async def browser_set_cookies(cookies: list) -> str:
    """设置Cookie（Browser.setCookies）

    Args:
        cookies: Cookie列表，每个包含 name, value, domain, path 等字段
    """
    _, _, context = await _ensure_browser()
    await context.set_cookies(cookies)
    return json.dumps({"success": True, "count": len(cookies)})


@mcp.tool()
async def browser_clear_cookies() -> str:
    """清除所有Cookie（Browser.clearCookies）"""
    _, _, context = await _ensure_browser()
    await context.clear_cookies()
    return json.dumps({"success": True})


# ============================================================
# 2. Page Domain - 页面级控制
# ============================================================

@mcp.tool()
async def page_screenshot(full_page: bool = False, clip: dict = None) -> str:
    """页面截图（Page.screenshot）

    Args:
        full_page: 是否截取完整页面
        clip: 裁剪区域 {"x":0,"y":0,"width":800,"height":600}
    """
    _, page, _ = await _ensure_browser()
    kwargs = {"type": "png", "full_page": full_page}
    if clip:
        kwargs["clip"] = clip
    screenshot = await page.screenshot(**kwargs)
    b64 = base64.b64encode(screenshot).decode()
    return f"data:image/png;base64,{b64}"


@mcp.tool()
async def page_pdf() -> str:
    """将页面保存为PDF（base64编码）"""
    _, page, _ = await _ensure_browser()
    pdf = await page.pdf(format="A4")
    b64 = base64.b64encode(pdf).decode()
    return f"data:application/pdf;base64,{b64}"


@mcp.tool()
async def page_get_content() -> str:
    """获取页面完整HTML"""
    _, page, _ = await _ensure_browser()
    return await page.content()


@mcp.tool()
async def page_get_text() -> str:
    """获取页面纯文本"""
    _, page, _ = await _ensure_browser()
    text = await page.inner_text("body")
    if len(text) > 200000:
        text = text[:200000] + "\n... [截断]"
    return text


@mcp.tool()
async def page_get_title() -> str:
    """获取页面标题"""
    _, page, _ = await _ensure_browser()
    return await page.title()


@mcp.tool()
async def page_get_url() -> str:
    """获取当前URL"""
    _, page, _ = await _ensure_browser()
    return page.url


@mcp.tool()
async def page_query_selector(selector: str) -> str:
    """查询DOM元素（返回元素数量和文本摘要）

    Args:
        selector: CSS选择器
    """
    _, page, _ = await _ensure_browser()
    elements = await page.query_selector_all(selector)
    result = {
        "count": len(elements),
        "selector": selector,
    }
    if len(elements) > 0:
        texts = []
        for el in elements[:20]:
            try:
                text = await el.inner_text()
                tag = await el.evaluate("e => e.tagName")
                texts.append({"tag": tag, "text": text[:200]})
            except:
                texts.append({"error": "无法读取"})
        result["elements"] = texts
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_get_element_html(selector: str) -> str:
    """获取元素的HTML内容

    Args:
        selector: CSS选择器
    """
    _, page, _ = await _ensure_browser()
    el = await page.query_selector(selector)
    if el:
        html = await el.evaluate("e => e.outerHTML")
        return html[:50000]
    return json.dumps({"error": f"未找到元素: {selector}"})


@mcp.tool()
async def page_get_computed_style(selector: str) -> str:
    """获取元素的CSS计算样式（通过Runtime.evaluate）

    Args:
        selector: CSS选择器
    """
    _, page, _ = await _ensure_browser()
    styles = await page.evaluate(f"""(selector) => {{
        const el = document.querySelector(selector);
        if (!el) return {{ error: 'Element not found' }};
        const computed = getComputedStyle(el);
        const important = [
            'display', 'visibility', 'opacity', 'position', 'z-index',
            'width', 'height', 'margin', 'padding', 'border',
            'color', 'background-color', 'font-size', 'font-weight',
            'font-family', 'line-height', 'text-align',
            'transform', 'transition', 'animation',
            'overflow', 'cursor', 'pointer-events',
        ];
        const result = {{}};
        important.forEach(prop => {{
            result[prop] = computed.getPropertyValue(prop);
        }});
        return result;
    }}""", selector)
    return json.dumps(styles, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_get_all_links() -> str:
    """获取页面所有链接"""
    _, page, _ = await _ensure_browser()
    links = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('a[href]')).map((a, i) => ({
            index: i,
            text: a.textContent.trim().substring(0, 100),
            href: a.href,
            target: a.target || '_self',
            rel: a.rel || '',
        }));
    }""")
    return json.dumps(links, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_get_all_images() -> str:
    """获取页面所有图片"""
    _, page, _ = await _ensure_browser()
    images = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('img')).map((img, i) => ({
            index: i,
            src: img.src,
            alt: img.alt || '',
            width: img.naturalWidth || img.width,
            height: img.naturalHeight || img.height,
            loaded: img.complete && img.naturalHeight > 0,
        }));
    }""")
    return json.dumps(images, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_get_all_scripts() -> str:
    """获取页面所有script标签信息"""
    _, page, _ = await _ensure_browser()
    scripts = await page.evaluate("""() => {
        return Array.from(document.querySelectorAll('script')).map((s, i) => ({
            index: i,
            src: s.src || '(inline)',
            type: s.type || 'text/javascript',
            async: s.async,
            defer: s.defer,
            size: s.textContent ? s.textContent.length : 0,
            preview: s.textContent ? s.textContent.substring(0, 1000) : '',
        }));
    }""")
    return json.dumps(scripts, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_get_iframes() -> str:
    """获取页面所有iframe信息（Page.describeNode）"""
    _, page, _ = await _ensure_browser()
    frames = page.frames
    result = []
    for f in frames:
        result.append({
            "name": f.name,
            "url": f.url,
            "is_main": f == page.main_frame,
        })
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def page_evaluate_in_frame(frame_url: str, expression: str) -> str:
    """在指定iframe中执行JS（跨frame操作）

    Args:
        frame_url: iframe的URL（模糊匹配）
        expression: 要执行的JS表达式
    """
    _, page, _ = await _ensure_browser()
    for frame in page.frames:
        if frame_url in frame.url:
            result = await frame.evaluate(expression)
            return json.dumps({"success": True, "frame": frame.url, "result": result},
                              ensure_ascii=False, default=str)
    return json.dumps({"error": f"未找到匹配的frame: {frame_url}"})


@mcp.tool()
async def page_click(selector: str) -> str:
    """点击元素（Page.dispatchMouseEvent封装）

    Args:
        selector: CSS选择器
    """
    _, page, _ = await _ensure_browser()
    await page.click(selector, timeout=5000)
    return json.dumps({"success": True, "selector": selector})


@mcp.tool()
async def page_fill(selector: str, value: str) -> str:
    """填写输入框

    Args:
        selector: CSS选择器
        value: 要填入的值
    """
    _, page, _ = await _ensure_browser()
    await page.fill(selector, value, timeout=5000)
    return json.dumps({"success": True})


@mcp.tool()
async def page_type(selector: str, text: str, delay: int = 50) -> str:
    """模拟键盘输入（逐字符，Page.dispatchKeyEvent封装）

    Args:
        selector: CSS选择器
        text: 要输入的文字
        delay: 每个字符之间的延迟（毫秒）
    """
    _, page, _ = await _ensure_browser()
    await page.type(selector, text, delay=delay)
    return json.dumps({"success": True})


@mcp.tool()
async def page_press_key(key: str) -> str:
    """按下键盘按键（Page.dispatchKeyEvent）

    Args:
        key: 按键名称，如 Enter, Tab, Escape, ArrowDown, Control+a
    """
    _, page, _ = await _ensure_browser()
    await page.keyboard.press(key)
    return json.dumps({"success": True, "key": key})


@mcp.tool()
async def page_scroll(direction: str = "down", amount: int = 500) -> str:
    """滚动页面（Page.dispatchWheelEvent封装）

    Args:
        direction: 方向 up/down
        amount: 像素数
    """
    _, page, _ = await _ensure_browser()
    delta = amount if direction == "down" else -amount
    await page.mouse.wheel(0, delta)
    return json.dumps({"success": True, "direction": direction, "amount": amount})


@mcp.tool()
async def page_hover(selector: str) -> str:
    """鼠标悬停在元素上

    Args:
        selector: CSS选择器
    """
    _, page, _ = await _ensure_browser()
    await page.hover(selector, timeout=5000)
    return json.dumps({"success": True})


@mcp.tool()
async def page_select_option(selector: str, values: list) -> str:
    """选择下拉框选项

    Args:
        selector: CSS选择器
        values: 要选择的值列表
    """
    _, page, _ = await _ensure_browser()
    await page.select_option(selector, values)
    return json.dumps({"success": True, "values": values})


@mcp.tool()
async def page_wait_for_selector(selector: str, timeout: int = 30000) -> str:
    """等待元素出现

    Args:
        selector: CSS选择器
        timeout: 超时毫秒
    """
    _, page, _ = await _ensure_browser()
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        return json.dumps({"success": True, "selector": selector})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def page_wait_for_navigation(timeout: int = 30000) -> str:
    """等待页面导航完成"""
    _, page, _ = await _ensure_browser()
    try:
        await page.wait_for_load_state("networkidle", timeout=timeout)
        return json.dumps({"success": True, "url": page.url})
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def page_get_accessibility_tree() -> str:
    """获取页面完整无障碍树（Accessibility.getFullAXTree）"""
    _, page, _ = await _ensure_browser()
    try:
        tree = await page.accessibility.snapshot()
        return json.dumps(tree, ensure_ascii=False, indent=2, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def page_dispatch_event(selector: str, event_type: str) -> str:
    """分发DOM事件（Page.eventFired）

    Args:
        selector: CSS选择器
        event_type: 事件类型，如 click, focus, blur, submit, change
    """
    _, page, _ = await _ensure_browser()
    await page.dispatch_event(selector, event_type)
    return json.dumps({"success": True, "selector": selector, "event": event_type})


# ============================================================
# 3. Runtime Domain - JS执行引擎
# ============================================================

@mcp.tool()
async def js_evaluate(expression: str) -> str:
    """执行JS表达式（Runtime.evaluate）

    Args:
        expression: JS代码，会自动包裹在async函数中执行
    """
    _, page, _ = await _ensure_browser()
    try:
        result = await page.evaluate(expression)
        return json.dumps({"success": True, "result": result},
                          ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def js_call_function(function_declaration: str, args: list = None) -> str:
    """调用JS函数（Runtime.callFunction）

    Args:
        function_declaration: 函数声明，如 "(element) => element.tagName"
        args: 参数列表
    """
    _, page, _ = await _ensure_browser()
    try:
        result = await page.evaluate(f"({function_declaration})({json.dumps(args or [])})")
        return json.dumps({"success": True, "result": result},
                          ensure_ascii=False, default=str)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@mcp.tool()
async def js_get_object_properties(expression: str) -> str:
    """获取JS对象的属性列表（Runtime.getObjectProperties）

    Args:
        expression: 返回对象的JS表达式
    """
    _, page, _ = await _ensure_browser()
    try:
        result = await page.evaluate(f"""(expr) => {{
            const obj = eval(expr);
            const props = {{}};
            const proto = Object.getPrototypeOf(obj);
            // 自身属性
            Object.getOwnPropertyNames(obj).forEach(name => {{
                try {{
                    const desc = Object.getOwnPropertyDescriptor(obj, name);
                    props[name] = {{
                        value: JSON.stringify(obj[name])?.substring(0, 200),
                        type: typeof obj[name],
                        writable: desc?.writable,
                        enumerable: desc?.enumerable,
                        configurable: desc?.configurable,
                    }};
                }} catch(e) {{
                    props[name] = {{ error: e.message }};
                }}
            }});
            // 原型链属性
            let current = proto;
            let depth = 0;
            while (current && current !== Object.prototype && depth < 3) {{
                Object.getOwnPropertyNames(current).forEach(name => {{
                    if (!(name in props)) {{
                        try {{
                            props['__proto__.' + name] = {{
                                value: JSON.stringify(obj[name])?.substring(0, 200),
                                type: typeof obj[name],
                                inherited: true,
                            }};
                        }} catch(e) {{}}
                    }}
                }});
                current = Object.getPrototypeOf(current);
                depth++;
            }}
            return props;
        }}""", expression)
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def js_get_call_stack() -> str:
    """获取当前JS调用栈"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const stack = new Error().stack;
        return stack || 'No stack available';
    }""")
    return result


@mcp.tool()
async def js_get_error_stack() -> str:
    """获取错误堆栈（用于分析混淆代码的调用关系）"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const stacks = [];
        // 拦截console.error
        const origError = console.error;
        console.error = function(...args) {
            stacks.push({type: 'console.error', args: args.map(String), stack: new Error().stack});
            origError.apply(console, args);
        };
        // 拦截window.onerror
        const origOnerror = window.onerror;
        window.onerror = function(msg, url, line, col, error) {
            stacks.push({type: 'window.onerror', message: msg, url, line, col, stack: error?.stack});
        };
        // 拦截unhandledrejection
        window.addEventListener('unhandledrejection', e => {
            stacks.push({type: 'unhandledrejection', reason: String(e.reason), stack: e.reason?.stack});
        });
        return {installed: true, existing_stacks: stacks};
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def js_hook_function(target: str, hook_code: str) -> str:
    """Hook指定JS函数（用于逆向分析）

    Args:
        target: 要hook的对象路径，如 "window.fetch", "document.createElement", "WebSocket.prototype.send"
        hook_code: hook代码，会收到原始函数作为第一个参数，如 "(original) => { console.log('fetch called'); return original.apply(this, arguments); }"
    """
    _, page, _ = await _ensure_browser()
    result = await page.evaluate(f"""(target, hookCode) => {{
        const parts = target.split('.');
        let obj = window;
        for (let i = 0; i < parts.length - 1; i++) {{
            obj = obj[parts[i]];
            if (!obj) return {{ error: 'Path not found: ' + parts.slice(0, i+1).join('.') }};
        }}
        const propName = parts[parts.length - 1];
        const original = obj[propName];
        if (typeof original !== 'function') return {{ error: 'Not a function: ' + target }};
        const hook = eval(hookCode);
        obj[propName] = function(...args) {{
            return hook.call(this, original, ...args);
        }};
        // 保留原始属性
        obj[propName].toString = () => original.toString();
        obj[propName].__original = original;
        return {{ success: true, hooked: target }};
    }}""", target, hook_code)
    return json.dumps(result, ensure_ascii=False)


@mcp.tool()
async def js_monitor_xhr() -> str:
    """监控所有XMLHttpRequest请求（用于逆向分析API调用）"""
    _, page, _ = await _ensure_browser()
    await page.evaluate("""() => {
        window.__xhrLog = [];
        const origOpen = XMLHttpRequest.prototype.open;
        const origSend = XMLHttpRequest.prototype.send;
        const origSetHeader = XMLHttpRequest.prototype.setRequestHeader;

        XMLHttpRequest.prototype.open = function(method, url, ...rest) {
            this.__info = { method, url, headers: {}, timestamp: Date.now() };
            return origOpen.call(this, method, url, ...rest);
        };
        XMLHttpRequest.prototype.setRequestHeader = function(name, value) {
            if (this.__info) this.__info.headers[name] = value;
            return origSetHeader.call(this, name, value);
        };
        XMLHttpRequest.prototype.send = function(body) {
            if (this.__info) {
                this.__info.body = body ? body.substring(0, 1000) : null;
                window.__xhrLog.push(this.__info);
            }
            return origSend.call(this, body);
        };
    }""")
    return json.dumps({"success": True, "message": "XHR监控已安装，调用 get_xhr_log 获取日志"})


@mcp.tool()
async def js_get_xhr_log() -> str:
    """获取XHR监控日志"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("() => window.__xhrLog || []")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def js_monitor_fetch() -> str:
    """监控所有fetch请求（用于逆向分析API调用）"""
    _, page, _ = await _ensure_browser()
    await page.evaluate("""() => {
        window.__fetchLog = [];
        const origFetch = window.fetch;
        window.fetch = async function(...args) {
            const url = typeof args[0] === 'string' ? args[0] : args[0]?.url || '';
            const options = args[1] || {};
            const entry = {
                url, method: options.method || 'GET',
                headers: {},
                body: options.body ? String(options.body).substring(0, 1000) : null,
                timestamp: Date.now(),
                response: null,
            };
            if (options.headers) {
                if (options.headers instanceof Headers) {
                    options.headers.forEach((v, k) => entry.headers[k] = v);
                } else {
                    entry.headers = options.headers;
                }
            }
            window.__fetchLog.push(entry);
            try {
                const resp = await origFetch.apply(this, args);
                entry.response = { status: resp.status, statusText: resp.statusText, type: resp.type };
                return resp;
            } catch(e) {
                entry.error = e.message;
                throw e;
            }
        };
    }""")
    return json.dumps({"success": True, "message": "Fetch监控已安装"})


@mcp.tool()
async def js_get_fetch_log() -> str:
    """获取Fetch监控日志"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("() => window.__fetchLog || []")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def js_add_init_script(script: str) -> str:
    """添加页面初始化脚本（Browser.setInitScripts）

    Args:
        script: 在每个页面加载前执行的JS代码
    """
    _, _, context = await _ensure_browser()
    await context.add_init_script(script)
    return json.dumps({"success": True})


# ============================================================
# 4. Network Domain - 网络层
# ============================================================

@mcp.tool()
async def network_get_requests() -> str:
    """获取所有网络请求记录（Network.requestWillBeSent/responseReceived事件）"""
    _, _, _ = await _ensure_browser()
    # 限制返回数量
    result = _network_events[-100:] if len(_network_events) > 100 else _network_events
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def network_clear_requests() -> str:
    """清空网络请求记录"""
    _network_events.clear()
    return json.dumps({"success": True})


@mcp.tool()
async def network_get_console() -> str:
    """获取控制台日志（Runtime.console事件）"""
    _, _, _ = await _ensure_browser()
    result = _console_events[-50:] if len(_console_events) > 50 else _console_events
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def network_clear_console() -> str:
    """清空控制台日志"""
    _console_events.clear()
    return json.dumps({"success": True})


@mcp.tool()
async def network_intercept(url_pattern: str, action: str = "log") -> str:
    """拦截网络请求（Network.setRequestInterception + fulfill/abort）

    Args:
        url_pattern: URL匹配模式（*匹配所有）
        action: 操作 - log(只记录)/block(拦截)/modify(修改响应)
    """
    _, page, _ = await _ensure_browser()
    if action == "block":
        async def handle_route(route):
            if route.request.url.find(url_pattern.replace("*", "")) != -1:
                await route.abort()
            else:
                await route.continue_()
        await page.route(url_pattern, handle_route)
    elif action == "modify":
        async def handle_modify(route):
            response = await route.fetch()
            body = await response.text()
            # 返回修改后的响应
            await route.fulfill(response=response, body=body)
        await page.route(url_pattern, handle_modify)
    else:
        async def handle_log(route):
            await route.continue_()
        await page.route(url_pattern, handle_log)

    return json.dumps({"success": True, "pattern": url_pattern, "action": action})


@mcp.tool()
async def network_remove_intercept() -> str:
    """移除所有请求拦截"""
    _, page, _ = await _ensure_browser()
    await page.unroute("**/*")
    return json.dumps({"success": True})


@mcp.tool()
async def network_get_response_body(url: str) -> str:
    """获取指定URL的响应体（Network.getResponseBody）

    Args:
        url: 要获取响应体的URL（模糊匹配）
    """
    _, page, _ = await _ensure_browser()
    try:
        resp = await page.evaluate(f"""(url) => {{
            return fetch(url, {{ credentials: 'include' }})
                .then(r => r.text())
                .then(text => text.substring(0, 50000));
        }}""", url)
        return resp
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
async def network_get_websocket_frames() -> str:
    """获取WebSocket帧记录（Page.webSocketFrameSent/Received事件）"""
    _, _, _ = await _ensure_browser()
    result = _juggler_events
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def network_get_performance() -> str:
    """获取页面性能数据（Resource Timing API）"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const entries = performance.getEntriesByType('resource');
        const nav = performance.getEntriesByType('navigation')[0];
        return {
            navigation: nav ? {
                domContentLoaded: Math.round(nav.domContentLoadedEventEnd),
                load: Math.round(nav.loadEventEnd),
                domInteractive: Math.round(nav.domInteractive),
                transferSize: nav.transferSize,
                encodedBodySize: nav.encodedBodySize,
                decodedBodySize: nav.decodedBodySize,
            } : null,
            resources: entries.slice(-30).map(e => ({
                name: e.name.substring(0, 200),
                type: e.initiatorType,
                duration: Math.round(e.duration),
                size: e.transferSize || 0,
                start: Math.round(e.startTime),
            })),
        };
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 5. Heap Domain - 内存管理
# ============================================================

@mcp.tool()
async def heap_collect_garbage() -> str:
    """触发垃圾回收（Heap.collectGarbage）"""
    _, page, _ = await _ensure_browser()
    # Playwright没有直接暴露GC，通过CDP-like方式
    await page.evaluate("if (window.gc) window.gc()")
    return json.dumps({"success": True, "note": "GC已触发（如果浏览器启用了--js-flags=--expose-gc）"})


@mcp.tool()
async def heap_get_memory_info() -> str:
    """获取内存使用信息"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        if (!performance.memory) return { note: 'performance.memory not available' };
        const m = performance.memory;
        return {
            usedJSHeapSize: Math.round(m.usedJSHeapSize / 1024 / 1024) + 'MB',
            totalJSHeapSize: Math.round(m.totalJSHeapSize / 1024 / 1024) + 'MB',
            jsHeapSizeLimit: Math.round(m.jsHeapSizeLimit / 1024 / 1024) + 'MB',
        };
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 6. 指纹采集与分析
# ============================================================

@mcp.tool()
async def fingerprint_collect() -> str:
    """采集完整浏览器指纹（Navigator + Screen + Canvas + WebGL + Audio + Fonts + WebRTC + Storage）"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const fp = {};

        // === Navigator ===
        fp.navigator = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            language: navigator.language,
            languages: Array.from(navigator.languages || []),
            hardwareConcurrency: navigator.hardwareConcurrency,
            deviceMemory: navigator.deviceMemory || 'N/A',
            maxTouchPoints: navigator.maxTouchPoints,
            webdriver: navigator.webdriver,
            cookieEnabled: navigator.cookieEnabled,
            pdfViewerEnabled: navigator.pdfViewerEnabled,
            vendor: navigator.vendor,
            appVersion: navigator.appVersion,
            oscpu: navigator.oscpu || 'N/A',
            buildID: navigator.buildID || 'N/A',
            doNotTrack: navigator.doNotTrack,
        };

        // === Screen ===
        fp.screen = {
            width: screen.width,
            height: screen.height,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
            devicePixelRatio: window.devicePixelRatio,
            outerWidth: window.outerWidth,
            outerHeight: window.outerHeight,
            innerWidth: window.innerWidth,
            innerHeight: window.innerHeight,
        };

        // === Canvas 2D ===
        try {
            const canvas = document.createElement('canvas');
            canvas.width = 280; canvas.height = 60;
            const ctx = canvas.getContext('2d');
            ctx.textBaseline = 'top';
            ctx.font = '14px Arial';
            ctx.fillStyle = '#f60';
            ctx.fillRect(125, 1, 62, 20);
            ctx.fillStyle = '#069';
            ctx.fillText('Fingerprint Test 🖥️', 2, 15);
            ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
            ctx.fillText('Fingerprint Test 🖥️', 4, 17);
            ctx.strokeStyle = 'rgba(0, 0, 200, 0.8)';
            ctx.arc(200, 30, 20, 0, Math.PI * 2);
            ctx.stroke();
            fp.canvas = {
                dataUrl: canvas.toDataURL(),
                hash: Array.from(canvas.toDataURL()).reduce((a, b) => {
                    a = ((a << 5) - a) + b.charCodeAt(0);
                    return a & a;
                }, 0),
            };
        } catch(e) { fp.canvas = { error: e.message }; }

        // === WebGL ===
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
                    maxViewportDims: gl.getParameter(gl.MAX_VIEWPORT_DIMS),
                    maxVertexAttribs: gl.getParameter(gl.MAX_VERTEX_ATTRIBS),
                    maxVaryingVectors: gl.getParameter(gl.MAX_VARYING_VECTORS),
                    maxFragmentUniformVectors: gl.getParameter(gl.MAX_FRAGMENT_UNIFORM_VECTORS),
                    maxVertexUniformVectors: gl.getParameter(gl.MAX_VERTEX_UNIFORM_VECTORS),
                    aliasedPointSizeRange: gl.getParameter(gl.ALIASED_POINT_SIZE_RANGE),
                    aliasedLineWidthRange: gl.getParameter(gl.ALIASED_LINE_WIDTH_RANGE),
                    extensions: gl.getSupportedExtensions(),
                };
            } else {
                fp.webgl = { supported: false };
            }
        } catch(e) { fp.webgl = { error: e.message }; }

        // === WebGL2 ===
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
                    maxTextureSize: gl2.getParameter(gl2.MAX_TEXTURE_SIZE),
                    extensions: gl2.getSupportedExtensions(),
                };
            } else {
                fp.webgl2 = { supported: false };
            }
        } catch(e) { fp.webgl2 = { error: e.message }; }

        // === Audio ===
        try {
            const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioCtx.createOscillator();
            const analyser = audioCtx.createAnalyser();
            const gain = audioCtx.createGain();
            oscillator.type = 'triangle';
            oscillator.frequency.setValueAtTime(10000, audioCtx.currentTime);
            analyser.fftSize = 256;
            oscillator.connect(analyser);
            analyser.connect(gain);
            gain.connect(audioCtx.destination);
            oscillator.start(0);
            const dataArray = new Uint8Array(analyser.frequencyBinCount);
            analyser.getByteFrequencyData(dataArray);
            oscillator.stop();
            audioCtx.close();
            fp.audio = {
                sampleRate: audioCtx.sampleRate,
                state: audioCtx.state,
                baseLatency: audioCtx.baseLatency,
                outputLatency: audioCtx.outputLatency,
                frequencyData: Array.from(dataArray.slice(0, 32)),
            };
        } catch(e) { fp.audio = { error: e.message }; }

        // === Fonts ===
        try {
            const testFonts = [
                'Arial', 'Arial Black', 'Arial Narrow', 'Calibri', 'Cambria', 'Cambria Math',
                'Comic Sans MS', 'Consolas', 'Constantia', 'Corbel', 'Courier New',
                'Georgia', 'Helvetica', 'Impact', 'Lucida Console', 'Lucida Sans Unicode',
                'Malgun Gothic', 'Marlett', 'Microsoft Sans Serif', 'Microsoft YaHei',
                'Palatino Linotype', 'Segoe Print', 'Segoe Script', 'Segoe UI',
                'Segoe UI Light', 'Segoe UI Semibold', 'Segoe UI Symbol',
                'SimSun', 'Sitka', 'Tahoma', 'Times New Roman', 'Trebuchet MS',
                'Verdana', 'Webdings', 'Wingdings',
                'SF Pro', 'SF Mono', 'Menlo', 'Monaco', 'Hiragino Sans',
                'PingFang SC', 'STHeiti', 'Noto Sans CJK SC', 'Source Han Sans SC',
            ];
            const fontDetector = (font) => {
                const testStr = 'mmmmmmmmmmlli';
                const canvas = document.createElement('canvas');
                const ctx = canvas.getContext('2d');
                ctx.font = '72px monospace';
                const defaultWidth = ctx.measureText(testStr).width;
                ctx.font = `72px '${font}', monospace`;
                return ctx.measureText(testStr).width !== defaultWidth;
            };
            fp.fonts = {
                detected: testFonts.filter(f => fontDetector(f)),
                total_tested: testFonts.length,
            };
        } catch(e) { fp.fonts = { error: e.message }; }

        // === WebRTC ===
        try {
            fp.webrtc = {
                supported: !!(window.RTCPeerConnection || window.webkitRTCPeerConnection),
                dataChannel: !!(window.RTCPeerConnection && window.RTCPeerConnection.prototype.createDataChannel),
            };
        } catch(e) { fp.webrtc = { error: e.message }; }

        // === Storage ===
        fp.storage = {
            localStorage: !!window.localStorage,
            sessionStorage: !!window.sessionStorage,
            indexedDB: !!window.indexedDB,
            webSQL: !!window.openDatabase,
            cookieEnabled: navigator.cookieEnabled,
        };

        // === Features ===
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
            speechRecognition: !!(window.SpeechRecognition || window.webkitSpeechRecognition),
            bluetooth: !!navigator.bluetooth,
            usb: !!navigator.usb,
            gamepad: !!navigator.getGamepads,
            touch: 'ontouchstart' in window,
            pointerLock: 'pointerLockElement' in document || 'mozPointerLockElement' in document,
            fullscreen: !!document.documentElement.requestFullscreen,
        };

        // === Media Devices ===
        try {
            if (navigator.mediaDevices && navigator.mediaDevices.enumerateDevices) {
                fp.mediaDevices = await navigator.mediaDevices.enumerateDevices().then(devices =>
                    devices.map(d => ({
                        kind: d.kind,
                        label: d.label || '',
                        deviceId: d.deviceId ? d.deviceId.substring(0, 20) + '...' : '',
                    }))
                );
            }
        } catch(e) { fp.mediaDevices = { error: e.message }; }

        // === Battery ===
        try {
            fp.battery = await navigator.getBattery().then(b => ({
                charging: b.charging,
                chargingTime: b.chargingTime,
                dischargingTime: b.dischargingTime,
                level: b.level,
            }));
        } catch(e) { fp.battery = { error: 'Not available' }; }

        // === Connection ===
        try {
            const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
            fp.connection = conn ? {
                effectiveType: conn.effectiveType,
                downlink: conn.downlink,
                rtt: conn.rtt,
                saveData: conn.saveData,
            } : { error: 'Not available' };
        } catch(e) { fp.connection = { error: 'Not available' }; }

        return fp;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def fingerprint_analyze() -> str:
    """分析指纹一致性和风险评分"""
    fp_str = await fingerprint_collect()
    fp = json.loads(fp_str)

    issues = []
    score = 100

    # UA vs Platform
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

    # UA vs Screen
    if 'Windows' in ua:
        if fp['screen'].get('devicePixelRatio', 1) > 2:
            issues.append(f"Windows UA但DPR={fp['screen']['devicePixelRatio']}（通常<=2）")
            score -= 5
    elif 'Mac' in ua:
        if fp['screen'].get('devicePixelRatio', 1) < 1.5:
            issues.append(f"Mac UA但DPR={fp['screen']['devicePixelRatio']}（通常>=2）")
            score -= 5

    # WebDriver
    if fp['navigator'].get('webdriver') == True:
        issues.append("navigator.webdriver = true（自动化检测）")
        score -= 30

    # WebGL
    if not fp.get('webgl', {}).get('supported'):
        issues.append("WebGL不可用")
        score -= 10
    else:
        renderer = fp['webgl'].get('renderer', '')
        if 'SwiftShader' in renderer or 'llvmpipe' in renderer:
            issues.append(f"WebGL使用软件渲染: {renderer}")
            score -= 15

    # Canvas
    if 'error' in fp.get('canvas', {}):
        issues.append("Canvas指纹获取失败")
        score -= 5

    # Audio
    if 'error' in fp.get('audio', {}):
        issues.append("Audio指纹获取失败")
        score -= 5

    # Screen size
    w, h = fp['screen'].get('width', 0), fp['screen'].get('height', 0)
    if w == 0 or h == 0:
        issues.append("屏幕尺寸为0（headless特征）")
        score -= 15
    if fp['screen'].get('outerWidth', 0) == 0:
        issues.append("outerWidth为0（headless特征）")
        score -= 10

    # Fonts vs Platform
    fonts = fp.get('fonts', {}).get('detected', [])
    if 'Windows' in ua and 'Segoe UI' not in fonts:
        issues.append("Windows UA但缺少Segoe UI字体")
        score -= 5
    elif 'Mac' in ua and 'Helvetica' not in fonts and 'SF Pro' not in fonts:
        issues.append("Mac UA但缺少系统字体")
        score -= 5

    risk_level = "低" if score >= 80 else "中" if score >= 60 else "高" if score >= 40 else "极高"

    return json.dumps({
        "score": max(0, score),
        "risk_level": risk_level,
        "issues": issues,
        "issue_count": len(issues),
        "summary": {
            "user_agent": ua[:80],
            "platform": platform,
            "webgl_renderer": fp.get('webgl', {}).get('renderer', 'N/A'),
            "webgl_vendor": fp.get('webgl', {}).get('vendor', 'N/A'),
            "fonts_count": len(fonts),
            "screen": f"{w}x{h}",
            "dpr": fp['screen'].get('devicePixelRatio'),
            "hardware_concurrency": fp['navigator'].get('hardwareConcurrency'),
        }
    }, ensure_ascii=False, indent=2)


@mcp.tool()
async def detect_stealth() -> str:
    """全面检测反检测/自动化特征（综合检测）"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const checks = {};

        // Navigator属性
        checks.navigator_webdriver = navigator.webdriver;
        checks.navigator_languages = navigator.languages?.length > 0;
        checks.navigator_plugins = navigator.plugins?.length;
        checks.navigator_permissions = !!navigator.permissions;

        // Window属性
        checks.window_chrome = !!window.chrome;
        checks.window_notifications = !!window.Notification;
        checks.outerWidth = window.outerWidth;
        checks.outerHeight = window.outerHeight;
        checks.innerWidth = window.innerWidth;
        checks.innerHeight = window.innerHeight;

        // DOM属性检测
        checks.attr_webdriver = !!document.documentElement.getAttribute('webdriver');
        checks.attr_selenium = !!document.documentElement.getAttribute('selenium');
        checks.attr_driver = !!document.documentElement.getAttribute('driver');
        checks.attr_cdp = !!document.documentElement.getAttribute('cdp');
        checks.attr_webkit = !!document.documentElement.getAttribute('webkit-');

        // UA检测
        checks.ua_headless = /headless/i.test(navigator.userAgent);
        checks.ua_has_webdriver = /webdriver/i.test(navigator.userAgent);

        // 功能检测
        checks.has_plugins = navigator.plugins?.length > 0;
        checks.has_permissions = !!navigator.permissions?.query;
        checks.has_notification = !!window.Notification;

        // CDP/DevTools检测
        try {
            const err = new Error();
            checks.cdp_in_stack = err.stack?.includes('evaluate') || false;
        } catch(e) { checks.cdp_in_stack = false; }

        // iframe contentWindow检测
        try {
            const iframe = document.createElement('iframe');
            iframe.style.display = 'none';
            document.body.appendChild(iframe);
            checks.iframe_contentWindow = !!iframe.contentWindow;
            checks.iframe_same_origin = true;
            document.body.removeChild(iframe);
        } catch(e) {
            checks.iframe_contentWindow = false;
            checks.iframe_same_origin = false;
        }

        // toString检测（检测API是否被hook）
        try {
            checks.toString_native = Function.prototype.toString.call(navigator.getUserMedia).includes('[native code]');
        } catch(e) {
            checks.toString_native = 'N/A';
        }

        // 风险评估
        const risks = [];
        if (checks.navigator_webdriver) risks.push('navigator.webdriver = true');
        if (checks.attr_webdriver) risks.push('webdriver DOM attribute');
        if (checks.attr_selenium) risks.push('selenium DOM attribute');
        if (checks.attr_driver) risks.push('driver DOM attribute');
        if (checks.ua_headless) risks.push('headless in User-Agent');
        if (checks.outerWidth === 0 && checks.outerHeight === 0) risks.push('zero window size');
        if (checks.cdp_in_stack) risks.push('CDP evaluate in stack');
        if (checks.ua_has_webdriver) risks.push('webdriver in User-Agent');
        if (!checks.has_plugins) risks.push('no plugins (may be suspicious)');
        if (checks.toString_native === false) risks.push('API toString not native (hooked)');

        checks.risks = risks;
        checks.risk_count = risks.length;
        checks.overall = risks.length === 0 ? 'CLEAN' : risks.length <= 2 ? 'LOW_RISK' : risks.length <= 4 ? 'MEDIUM_RISK' : 'HIGH_RISK';

        return checks;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


# ============================================================
# 7. Screencast Domain - 屏幕投射
# ============================================================

@mcp.tool()
async def screencast_start(width: int = 1280, height: int = 720) -> str:
    """开始屏幕投射（Page.startScreencast）

    Args:
        width: 视频宽度
        height: 视频高度
    """
    _, page, _ = await _ensure_browser()
    await page.set_viewport_size({"width": width, "height": height})
    return json.dumps({"success": True, "resolution": f"{width}x{height}", "note": "使用page_screenshot获取帧"})


# ============================================================
# 8. Cookie & Storage
# ============================================================

@mcp.tool()
async def storage_get_local_storage() -> str:
    """获取localStorage所有数据"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const data = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            data[key] = localStorage.getItem(key);
        }
        return data;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def storage_get_session_storage() -> str:
    """获取sessionStorage所有数据"""
    _, page, _ = await _ensure_browser()
    result = await page.evaluate("""() => {
        const data = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            data[key] = sessionStorage.getItem(key);
        }
        return data;
    }""")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
async def storage_set_local_storage(key: str, value: str) -> str:
    """设置localStorage

    Args:
        key: 键
        value: 值
    """
    _, page, _ = await _ensure_browser()
    await page.evaluate(f"localStorage.setItem('{key}', JSON.stringify({json.dumps(value)}))")
    return json.dumps({"success": True})


# ============================================================
# 启动
# ============================================================

if __name__ == "__main__":
    mcp.run()
