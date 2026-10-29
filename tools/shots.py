"""Screenshots of the QA application (python tools/dev.py serve) for visual reviews, light or dark.

Drives a headless Edge over the DevTools protocol, with its own temporary profile (never the
user's Edge). Being headless, it keeps drawing when no window is visible, so maps and charts
render.

    backend/.venv/Scripts/python.exe tools/dev.py shots <out_dir> dark 1440x1000 [--full]
        [--wait=6] [--click=<button text>]... name=<route> [name=<route>...]

Routes are the application's, without "#/": projects, compute, projects/<id>/farms...
A --click target is a button, link, tab, label or field whose text, accessible name or
placeholder is (or starts with) the given text; the click is a real mouse click, made after the
page has loaded. --type=<text> then types into the focused field. Clicks and typing run in the
order given.

Design studies: --query=direction=latitude, --report (DOM inventory), --text (sentences shown, with their colour), --reduced-motion,
--timings (time taken by each map: to its style, to its first complete drawing),
--block=<host>[,<host>] (that server cannot be reached, as when offline or behind a filter),
--settle=<seconds> (wait after the clicks before the capture),
--eval=<javascript> (run in the page after the clicks, e.g. to place a 3D camera).
For the local screenshot gallery, --base=http://127.0.0.1:8766/ name=directions.html.
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
