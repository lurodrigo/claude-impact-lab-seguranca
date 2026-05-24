"""
CLI entry point for report generation.

Usage examples:

  # List all available FM areas
  python main.py --list-areas

  # Generate full report for area fid=12 (Rio Sul / Lauro Müller), 2023-2024
  python main.py --fid 12 --ano-inicio 2023 --ano-fim 2024 --mes-ref "Maio 2026"

  # Generate report for all years available
  python main.py --fid 12 --ano-inicio 2020 --ano-fim 2024

  # Export HTML only (no PDF, faster for preview)
  python main.py --fid 12 --html-only

  # Skip map generation (fastest, for data validation)
  python main.py --fid 12 --no-maps
"""
import argparse
import os
import sys
import json
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from report_generator import gerar_contexto_relatorio, listar_areas
from pdf_exporter import exportar_pdf, exportar_html

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")


def main():
    parser = argparse.ArgumentParser(description="CompStat Report Generator")
    parser.add_argument("--list-areas", action="store_true", help="List available FM areas and exit")
    parser.add_argument("--fid",        type=int,   default=12,         help="Shapefile fid of the FM area")
    parser.add_argument("--ano-inicio", type=int,   default=2023,       help="First year of crime analysis window")
    parser.add_argument("--ano-fim",    type=int,   default=2024,       help="Last year of crime analysis window")
    parser.add_argument("--mes-ref",    type=str,   default="Maio 2026",help="Reference month/year for report header")
    parser.add_argument("--output",     type=str,   default="",         help="Output file path (auto-generated if omitted)")
    parser.add_argument("--html-only",  action="store_true",            help="Export HTML instead of PDF")
    parser.add_argument("--no-maps",    action="store_true",            help="Skip map/chart generation")
    parser.add_argument("--json-ctx",   action="store_true",            help="Dump context dict as JSON (debug)")
    args = parser.parse_args()

    if args.list_areas:
        print("\nÁreas disponíveis no shapefile:")
        for a in listar_areas():
            print(f"  fid={a['fid']:3d}  {a['nome']}")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n→ Gerando relatório para fid={args.fid} | período {args.ano_inicio}–{args.ano_fim}")
    t0 = time.time()

    ctx = gerar_contexto_relatorio(
        shapefile_fid   = args.fid,
        ano_inicio      = args.ano_inicio,
        ano_fim         = args.ano_fim,
        mes_referencia  = args.mes_ref,
        gerar_mapas     = not args.no_maps,
    )

    print(f"  ✓ Contexto calculado em {time.time()-t0:.1f}s")
    print(f"  ✓ Ocorrências na área (período): {ctx['indicadores']['total']}")
    print(f"  ✓ Fatores urbanos: {len(ctx['fatores'])}")
    print(f"  ✓ Câmeras: {ctx['cameras']['total']}")
    print(f"  ✓ Grupos criminosos: {ctx['identificacao']['grupos_criminosos']}")
    print(f"  ✓ Ranking: {ctx['indicadores']['ranking_pos']}º de {ctx['indicadores'].get('ranking_total_areas','?')} áreas")

    if args.json_ctx:
        ctx_clean = {k: v for k, v in ctx.items() if not k.startswith("img_")}
        print(json.dumps(ctx_clean, ensure_ascii=False, indent=2))

    if args.output:
        out_path = args.output
    else:
        ext = "html" if args.html_only else "pdf"
        safe_name = ctx["meta"]["nome_area"].replace("/", "-").replace("–", "-")[:60]
        out_path = os.path.join(OUTPUT_DIR, f"relatorio_{args.fid}_{args.ano_inicio}-{args.ano_fim}.{ext}")

    t1 = time.time()
    if args.html_only:
        path = exportar_html(ctx, out_path)
        print(f"  ✓ HTML exportado em {time.time()-t1:.1f}s")
    else:
        path = exportar_pdf(ctx, out_path)
        print(f"  ✓ PDF exportado em {time.time()-t1:.1f}s")

    print(f"\n✅ Relatório gerado: {path}\n")


if __name__ == "__main__":
    main()
