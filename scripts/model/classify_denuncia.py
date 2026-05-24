#!/usr/bin/env python3
"""
Classify Disque Denúncia reports using Claude API with Prompt Caching.
Extracts crime type, modus operandi, escape routes, fencing points, and criminal organization influence.
"""

import os
import sys
import csv
import json
import logging
import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field
from anthropic import AsyncAnthropic
from tqdm.asyncio import tqdm as async_tqdm

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class DenunciaClassification(BaseModel):
    """Structured output for Disque Denúncia classification."""

    desc_delito: str = Field(
        description="Crime type: 'Roubo a transeunte', 'Roubo de carater generico ocorrido sem carro e que nao é roubo a celular', 'Roubo de aparelho celular', 'Roubo em coletivo (em transporte: onibus, van etc)', or 'Indeterminado'"
    )

    modus_operandi: str = Field(
        description="Method of operation: 'Pedestre', 'Moto', 'Carro', or 'Indeterminado'"
    )

    rotas_fuga: str = Field(
        description="Escape routes mentioned: 'Sim', 'Não', or 'Indeterminado'"
    )

    rotas_fuga_detalhes: Optional[str] = Field(
        default=None,
        description="Details of escape routes if found, otherwise null"
    )

    pontos_receptacao: str = Field(
        description="Fencing points mentioned: 'Sim', 'Não', or 'Indeterminado'"
    )

    pontos_receptacao_detalhes: Optional[str] = Field(
        default=None,
        description="Details of fencing points if found, otherwise null"
    )

    influencia_org_criminosas: str = Field(
        description="Criminal organization influence: 'Sim', 'Não', or 'Indeterminado'"
    )

    influencia_org_criminosas_detalhes: Optional[str] = Field(
        default=None,
        description="Which faction/organization if found, otherwise null"
    )

    fator_urbano_categoria: str = Field(
        description="Urban factor category from CompStat table, or 'Nenhum' if not mentioned"
    )

    fator_urbano: str = Field(
        description="Specific urban factor from CompStat table, or 'Nenhum' if not mentioned"
    )

    fator_urbano_orgao_responsavel: str = Field(
        description="Organization responsible for resolving the urban factor, or 'Nenhum' if not applicable"
    )


# System prompt with classification instructions (will be cached)
SYSTEM_PROMPT = """Você é um analista de segurança pública do CompStat Municipal do Rio de Janeiro. Sua tarefa é classificar relatos de denúncias anônimas para identificar padrões criminais.

INSTRUÇÕES DE CLASSIFICAÇÃO:

1. **desc_delito** (tipo de crime - siga EXATAMENTE o padrão ISP):
   - "Roubo de aparelho celular" - especificamente roubo de aparelho celular (o objetivo é o celular)
   - "Roubo em coletivo (em transporte: onibus, van etc)" - roubo em transporte público
   - "Roubo a transeunte" - roubo com ameaça de violência (ou concretização de violência) contra pessoa na rua (roubos genéricos que NÃO são celular e NÃO são em transporte)
   - "Indeterminado" - se não houver informação suficiente ou não for roubo

2. **modus_operandi** (modo de operação - APENAS para crimes de roubo):
   - "Pedestre" - crime cometido com o criminoso a pé
   - "Moto" - uso de motocicleta
   - "Carro" - uso de automóvel
   - "Indeterminado" - se não especificado OU se desc_delito for "Indeterminado" (não é roubo)

3. **rotas_fuga**:
   - "Sim" se o relato menciona rotas de fuga específicas
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha rotas_fuga_detalhes com a descrição

4. **pontos_receptacao** (pontos de receptação/venda de produtos roubados):
   - "Sim" se o relato menciona locais de receptação
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha pontos_receptacao_detalhes com o local/descrição

5. **influencia_org_criminosas** (facções):
   - "Sim" se o relato menciona facções criminosas (CV, ADA, TCP, etc.)
   - "Não" se não menciona
   - "Indeterminado" se não há informação
   - Se "Sim", preencha influencia_org_criminosas_detalhes com qual facção

6. **Fatores Urbanos de Incidência Criminal** (MAIS IMPORTANTE):
   Identifique se o relato menciona algum fator urbano da tabela CompStat abaixo.
   Se SIM, preencha: fator_urbano_categoria, fator_urbano, fator_urbano_orgao_responsavel
   Se NÃO, preencha todos com "Nenhum"

   TABELA DE FATORES URBANOS:

   Categoria: Trânsito
   - Fator: "Ponto de retenção de tráfego" → Órgão: "CET-Rio"
   - Fator: "Motocicletas trafegando no passeio" → Órgão: "GM-Rio"
   - Fator: "Bicicletas trafegando no passeio" → Órgão: "GM-Rio"
   - Fator: "Estacionamento irregular forçando pedestres à pista" → Órgão: "SEOP"
   - Fator: "Veículos de grande porte obstruindo a visibilidade" → Órgão: "SEOP"

   Categoria: Ponto de ônibus
   - Fator: "Ponto de ônibus com histórico de vandalismo" → Órgão: "SMTR"

   Categoria: Vegetação urbana
   - Fator: "Vegetação encobrindo iluminação pública" → Órgão: "Comlurb"
   - Fator: "Vegetação obstruindo a visibilidade do passeio" → Órgão: "Comlurb"
   - Fator: "Vegetação servindo de esconderijo" → Órgão: "Comlurb"

   Categoria: Limpeza urbana
   - Fator: "Lixo/entulho obstruindo a visibilidade" → Órgão: "Comlurb"
   - Fator: "Lixo/entulho forçando pedestres à pista" → Órgão: "Comlurb"

   Categoria: Iluminação
   - Fator: "Área mal iluminada com circulação de pedestres" → Órgão: "RioLuz"
   - Fator: "Área mal iluminada com parada de veículos" → Órgão: "RioLuz"

   Categoria: Obstrução de logradouro
   - Fator: "Mobiliário urbano desviando pedestres à pista" → Órgão: "Seconserva"
   - Fator: "Calçada estreita forçando pedestres à pista" → Órgão: "Seconserva"
   - Fator: "Comércio irregular obstruindo a visibilidade do passeio" → Órgão: "SEOP"

   Categoria: Refúgio
   - Fator: "Mobiliário abandonado servindo de esconderijo" → Órgão: "Seconserva"
   - Fator: "Tapumes servindo de esconderijo" → Órgão: "Seconserva"
   - Fator: "Mobiliário/estrutura servindo de esconderijo" → Órgão: "Seconserva"
   - Fator: "Vãos ou cavidades usados como esconderijo" → Órgão: "Seconserva"

   Categoria: Pessoa em situação de rua
   - Fator: "Adultos (transitória / pernoite / moradia)" → Órgão: "SMAS"
   - Fator: "Crianças e/ou adolescentes" → Órgão: "SMAS"
   - Fator: "Famílias ou casais" → Órgão: "SMAS"

   Categoria: Cena de uso de drogas
   - Fator: "Eventual (sem pontos de venda próximos)" → Órgão: "SMAS"
   - Fator: "Crônica (com pontos de venda nas proximidades)" → Órgão: "SMAS"

   Categoria: Praças e parques
   - Fator: "Área mal iluminada com circulação de pedestres" → Órgão: "RioLuz"
   - Fator: "Vegetação servindo de esconderijo" → Órgão: "Comlurb"
   - Fator: "Mobiliário abandonado servindo de esconderijo" → Órgão: "Seconserva"
   - Fator: "Mobiliário/estrutura servindo de esconderijo" → Órgão: "Seconserva"

IMPORTANTE:
- Seja preciso e baseie-se APENAS no texto fornecido
- Use "Indeterminado" quando não houver informação clara
- Para campos de detalhes (rotas_fuga_detalhes, etc.), use null se não aplicável
- Se desc_delito for "Indeterminado" (não é roubo), modus_operandi DEVE ser "Indeterminado" também
- Para fatores urbanos: use "Nenhum" se não houver menção a fatores da tabela
- Se múltiplos fatores forem mencionados, escolha o MAIS RELEVANTE para o contexto criminal

Analise o seguinte relato e extraia as informações pedidas em formato JSON estruturado."""


async def classify_batch_async(client: AsyncAnthropic, relatos_batch: List[tuple], semaphore: asyncio.Semaphore) -> tuple[List[Optional[DenunciaClassification]], dict]:
    """
    Classify multiple relatos in a single async API request using Claude API with prompt caching.

    Args:
        client: Async Anthropic client
        relatos_batch: List of (index, relato) tuples
        semaphore: Semaphore to limit concurrent requests

    Returns:
        Tuple of (List of DenunciaClassification objects, usage_stats dict)
    """
    if not relatos_batch:
        return [], {}

    async with semaphore:
        try:
            # Build prompt with multiple relatos
            relatos_text = ""
            for idx, (original_idx, relato) in enumerate(relatos_batch):
                relatos_text += f"\n[RELATO_{idx}]\n{relato[:2000]}\n"

            user_message = f"""Classifique EXATAMENTE {len(relatos_batch)} relatos listados abaixo.

{relatos_text}

IMPORTANTE: Retorne EXATAMENTE {len(relatos_batch)} objetos no array JSON, na MESMA ORDEM dos relatos acima.

Responda APENAS com um array JSON (sem texto adicional):
[
  {{
    "desc_delito": "...",
    "modus_operandi": "...",
    "rotas_fuga": "...",
    "rotas_fuga_detalhes": "..." ou null,
    "pontos_receptacao": "...",
    "pontos_receptacao_detalhes": "..." ou null,
    "influencia_org_criminosas": "...",
    "influencia_org_criminosas_detalhes": "..." ou null,
    "fator_urbano_categoria": "...",
    "fator_urbano": "...",
    "fator_urbano_orgao_responsavel": "..."
  }},
  ...
]"""

            response = await client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=6000,
                system=[
                    {
                        "type": "text",
                        "text": SYSTEM_PROMPT,
                        "cache_control": {"type": "ephemeral"}  # Cache the system prompt
                    }
                ],
                messages=[{
                    "role": "user",
                    "content": user_message
                }]
            )

            # Extract usage statistics
            usage_stats = {
                'input_tokens': response.usage.input_tokens,
                'output_tokens': response.usage.output_tokens,
                'cache_creation_input_tokens': getattr(response.usage, 'cache_creation_input_tokens', 0),
                'cache_read_input_tokens': getattr(response.usage, 'cache_read_input_tokens', 0)
            }

            # Parse the JSON output
            result_text = response.content[0].text.strip()
            # Remove markdown code fences if present
            if result_text.startswith('```'):
                result_text = result_text.split('```')[1]
                if result_text.startswith('json'):
                    result_text = result_text[4:]
                result_text = result_text.strip()

            result_json = json.loads(result_text)

            # Validate we got the right number of results
            if len(result_json) != len(relatos_batch):
                logger.warning(f"Expected {len(relatos_batch)} results, got {len(result_json)} - will adjust")

                # Handle mismatch: truncate if too many, pad with None if too few
                if len(result_json) > len(relatos_batch):
                    result_json = result_json[:len(relatos_batch)]
                else:
                    # Pad with None for missing results
                    result_json.extend([None] * (len(relatos_batch) - len(result_json)))

            # Convert to Pydantic models
            classifications = []
            for i, item in enumerate(result_json):
                if item is None:
                    logger.warning(f"Missing classification for item {i}")
                    classifications.append(None)
                else:
                    try:
                        classifications.append(DenunciaClassification(**item))
                    except Exception as e:
                        logger.error(f"Failed to parse classification {i}: {e}")
                        classifications.append(None)

            return classifications, usage_stats

        except Exception as e:
            logger.error(f"Batch classification error: {e}")
            return [None] * len(relatos_batch), {}


async def process_csv_async(input_path: str, output_path: str, api_key: str, limit: Optional[int] = None, max_concurrent: int = 25):
    """
    Process the CSV file and add classification columns using async processing.

    Args:
        input_path: Path to input CSV (disk_denuncia.csv)
        output_path: Path to output CSV with classifications
        api_key: Anthropic API key
        limit: Optional limit on number of rows with relatos to process (for testing)
        max_concurrent: Maximum number of concurrent API requests
    """
    client = AsyncAnthropic(api_key=api_key)
    semaphore = asyncio.Semaphore(max_concurrent)

    # Read input CSV
    logger.info(f"Reading {input_path}...")
    with open(input_path, 'r', encoding='iso-8859-1') as f:
        reader = csv.DictReader(f, delimiter=';')
        fieldnames = reader.fieldnames
        rows = [row for row in reader if any(row.values())]  # Skip empty rows

    logger.info(f"Loaded {len(rows)} rows")

    # Add new columns
    new_fieldnames = list(fieldnames) + [
        'desc_delito',
        'modus_operandi',
        'rotas_fuga',
        'rotas_fuga_detalhes',
        'pontos_receptacao',
        'pontos_receptacao_detalhes',
        'influencia_org_criminosas',
        'influencia_org_criminosas_detalhes',
        'fator_urbano_categoria',
        'fator_urbano',
        'fator_urbano_orgao_responsavel'
    ]

    # Filter rows with non-empty relatos
    rows_with_relatos = []
    rows_without_relatos = []

    for row in rows:
        relato = row.get('relato_redacted', '').strip()
        if relato:
            rows_with_relatos.append(row)
        else:
            rows_without_relatos.append(row)

    logger.info(f"Rows with relatos: {len(rows_with_relatos)}")
    logger.info(f"Rows without relatos (will skip API calls): {len(rows_without_relatos)}")
    logger.info(f"Cost savings from filtering: {len(rows_without_relatos) / len(rows) * 100:.1f}%")

    # Apply limit if specified (for testing)
    if limit is not None:
        logger.info(f"LIMITING to first {limit} rows with relatos (test mode)")
        rows_with_relatos = rows_with_relatos[:limit]

    # Process rows with relatos in batches (async)
    BATCH_SIZE = 20  # Process 20 relatos per API call (reduced due to longer prompt with urban factors)
    logger.info(f"Classifying with Claude using ASYNC batch processing (batch size: {BATCH_SIZE})")
    logger.info(f"Max concurrent requests: {max_concurrent}")
    logger.info("Using prompt caching for 90% cost reduction")
    logger.info(f"Total API calls needed: ~{len(rows_with_relatos) // BATCH_SIZE + 1}")

    # Track total usage and cost
    total_usage = {
        'input_tokens': 0,
        'output_tokens': 0,
        'cache_creation_input_tokens': 0,
        'cache_read_input_tokens': 0
    }

    # Prepare all batches
    all_batches = []
    batch_indices = []
    for batch_start in range(0, len(rows_with_relatos), BATCH_SIZE):
        batch_end = min(batch_start + BATCH_SIZE, len(rows_with_relatos))
        batch_rows = rows_with_relatos[batch_start:batch_end]

        # Prepare batch data: (index, relato)
        relatos_batch = []
        for idx, row in enumerate(batch_rows):
            relato = row.get('relato_redacted', '').strip()
            relatos_batch.append((idx, relato))

        all_batches.append((relatos_batch, batch_rows))
        batch_indices.append(batch_start)

    # Process all batches concurrently
    logger.info(f"Sending {len(all_batches)} batches concurrently (max {max_concurrent} at a time)...")
    tasks = [classify_batch_async(client, batch_data, semaphore) for batch_data, _ in all_batches]

    # Use gather to run all tasks and maintain order
    ordered_results = await asyncio.gather(*tasks)

    processed_rows = []
    for (relatos_batch, batch_rows), (classifications, usage_stats) in zip(all_batches, ordered_results):
        # Accumulate usage stats
        for key in total_usage:
            total_usage[key] += usage_stats.get(key, 0)

        # Apply classifications to rows
        for idx, (row, classification) in enumerate(zip(batch_rows, classifications)):
            if classification:
                row['desc_delito'] = classification.desc_delito
                row['modus_operandi'] = classification.modus_operandi
                row['rotas_fuga'] = classification.rotas_fuga
                row['rotas_fuga_detalhes'] = classification.rotas_fuga_detalhes or ''
                row['pontos_receptacao'] = classification.pontos_receptacao
                row['pontos_receptacao_detalhes'] = classification.pontos_receptacao_detalhes or ''
                row['influencia_org_criminosas'] = classification.influencia_org_criminosas
                row['influencia_org_criminosas_detalhes'] = classification.influencia_org_criminosas_detalhes or ''
                row['fator_urbano_categoria'] = classification.fator_urbano_categoria
                row['fator_urbano'] = classification.fator_urbano
                row['fator_urbano_orgao_responsavel'] = classification.fator_urbano_orgao_responsavel
            else:
                # Fallback to "Indeterminado" on error
                row['desc_delito'] = 'Indeterminado'
                row['modus_operandi'] = 'Indeterminado'
                row['rotas_fuga'] = 'Indeterminado'
                row['rotas_fuga_detalhes'] = ''
                row['pontos_receptacao'] = 'Indeterminado'
                row['pontos_receptacao_detalhes'] = ''
                row['influencia_org_criminosas'] = 'Indeterminado'
                row['influencia_org_criminosas_detalhes'] = ''
                row['fator_urbano_categoria'] = 'Nenhum'
                row['fator_urbano'] = 'Nenhum'
                row['fator_urbano_orgao_responsavel'] = 'Nenhum'

            processed_rows.append(row)

    # Add rows without relatos (with "Indeterminado" values)
    logger.info("Adding rows without relatos...")
    for row in rows_without_relatos:
        row['desc_delito'] = 'Indeterminado'
        row['modus_operandi'] = 'Indeterminado'
        row['rotas_fuga'] = 'Indeterminado'
        row['rotas_fuga_detalhes'] = ''
        row['pontos_receptacao'] = 'Indeterminado'
        row['pontos_receptacao_detalhes'] = ''
        row['influencia_org_criminosas'] = 'Indeterminado'
        row['influencia_org_criminosas_detalhes'] = ''
        row['fator_urbano_categoria'] = 'Nenhum'
        row['fator_urbano'] = 'Nenhum'
        row['fator_urbano_orgao_responsavel'] = 'Nenhum'
        processed_rows.append(row)

    # Write output CSV
    logger.info(f"Writing to {output_path}...")
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=new_fieldnames, delimiter=';')
        writer.writeheader()
        writer.writerows(processed_rows)

    logger.info(f"Done! Classified {len(processed_rows)} rows")

    # Calculate and log costs
    # Pricing for claude-sonnet-4-6 (as of 2025):
    # Input: $3 per 1M tokens
    # Output: $15 per 1M tokens
    # Cache writes: $3.75 per 1M tokens
    # Cache reads: $0.30 per 1M tokens

    cost_input = (total_usage['input_tokens'] / 1_000_000) * 3.0
    cost_output = (total_usage['output_tokens'] / 1_000_000) * 15.0
    cost_cache_write = (total_usage['cache_creation_input_tokens'] / 1_000_000) * 3.75
    cost_cache_read = (total_usage['cache_read_input_tokens'] / 1_000_000) * 0.30

    total_cost = cost_input + cost_output + cost_cache_write + cost_cache_read

    logger.info("=" * 60)
    logger.info("TOKEN USAGE & COST SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Input tokens: {total_usage['input_tokens']:,}")
    logger.info(f"Output tokens: {total_usage['output_tokens']:,}")
    logger.info(f"Cache creation tokens: {total_usage['cache_creation_input_tokens']:,}")
    logger.info(f"Cache read tokens: {total_usage['cache_read_input_tokens']:,}")
    logger.info(f"Total tokens: {sum(total_usage.values()):,}")
    logger.info("-" * 60)
    logger.info(f"Input cost: ${cost_input:.4f}")
    logger.info(f"Output cost: ${cost_output:.4f}")
    logger.info(f"Cache write cost: ${cost_cache_write:.4f}")
    logger.info(f"Cache read cost: ${cost_cache_read:.4f}")
    logger.info("-" * 60)
    logger.info(f"TOTAL COST: ${total_cost:.2f}")
    logger.info("=" * 60)

    # Save cost report to file
    cost_report_path = output_path.replace('.csv', '_cost_report.txt')
    with open(cost_report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("DISQUE DENÚNCIA CLASSIFICATION - COST REPORT\n")
        f.write("=" * 60 + "\n\n")
        f.write(f"Input file: {input_path}\n")
        f.write(f"Output file: {output_path}\n")
        f.write(f"Date: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Total rows processed: {len(rows)}\n")
        f.write(f"Rows with relatos: {len(rows_with_relatos) if limit is None else limit}\n")
        f.write(f"Rows without relatos: {len(rows_without_relatos)}\n")
        f.write(f"API calls made: {len(rows_with_relatos) // BATCH_SIZE + 1 if limit is None else (limit // BATCH_SIZE + 1)}\n")
        f.write(f"Batch size: {BATCH_SIZE}\n")
        f.write(f"Max concurrent requests: {max_concurrent}\n\n")
        f.write("TOKEN USAGE:\n")
        f.write(f"  Input tokens: {total_usage['input_tokens']:,}\n")
        f.write(f"  Output tokens: {total_usage['output_tokens']:,}\n")
        f.write(f"  Cache creation tokens: {total_usage['cache_creation_input_tokens']:,}\n")
        f.write(f"  Cache read tokens: {total_usage['cache_read_input_tokens']:,}\n")
        f.write(f"  Total tokens: {sum(total_usage.values()):,}\n\n")
        f.write("COSTS (USD):\n")
        f.write(f"  Input cost: ${cost_input:.4f}\n")
        f.write(f"  Output cost: ${cost_output:.4f}\n")
        f.write(f"  Cache write cost: ${cost_cache_write:.4f}\n")
        f.write(f"  Cache read cost: ${cost_cache_read:.4f}\n")
        f.write(f"  ─────────────────────\n")
        f.write(f"  TOTAL COST: ${total_cost:.2f}\n")
        f.write("=" * 60 + "\n")

    logger.info(f"Cost report saved to: {cost_report_path}")


def main():
    """Main entry point."""
    # Get API key
    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error("ANTHROPIC_API_KEY environment variable not set")
        logger.error("Set it with: export ANTHROPIC_API_KEY='your-api-key'")
        sys.exit(1)

    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Classify Disque Denúncia reports')
    parser.add_argument('--input', '-i', default='dados/disk_denuncia.csv',
                       help='Input CSV file path')
    parser.add_argument('--output', '-o', default=None,
                       help='Output CSV file path (default: output/<input_basename>_classified.csv)')
    parser.add_argument('--limit', '-l', type=int, default=None,
                       help='Limit number of rows to process (for testing)')

    args = parser.parse_args()

    input_path = args.input

    # Auto-generate output path if not specified
    if args.output:
        output_path = args.output
    else:
        input_basename = os.path.basename(input_path).replace('.csv', '')
        output_path = f'output/{input_basename}_classified.csv'

    limit = args.limit

    if not os.path.exists(input_path):
        logger.error(f"{input_path} not found")
        sys.exit(1)

    # Create output directory if it doesn't exist
    os.makedirs('output', exist_ok=True)

    if limit:
        logger.info(f"Running in TEST mode: will process only {limit} rows with relatos")

    # Process (async)
    asyncio.run(process_csv_async(input_path, output_path, api_key, limit=limit))


if __name__ == '__main__':
    main()
