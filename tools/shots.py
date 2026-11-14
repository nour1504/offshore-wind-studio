"""Screenshots of the QA application (tools/dev.py serve), light or dark, for visual reviews.

A headless Edge with its own temporary profile (never the user's Edge), driven over the DevTools
protocol; headless, it keeps drawing maps and charts with no window shown.

    backend/.venv/Scripts/python.exe tools/dev.py shots <out_dir> dark 1440x1000 [--full]
        [--wait=6] [--click=<button text>]... name=<route> [name=<route>...]

Routes without "#/" (projects, compute, projects/<id>/farms...). --click: a real mouse click on the
button, link, tab, label or field whose text, accessible name or placeholder is or starts with the
text; --type=<text> types into the focused field; both in the order given.

Studies: --query=direction=latitude, --report (DOM inventory), --text (sentences and colours),
--fonts, --colours, --reduced-motion, --timings (each map's time to style and first drawing),
--block=<host>[,<host>] (as offline), --settle=<s> (wait before the capture), --eval=<javascript>,
--css=<file> (laid over the app's styles). Local gallery: --base=http://127.0.0.1:8766/
name=directions.html.
"""

import base64
import json
import socket
import subprocess
import tempfile
import time
import urllib.request
from contextlib import suppress
from pathlib import Path
from urllib.parse import parse_qsl, urlencode

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
BASE = "http://127.0.0.1:8765/#/"
FIND = """(() => {
  const all = [...document.querySelectorAll('button, a, [role=button], [role=tab], [role=option], label, input, textarea')];
  const name = e => e.getAttribute('aria-label') ?? e.getAttribute('placeholder') ?? e.textContent.trim();
  const el = all.find(e => name(e) === TEXT) ?? all.find(e => name(e).startsWith(TEXT));
  if (!el) return null;
  el.scrollIntoView({block: 'center'});
  const r = el.getBoundingClientRect();
  return [r.x + r.width / 2, r.y + r.height / 2];
})()"""


def main(argv: list[str]) -> None:
    def option(name: str, default: str | None = None) -> str | None:
        return next((a.split("=", 1)[1] for a in argv if a.startswith(f"--{name}=")), default)

    out = Path(argv[0])
    out.mkdir(parents=True, exist_ok=True)
    scheme, size = argv[1], argv[2]
    width, height = (int(v) for v in size.split("x"))
    full = "--full" in argv
    wait = float(option("wait", "6"))
    actions = [
        (a[2:].split("=", 1)[0], a.split("=", 1)[1])
        for a in argv
        if a.startswith(("--click=", "--type="))
    ]
    query = urlencode(parse_qsl(option("query", "") or "", keep_blank_values=True))
    base = option("base", BASE) or BASE
    base = base.replace("/#/", f"/?{query}#/") if query else base
    jobs = [a.split("=", 1) for a in argv[3:] if not a.startswith("--")]
    blocked = [f"MAP {host} ~NOTFOUND" for host in (option("block") or "").split(",") if host]
    # Every capture owns its endpoint, even if a previous Edge is still closing.
    with socket.socket() as endpoint:
        endpoint.bind(("127.0.0.1", 0))
        port = endpoint.getsockname()[1]
    with tempfile.TemporaryDirectory(prefix="ows-edge-", ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen(
            [
                EDGE,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={profile}",
                "--use-angle=swiftshader",
                "--enable-unsafe-swiftshader",
                "--hide-scrollbars",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-extensions",
                f"--window-size={width},{height}",
                *([f"--host-resolver-rules={', '.join(blocked)}"] if blocked else []),
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            target = None
            for _ in range(50):
                try:
                    pages = [
                        t
                        for t in json.load(
                            urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list")
                        )
                        if t.get("type") == "page"
                    ]
                    if pages:
                        target = pages[0]["webSocketDebuggerUrl"]
                        break
                except OSError:
                    pass
                time.sleep(0.3)
            if target is None:
                raise SystemExit("Edge did not start")
            with connect(target, max_size=None, open_timeout=20) as ws:
                counter = 0

                def call(method: str, **params):
                    nonlocal counter
                    counter += 1
                    ws.send(json.dumps({"id": counter, "method": method, "params": params}))
                    while True:
                        message = json.loads(ws.recv(timeout=60))
                        if message.get("id") == counter:
                            if "error" in message:
                                raise RuntimeError(f"{method}: {message['error']}")
                            return message.get("result", {})

                call("Page.enable")
                features = [{"name": "prefers-color-scheme", "value": scheme}]
                if "--reduced-motion" in argv:
                    features.append({"name": "prefers-reduced-motion", "value": "reduce"})
                call("Emulation.setEmulatedMedia", features=features)
                sheet = option("css")
                if sheet:
                    # Added once the page is parsed, before its scripts run (they read the colours)
                    css = json.dumps(Path(sheet).read_text(encoding="utf-8"))
                    call(
                        "Page.addScriptToEvaluateOnNewDocument",
                        source="document.addEventListener('readystatechange', () => document.readyState === 'interactive'"
                        f" && document.head.appendChild(Object.assign(document.createElement('style'), {{ textContent: {css} }})))",
                    )
                call(
                    "Emulation.setDeviceMetricsOverride",
                    width=width,
                    height=height,
                    deviceScaleFactor=1,
                    mobile=False,
                )
                for name, route in jobs:
                    call("Page.navigate", url=base + route)
                    time.sleep(wait)
                    for kind, text in actions:
                        if kind == "type":
                            call("Input.insertText", text=text)
                            time.sleep(1.5)
                            continue
                        found = call(
                            "Runtime.evaluate",
                            returnByValue=True,
                            expression=FIND.replace("TEXT", json.dumps(text)),
                        )["result"].get("value")
                        if not found:
                            print(f"  {name}: nothing to click named {text!r}")
                            continue
                        for event in ("mouseMoved", "mousePressed", "mouseReleased"):
                            call(
                                "Input.dispatchMouseEvent",
                                type=event,
                                x=found[0],
                                y=found[1],
                                button="left",
                                clickCount=1,
                            )
                        time.sleep(1.2)
                    script = option("eval")
                    if script:
                        call("Runtime.evaluate", expression=script)
                        time.sleep(1.5)
                    time.sleep(float(option("settle", "0") or 0))
                    params: dict = {"format": "png"}
                    if full:
                        content = call("Page.getLayoutMetrics")["cssContentSize"]
                        params.update(
                            captureBeyondViewport=True,
                            clip={
                                "x": 0,
                                "y": 0,
                                "width": width,
                                "height": min(content["height"], 6000),
                                "scale": 1,
                            },
                        )
                    (out / f"{name}.png").write_bytes(
                        base64.b64decode(call("Page.captureScreenshot", **params)["data"])
                    )
                    if "--text" in argv:
                        # Every sentence shown, one per line, after its text colour (dimmed = grey)
                        text = call(
                            "Runtime.evaluate",
                            returnByValue=True,
                            expression=r"""(() => {
                          const main = document.querySelector('main') ?? document.body;
                          return [...main.querySelectorAll('p, span, div, label')].filter(e => e.childElementCount === 0 && e.textContent.trim().length > 25)
                            .map(e => (getComputedStyle(e).color.match(/\d+/g) ?? []).slice(0, 3).join(',') + ' | ' + e.textContent.trim()).join('\n');
                        })()""",
                        )["result"]["value"]
                        (out / f"{name}.txt").write_text(text, encoding="utf-8")
                    if "--fonts" in argv:
                        # Every typeface, size and weight shown, with where and a few of its texts
                        fonts = call(
                            "Runtime.evaluate",
                            returnByValue=True,
                            expression=r"""(() => {
                          const found = {};
                          const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                          for (let node = walk.nextNode(); node; node = walk.nextNode()) {
                            const text = node.textContent.trim();
                            const el = node.parentElement;
                            if (!text || !el || !el.getClientRects().length || el.closest('[aria-hidden="true"], script, style')) continue;
                            const style = getComputedStyle(el);
                            if (style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
                            const key = style.fontFamily.split(',')[0].replace(/"/g, '') + ' | ' + style.fontSize + ' | ' + style.fontWeight;
                            const owner = el.closest('[class]');
                            const cls = owner ? String(owner.getAttribute('class')).split(/\s+/).filter(c => !/^m_[0-9a-f]+$/.test(c)).slice(0, 2).join('.') : '';
                            const entry = found[key] ??= { count: 0, where: {} };
                            entry.count += 1;
                            const where = el.tagName.toLowerCase() + (cls ? '.' + cls : '');
                            const seen = entry.where[where] ??= [];
                            if (seen.length < 3 && !seen.includes(text.slice(0, 40))) seen.push(text.slice(0, 40));
                          }
                          return JSON.stringify(found, null, 1);
                        })()""",
                        )["result"]["value"]
                        (out / f"{name}.fonts.json").write_text(fonts, encoding="utf-8")
                    if "--colours" in argv:
                        # Every colour shown (backgrounds, texts, borders, SVG fills and strokes,
                        # shadows, gradients), with how often and where
                        colours = call(
                            "Runtime.evaluate",
                            returnByValue=True,
                            expression=r"""(() => {
                          const found = {};
                          const add = (colour, kind, el) => {
                            if (!colour || colour === 'none' || colour === 'transparent' || /rgba\([^)]*, 0\)$/.test(colour)) return;
                            const entry = found[colour] ??= { count: 0, kinds: {}, where: [] };
                            entry.count += 1;
                            entry.kinds[kind] = (entry.kinds[kind] ?? 0) + 1;
                            const owner = el.closest('[class]');
                            const cls = owner ? String(owner.getAttribute('class')).split(/\s+/).filter(c => !/^m_[0-9a-f]+$/.test(c)).slice(0, 2).join('.') : '';
                            const where = el.tagName.toLowerCase() + (cls ? '.' + cls : '');
                            if (entry.where.length < 5 && !entry.where.includes(where)) entry.where.push(where);
                          };
                          for (const el of document.querySelectorAll('body *')) {
                            if (!el.getClientRects().length || el.closest('[aria-hidden="true"]:not(svg *)')) continue;
                            const s = getComputedStyle(el);
                            if (s.visibility === 'hidden' || Number(s.opacity) === 0) continue;
                            add(s.backgroundColor, 'background', el);
                            if (s.backgroundImage !== 'none' && !s.backgroundImage.startsWith('url')) add(s.backgroundImage.slice(0, 160), 'gradient', el);
                            if ([...el.childNodes].some(n => n.nodeType === 3 && n.textContent.trim())) add(s.color, 'text', el);
                            if (parseFloat(s.borderTopWidth) > 0 && s.borderTopStyle !== 'none') add(s.borderTopColor, 'border', el);
                            if (s.boxShadow !== 'none') add(s.boxShadow.slice(0, 160), 'shadow', el);
                            if (el instanceof SVGElement && el.tagName !== 'svg' && el.tagName !== 'g') { add(s.fill, 'fill', el); add(s.stroke, 'stroke', el); }
                          }
                          return JSON.stringify(found, null, 1);
                        })()""",
                        )["result"]["value"]
                        (out / f"{name}.colours.json").write_text(colours, encoding="utf-8")
                    if "--report" in argv:
                        report = call(
                            "Runtime.evaluate",
                            returnByValue=True,
                            expression="""JSON.stringify({
                          title: document.querySelector('h1')?.textContent,
                          direction: document.documentElement.dataset.design ?? 'baseline',
                          width: innerWidth, overflow: document.documentElement.scrollWidth > innerWidth,
                          font: getComputedStyle(document.body).fontFamily,
                          fonts: [...document.fonts].map(f => ({family: f.family, status: f.status})),
                          reducedMotion: matchMedia('(prefers-reduced-motion: reduce)').matches,
                          runningAnimations: document.getAnimations().filter(a => a.playState === 'running').length,
                          canvasFilters: [...document.querySelectorAll('.ows-map canvas')].map(e => getComputedStyle(e).filter),
                          controls: [...document.querySelectorAll('button, a, input, textarea, select')].map(e => ({
                            tag: e.tagName, type: e.type ?? '', role: e.getAttribute('role'),
                            label: e.getAttribute('aria-label') ?? '', text: e.textContent.trim(),
                            visible: e.getClientRects().length > 0
                          }))
                        })""",
                        )["result"]["value"]
                        (out / f"{name}.json").write_text(report, encoding="utf-8")
                    if "--timings" in argv:
                        # Map timings recorded by ProjectMap (mount to style, mount to first idle)
                        # (waits up to 30 s for a map opened by a click to finish drawing)
                        for _ in range(60):
                            timings = call(
                                "Runtime.evaluate",
                                returnByValue=True,
                                expression="JSON.stringify(window.__owsMapTimings ?? [])",
                            )["result"]["value"]
                            if timings != "[]":
                                break
                            time.sleep(0.5)
                        (out / f"{name}.timings.json").write_text(timings, encoding="utf-8")
                        print(f"{name} timings: {timings}")
                    print(f"{name}: {out / (name + '.png')}")
                # The browser may close the socket before acknowledging its own exit.
                with suppress(ConnectionClosed):
                    call("Browser.close")
        finally:
            try:
                browser.wait(3)
            except subprocess.TimeoutExpired:
                # Kill this Edge process tree by PID only, never other Edge instances
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(browser.pid)],
                    capture_output=True,
                    check=False,
                )
                try:
                    browser.wait(10)
                except subprocess.TimeoutExpired:
                    browser.kill()
                    browser.wait(10)
