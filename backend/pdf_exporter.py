"""
PDF export: renders the Jinja2 template with report context and converts
to PDF via Playwright (headless Chromium). This avoids native GTK/Pango
dependencies that WeasyPrint requires on Windows.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")


def _build_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    env.filters["abs"] = abs
    return env


def renderizar_html(context: dict) -> str:
    """Renders the report template with the given context. Returns HTML string."""
    env = _build_env()
    template = env.get_template("relatorio.html")
    return template.render(**context)


def exportar_pdf(context: dict, output_path: str) -> str:
    """
    Renders HTML and writes a PDF to output_path via headless Chromium.
    Returns the absolute path to the generated file.
    """
    from playwright.sync_api import sync_playwright

    html_str = renderizar_html(context)

    # Write HTML to a temp file so Chromium can resolve relative resources
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", encoding="utf-8", delete=False
    ) as tmp:
        tmp.write(html_str)
        tmp_path = tmp.name

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file:///{tmp_path.replace(os.sep, '/')}")
            page.wait_for_load_state("networkidle")
            page.pdf(
                path=output_path,
                format="A4",
                margin={"top": "14mm", "right": "12mm", "bottom": "14mm", "left": "12mm"},
                print_background=True,
            )
            browser.close()
    finally:
        os.unlink(tmp_path)

    return os.path.abspath(output_path)


def exportar_html(context: dict, output_path: str) -> str:
    """Writes the rendered HTML to disk (useful for browser preview)."""
    html_str = renderizar_html(context)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_str)
    return os.path.abspath(output_path)
