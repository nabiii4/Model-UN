"""Real-browser tests (Chromium via Playwright) at Chromebook size 1366x768, in mock mode.

Optional: they skip themselves if Playwright isn't installed. To run them:
    pip install -r requirements-dev.txt && python -m playwright install chromium
    pytest tests/e2e
"""
import re
import threading
import time

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from conftest import make_app  # noqa: E402

CHROMEBOOK = {"width": 1366, "height": 768}


@pytest.fixture(scope="module")
def base_url(tmp_path_factory):
    from werkzeug.serving import make_server
    app = make_app(tmp_path_factory.mktemp("e2e"))
    server = make_server("127.0.0.1", 0, app, threaded=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    pw = sync_api.sync_playwright().start()
    try:
        b = pw.chromium.launch(args=["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"])
    except Exception as e:  # browser not downloaded
        pw.stop()
        pytest.skip(f"Chromium isn't available: {e}")
    yield b
    b.close()
    pw.stop()


class Watcher:
    """Collects console errors and page crashes so a test fails on any JavaScript error."""

    def __init__(self, page):
        self.errors = []
        page.on("pageerror", lambda e: self.errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: self._console(m))

    def _console(self, m):
        # 423 (lock) and 4xx answers are expected API results, shown to the user as friendly messages.
        if m.type == "error" and "status of 4" not in m.text:
            self.errors.append(f"console: {m.text}")


def wait_for(cond, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        time.sleep(0.2)
    raise AssertionError("timed out")


def join(page, base_url, name, next_path):
    page.goto(f"{base_url}/join?next={next_path}")
    page.fill("#club-code", "testclub")
    page.fill("#name", name)
    page.fill("#pin", "1234")
    page.click("#join-btn")
    page.wait_for_url(f"{base_url}{next_path}")


def test_whole_loop_on_a_chromebook(browser, base_url):
    """door -> draw -> questions -> reveal -> edit -> save -> round -> feedback -> handoff -> Human Round"""
    ctx = browser.new_context(viewport=CHROMEBOOK)
    page = ctx.new_page()
    watch = Watcher(page)
    page.goto(base_url + "/")
    page.click("a.door[href='/draw?path=canvas']")
    page.wait_for_url(base_url + "/draw?path=canvas")
    join(page, base_url, "Loop Tester", "/draw?path=canvas")

    box = page.locator(".pad-canvas").bounding_box()
    page.mouse.move(box["x"] + 150, box["y"] + 120)
    page.mouse.down()
    for i in range(25):
        page.mouse.move(box["x"] + 150 + i * 12, box["y"] + 120 + (i % 4) * 15)
    page.mouse.up()
    page.click("#done-drawing")
    page.click("#use-photo")
    page.click("button.chip:has-text('Being interrupted')")
    page.click("#q-continue")
    page.wait_for_selector("#to-meet:not([hidden])", timeout=30000)
    assert page.locator("#clue-list li").count() >= 2
    page.click("#to-meet")
    page.fill("#revise-text", "rename it to Captain Chaos")
    page.click("#revise-go")
    page.click("#revise-result button:has-text('Accept')")
    wait_for(lambda: page.input_value(".persona-card input.inline-edit >> nth=0") == "Captain Chaos")
    page.click("#to-save")
    page.click("#save-btn")
    page.click("text=Practice against it now")
    page.wait_for_selector("#delegate option", state="attached")
    page.fill("#my-country", "Canada")
    page.click("#start")
    page.wait_for_url(re.compile(r".*/practice/[0-9a-f-]{36}$"), timeout=30000)
    page.wait_for_selector(".bubble.delegate")
    # The Practice Room fits a 1366x768 screen without page scrolling.
    assert page.evaluate("() => document.scrollingElement.scrollHeight <= window.innerHeight + 2")
    answers = ["Canada would phase out single-use plastic over five years, for example with a fee on producers.",
               "The fee is paid by the companies that make the packaging, not shoppers.",
               "Canada agrees jobs matter, so we would fund job training with part of the fee."]
    for i, text in enumerate(answers):
        page.fill("#answer", text)
        page.keyboard.press("Control+Enter")
        if i < 2:
            wait_for(lambda: page.locator(".bubble.delegate").count() >= i + 2 and page.locator("#answer").is_enabled())
    page.wait_for_url("**/feedback", timeout=40000)
    quote = page.inner_text(".strength-quote").strip("“”")
    assert any(quote.lower().rstrip(".") in a.lower() for a in answers)
    page.click("text=Continue")
    page.wait_for_url(re.compile(r".*/human\?round=.*"))
    assert "Now go find a human." in page.inner_text("h1")
    page.click("#found-btn")
    for _ in range(4):
        page.click("#next-seg")
    page.wait_for_selector("#hr-done:not([hidden])")
    assert "human round" in page.inner_text("#hr-done").lower()
    assert watch.errors == []
    ctx.close()


def test_captured_images_are_not_mirrored(browser, base_url):
    """prepareImage keeps left on the left; the camera code asks for mirror: false."""
    from pathlib import Path
    camera_js = (Path(__file__).resolve().parents[2] / "static" / "js" / "draw-camera.js").read_text(encoding="utf-8")
    assert "mirror: false" in camera_js
    page = browser.new_page(viewport=CHROMEBOOK)
    page.goto(base_url + "/draw?path=paper")
    left_is_dark = page.evaluate("""async () => {
      const { prepareImage } = await import('/static/js/image-prep.js');
      const c = document.createElement('canvas'); c.width = 200; c.height = 100;
      const ctx = c.getContext('2d'); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, 200, 100);
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, 100, 100);
      const out = await prepareImage(c, { boost: false });
      const img = new Image(); img.src = out.dataUrl; await img.decode();
      const k = document.createElement('canvas'); k.width = 200; k.height = 100;
      const kc = k.getContext('2d'); kc.drawImage(img, 0, 0);
      return kc.getImageData(20, 50, 1, 1).data[0] < 60 && kc.getImageData(180, 50, 1, 1).data[0] > 200;
    }""")
    assert left_is_dark
    page.close()


def test_keyboard_only_round(browser, base_url):
    page = browser.new_page(viewport=CHROMEBOOK)
    watch = Watcher(page)
    join(page, base_url, "Keys Only", "/practice/new?delegate=seed-perfect-suit")
    page.wait_for_selector("#delegate option", state="attached")
    page.focus("#my-country")
    page.keyboard.type("Japan")
    page.focus("#start")
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r".*/practice/[0-9a-f-]{36}$"), timeout=30000)
    page.wait_for_selector(".bubble.delegate")
    for i in range(3):
        wait_for(lambda: page.locator("#answer").is_enabled())
        page.focus("#answer")
        page.keyboard.type("Japan supports a treaty with yearly reports from 30 countries.")
        page.keyboard.press("Control+Enter")
        if i < 2:
            wait_for(lambda: page.locator(".bubble.delegate").count() >= i + 2)
    page.wait_for_url("**/feedback", timeout=40000)
    page.focus("text=Continue")
    page.keyboard.press("Enter")
    page.wait_for_url(re.compile(r".*/human.*"))
    assert watch.errors == []
    page.close()


@pytest.mark.parametrize("width", [360, 390, 1366])
def test_no_sideways_scrolling(browser, base_url, width):
    page = browser.new_page(viewport={"width": width, "height": 780})
    for path in ["/", "/wall", "/draw?path=canvas", "/draw?path=paper", "/human", "/join", "/d/seed-varsity-shark",
                 "/how-it-works", "/ritual", "/privacy"]:
        page.goto(base_url + path)
        page.wait_for_timeout(300)
        assert page.evaluate("() => document.documentElement.scrollWidth") <= width, path
    page.close()
