from dataclasses import dataclass, field


@dataclass
class Config:
    # gov.br credentials
    cpf: str
    password: str

    # CNPJ to act on behalf of
    cnpj: str

    # Request parameters
    data_inicial: str   # YYYY-MM-DD
    data_final: str     # YYYY-MM-DD
    pais: str = "PORTUGAL"
    ocupacao: str = "CNAE 62.04.0-00"

    # e-CAC static form IDs for Atestado de Residência Fiscal
    formulario_id: str = "69248f628a51d597f886ac9d"
    beneficio_id: str = "68b88fdf3089db035f17d57e"

    # Browser — keep False while developing so you can see the flow
    headless: bool = False

    # Capsolver API key — if set, hCaptchas are solved automatically
    # Get one at https://capsolver.com (~$1 per 1000 solves)
    capsolver_key: str | None = None
