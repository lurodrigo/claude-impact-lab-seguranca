"""
Bridge between the Streamlit app and the backend report generator.

Handles sys.path manipulation so backend modules can resolve their
bare imports (e.g. ``from config import ...``) without modifying
any backend code.
"""
from __future__ import annotations

import os
import sys
import tempfile

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from report_generator import gerar_contexto_relatorio, listar_areas  # noqa: E402
from pdf_exporter import renderizar_html, exportar_pdf, exportar_html  # noqa: E402


def check_playwright() -> bool:
    """Return True if Playwright + Chromium are available."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        return False


def generate_pdf_bytes(context: dict) -> bytes:
    """
    Render context to PDF and return raw bytes (suitable for
    ``st.download_button``).  Uses a temp file because Playwright's
    ``page.pdf()`` requires a file path.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    tmp.close()
    try:
        exportar_pdf(context, tmp.name)
        with open(tmp.name, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp.name)


def generate_html_string(context: dict) -> str:
    """Render context to HTML string."""
    return renderizar_html(context)
