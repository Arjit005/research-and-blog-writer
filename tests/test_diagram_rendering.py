"""Automated browser interaction and responsive rendering test suite using Playwright."""

import json
import os
import pytest
from playwright.sync_api import sync_playwright

HTML_TEST_HARNESS = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Mermaid Canvas Test Harness</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>
  <style>
    body { margin: 0; background-color: #030712; color: #f1f5f9; font-family: sans-serif; }
    .canvas-container {
      width: 1000px;
      height: 600px;
      margin: 20px auto;
      border: 1px solid #1e293b;
      position: relative;
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      background: radial-gradient(#1e293b 1px, transparent 1px);
      background-size: 24px 24px;
    }
    .viewport {
      transform-origin: center center;
      transition: transform 0.1s ease-out;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    svg {
      width: 100% !important;
      height: auto !important;
      max-width: none !important;
      display: block;
      margin: 0 auto;
    }
    .controls {
      display: flex;
      gap: 8px;
      justify-content: center;
      margin-top: 10px;
    }
    button {
      padding: 6px 12px;
      background: #1e293b;
      color: #f1f5f9;
      border: 1px solid #334155;
      border-radius: 6px;
      cursor: pointer;
    }
    #error-box {
      display: none;
      padding: 16px;
      background: rgba(245, 158, 11, 0.1);
      border: 1px solid rgba(245, 158, 11, 0.3);
      color: #fbbf24;
      border-radius: 8px;
      margin: 20px auto;
      width: 800px;
      font-family: monospace;
    }
  </style>
</head>
<body>
  <div class="controls">
    <button id="zoom-in" onclick="zoomBy(0.2)">Zoom In</button>
    <button id="zoom-out" onclick="zoomBy(-0.2)">Zoom Out</button>
    <button id="reset-zoom" onclick="resetZoom()">Reset</button>
    <button id="toggle-source" onclick="toggleSource()">Source</button>
  </div>
  <div class="canvas-container" id="container">
    <div class="viewport" id="viewport">
      <div id="mermaid-target"></div>
    </div>
  </div>
  <div id="error-box"></div>
  <pre id="source-box" style="display:none; width: 800px; margin: 10px auto; color: #a5b4fc; background: #0f172a; padding: 12px; border-radius: 8px;"></pre>

  <script>
    mermaid.initialize({
      startOnLoad: false,
      theme: 'dark',
      securityLevel: 'strict'
    });

    let currentZoom = 1.0;
    let panX = 0, panY = 0;

    function updateTransform() {
      document.getElementById('viewport').style.transform = `translate(${panX}px, ${panY}px) scale(${currentZoom})`;
    }

    function zoomBy(delta) {
      currentZoom = Math.max(0.4, Math.min(3.0, currentZoom + delta));
      updateTransform();
    }

    function resetZoom() {
      currentZoom = 1.0;
      panX = 0;
      panY = 0;
      updateTransform();
    }

    let showingSource = false;
    function toggleSource() {
      showingSource = !showingSource;
      document.getElementById('source-box').style.display = showingSource ? 'block' : 'none';
      document.getElementById('container').style.display = showingSource ? 'none' : 'flex';
    }

    async function renderMermaid(code) {
      document.getElementById('source-box').innerText = code;
      const target = document.getElementById('mermaid-target');
      const errorBox = document.getElementById('error-box');
      errorBox.style.display = 'none';
      try {
        await mermaid.parse(code);
        const { svg } = await mermaid.render('test-svg-id', code);
        target.innerHTML = svg;
      } catch (err) {
        errorBox.style.display = 'block';
        errorBox.innerText = 'Parse Error: ' + err.message;
        target.innerHTML = '';
      }
    }
  </script>
</body>
</html>
"""

@pytest.fixture(scope="module")
def harness_path(tmp_path_factory):
    fn = tmp_path_factory.mktemp("harness") / "index.html"
    fn.write_text(HTML_TEST_HARNESS, encoding="utf-8")
    return str(fn)


def test_playwright_mermaid_renders_properly(harness_path):
    """Verify that Mermaid renders valid SVGs and occupies proportional canvas area without shrinking."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"file:///{harness_path.replace(os.sep, '/')}")

        flowchart_code = """flowchart TD
            A[Identity Provider] --> B[Policy Decision Point]
            B --> C[Policy Enforcement Point]
            C --> D[Microsegmented Workload]
        """
        page.evaluate("code => renderMermaid(code)", flowchart_code)
        page.wait_for_selector("#mermaid-target svg")

        # Verify SVG element is present and has proper attributes
        svg = page.locator("#mermaid-target svg")
        assert svg.is_visible()
        box = svg.bounding_box()
        assert box is not None
        # Verify it is not a tiny box: width must occupy a substantial portion (> 250px) of container
        assert box["width"] > 250
        assert box["height"] > 100

        browser.close()


def test_playwright_zoom_and_pan_interactions(harness_path):
    """Test interactive zoom in, zoom out, and reset button clicks."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"file:///{harness_path.replace(os.sep, '/')}")

        page.evaluate("code => renderMermaid(code)", "flowchart LR\n A[Start] --> B[End]")
        page.wait_for_selector("#mermaid-target svg")

        # Initial scale
        init_transform = page.evaluate("() => document.getElementById('viewport').style.transform")
        assert "scale(1)" in init_transform or init_transform == ""

        # Click Zoom In
        page.click("#zoom-in")
        zoomed_in = page.evaluate("() => document.getElementById('viewport').style.transform")
        assert "scale(1.2)" in zoomed_in

        # Click Zoom Out twice
        page.click("#zoom-out")
        page.click("#zoom-out")
        zoomed_out = page.evaluate("() => document.getElementById('viewport').style.transform")
        assert "scale(0.8)" in zoomed_out

        # Click Reset
        page.click("#reset-zoom")
        reset_val = page.evaluate("() => document.getElementById('viewport').style.transform")
        assert "scale(1)" in reset_val

        browser.close()


def test_playwright_syntax_error_fallback(harness_path):
    """Verify that malformed Mermaid syntax displays the error container cleanly without unhandled crashes."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.goto(f"file:///{harness_path.replace(os.sep, '/')}")

        invalid_code = "flowchart TD\n A --> [unclosed label"
        page.evaluate("code => renderMermaid(code)", invalid_code)

        page.wait_for_selector("#error-box", state="visible")
        error_text = page.inner_text("#error-box")
        assert "Parse Error" in error_text

        browser.close()


def test_playwright_responsive_viewports(harness_path):
    """Verify rendering at Desktop, Tablet, and Mobile viewports."""
    viewports = [
        {"name": "Desktop", "width": 1280, "height": 800},
        {"name": "Tablet", "width": 768, "height": 1024},
        {"name": "Mobile", "width": 375, "height": 667},
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for vp in viewports:
            page = browser.new_page(viewport={"width": vp["width"], "height": vp["height"]})
            page.goto(f"file:///{harness_path.replace(os.sep, '/')}")

            page.evaluate("code => renderMermaid(code)", "flowchart TD\n NodeA --> NodeB")
            page.wait_for_selector("#mermaid-target svg")

            svg = page.locator("#mermaid-target svg")
            assert svg.is_visible()
            page.close()

        browser.close()
