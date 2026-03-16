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
        [--headless] \\
        [--verbose]
"""

import argparse
import asyncio
import logging
import sys

from config import Config
from auth import get_auth_session
from requerimento import submit_requerimento, wait_for_deferido, acknowledge_movimentacao, download_pdf, get_requerimento_detail


def parse_args() -> tuple[Config, bool]:
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
    parser.add_argument("--headless",     action="store_true",         help="Rodar o browser em modo headless")
    parser.add_argument("--capsolver-key", default=None, dest="capsolver_key",
                        help="Capsolver API key para resolver hCaptcha automaticamente (opcional)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Exibir logs detalhados (tokens, headers, payloads)")

    args = parser.parse_args()

    cfg = Config(
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
    return cfg, args.verbose


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )
    # Silence noisy third-party loggers
    for noisy in ("httpx", "httpcore", "asyncio", "playwright"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


async def run(cfg: Config) -> None:
    log = logging.getLogger("main")

    token, cookies = await get_auth_session(cfg.cpf, cfg.password, cfg.cnpj, headless=cfg.headless, capsolver_key=cfg.capsolver_key)
    log.info("Autenticação concluída.")

    result = submit_requerimento(token, cookies, cfg)
    protocolo = result.get("protocolo")
    log.info("Requerimento submetido — protocolo: %s", protocolo)

    if not protocolo:
        log.error("Sem protocolo na resposta — não é possível continuar.")
        return

    status = wait_for_deferido(token, cookies, cfg.cnpj, protocolo)
    requerimento_id = status["id"]
    log.info("Requerimento deferido (id: %s).", requerimento_id)

    detail = get_requerimento_detail(token, cookies, requerimento_id)
    id_movimentacao = next(
        m["id"] for m in detail["movimentacoes"] if m.get("podeTomarCiencia")
    )
    acknowledge_movimentacao(token, cookies, requerimento_id, id_movimentacao)
    log.info("Ciência registrada.")

    pdf_path = download_pdf(token, cookies, requerimento_id, id_movimentacao)
    log.info("PDF salvo em: %s", pdf_path.resolve())


def main() -> None:
    cfg, verbose = parse_args()
    setup_logging(verbose)
    try:
        asyncio.run(run(cfg))
    except Exception as e:
        logging.getLogger("main").error("Erro: %s", e)
        if verbose:
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
