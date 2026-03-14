"""
CLI entry point.

Usage:
    python main.py \\
        --cpf 000.000.000-00 \\
        --password "sua_senha" \\
        --cnpj 00.000.000/0001-00 \\
        --data-inicial 2026-01-01 \\
        --data-final 2026-01-31 \\
        [--pais PORTUGAL] \\
        [--ocupacao "CNAE 62.04.0-00"] \\
        [--headless]
"""

import argparse
import asyncio
import json
import sys

from config import Config
from auth import get_auth_session
from requerimento import submit_requerimento, wait_for_deferido, acknowledge_movimentacao, download_pdf


def parse_args() -> Config:
    parser = argparse.ArgumentParser(
        description="Solicita Atestado de Residência Fiscal na Receita Federal (e-CAC)"
    )
    parser.add_argument("--cpf",          required=True,  help="CPF do responsável (gov.br login)")
    parser.add_argument("--password",     required=True,  help="Senha do gov.br")
    parser.add_argument("--cnpj",         required=True,  help="CNPJ para o qual o atestado será emitido")
    parser.add_argument("--data-inicial", required=True,  dest="data_inicial", help="Data inicial (YYYY-MM-DD)")
    parser.add_argument("--data-final",   required=True,  dest="data_final",   help="Data final (YYYY-MM-DD)")
    parser.add_argument("--pais",         default="PORTUGAL",          help="País de destino do atestado")
    parser.add_argument("--ocupacao",     default="CNAE 62.04.0-00",  help="Ocupação principal")
    parser.add_argument("--headless",      action="store_true",         help="Rodar o browser em modo headless")
    parser.add_argument("--capsolver-key", default=None, dest="capsolver_key",
                        help="Capsolver API key para resolver hCaptcha automaticamente (opcional)")

    args = parser.parse_args()

    return Config(
        cpf=args.cpf,
        password=args.password,
        cnpj=args.cnpj,
        data_inicial=args.data_inicial,
        data_final=args.data_final,
        pais=args.pais,
        ocupacao=args.ocupacao,
        headless=args.headless,
        capsolver_key=args.capsolver_key,
    )


async def run(cfg: Config) -> None:
    # Step 1 & 2: browser auth + CNPJ profile switch → token + cookies
    token, cookies = await get_auth_session(cfg.cpf, cfg.password, cfg.cnpj, headless=cfg.headless, capsolver_key=cfg.capsolver_key)
    print(f"[main] Token obtained successfully.")

    # Step 3: submit the requerimento
    result = submit_requerimento(token, cookies, cfg)
    print("\n=== Requerimento submetido ===")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    protocolo = result.get("protocolo")
    if not protocolo:
        print("[main] No protocolo in response — cannot continue.")
        return

    # Step 4: poll until EM_ANALISE_DEFERIDO
    status = wait_for_deferido(token, cookies, cfg.cnpj, protocolo)
    print("\n=== Deferido ===")
    print(json.dumps(status, indent=2, ensure_ascii=False))

    # Step 5: acknowledge the movimentacao
    requerimento_id = status["id"]
    id_movimentacao = next(
        m["id"] for m in status["movimentacoes"] if m["tipo"] == "EM_ANALISE_DEFERIDO"
    )
    acknowledge_movimentacao(token, cookies, requerimento_id, id_movimentacao)

    # Step 6: download the PDF
    pdf_path = download_pdf(token, cookies, requerimento_id, id_movimentacao)
    print(f"\n=== PDF salvo em: {pdf_path} ===")


def main() -> None:
    cfg = parse_args()
    try:
        asyncio.run(run(cfg))
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
