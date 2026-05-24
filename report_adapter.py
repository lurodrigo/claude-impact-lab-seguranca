"""
Bridge between the Streamlit app and the backend report generator.

Handles sys.path manipulation so backend modules can resolve their
bare imports (e.g. ``from config import ...``) without modifying
any backend code.
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile

_BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")


def _import_backend():
    """
    Import backend modules with backend/ at the front of sys.path,
    temporarily hiding the root-level data_loader so the backend
    picks up its own.
    """
    saved_path = sys.path[:]
    saved_modules = {}
    shadow_names = ["data_loader", "config"]
    for name in shadow_names:
        if name in sys.modules:
            saved_modules[name] = sys.modules.pop(name)

    try:
        sys.path.insert(0, _BACKEND_DIR)
        # Remove the project root so backend's bare imports win
        project_root = os.path.dirname(os.path.abspath(__file__))
        sys.path = [p for p in sys.path if os.path.abspath(p) != project_root]

        report_gen = importlib.import_module("report_generator")
        pdf_exp = importlib.import_module("pdf_exporter")
        return report_gen, pdf_exp
    finally:
        sys.path = saved_path
        # Restore frontend modules that were shadowed
        for name, mod in saved_modules.items():
            sys.modules[name] = mod


_rg, _pe = _import_backend()

gerar_contexto_relatorio = _rg.gerar_contexto_relatorio
listar_areas = _rg.listar_areas
renderizar_html = _pe.renderizar_html
exportar_pdf = _pe.exportar_pdf
exportar_html = _pe.exportar_html


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
