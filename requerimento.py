"""
Submits the Atestado de Residência Fiscal requerimento to e-CAC.
"""

import json
import re
import time
import httpx
from pathlib import Path
from config import Config

ENDPOINT = "https://www3.cav.receita.fazenda.gov.br/contribuinte/servicos/requerimento"
LIST_ENDPOINT = "https://www3.cav.receita.fazenda.gov.br/contribuinte/api/requerimento/list/"
FORM_ID = "69248f628a51d597f886ac9d"


def _build_payload(cfg: Config) -> dict:
    cpf = re.sub(r"\D", "", cfg.cpf)
    cnpj = re.sub(r"\D", "", cfg.cnpj)

    return {
        "usuario": {"ni": cpf},
        "contribuinte": {"cnpj": cnpj},
        "formulario": {"id": cfg.formulario_id},
        "beneficio": {"id": cfg.beneficio_id},
        "consolidacaoRespostas": [{"respostas": [
            {"campo": {"validacoes": [], "nome": "page#1", "tipo": "page", "label": "ATESTADO DE RESIDÊNCIA FISCAL NO BRASIL", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 1}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "label#1", "tipo": "label", "label": "O Atestado de Residência Fiscal no Brasil será emitido com o nome e o endereço constantes no cadastro da Receita Federal no momento da autorização. Se houver inconsistência no nome ou endereço, faça a alteração do CPF ou do CNPJ através dos canais de atendimento apropriados para a atualização cadastral e depois entre com um novo requerimento no Sisen (não apresente recurso).", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 2}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "tipo-requerente", "tipo": "radio", "label": "O formulário será emitido para:", "dica": "", "prefixo": None, "sufixo": None, "opcoes": ["Pessoa Jurídica", "Brasileiro nato ou naturalizado", "Estrangeiro"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": ["{\"opcao\":\"Estrangeiro\",\"campos\":[{\"nome\":\"visto-arquivo\",\"tipo\":\"upload\"},{\"nome\":\"visto-data-emissao\",\"tipo\":\"date\"},{\"nome\":\"visto-tipo\",\"tipo\":\"radio\"},{\"nome\":\"page#2\",\"tipo\":\"page\"}]}", "{\"opcao\":\"Brasileiro nato ou naturalizado\",\"campos\":[{\"nome\":\"mudado\",\"tipo\":\"radio\"},{\"nome\":\"residia\",\"tipo\":\"radio\"},{\"nome\":\"comunicacao\",\"tipo\":\"radio\"}]}"], "sequencial": 3}, "valor": "Pessoa Jurídica"},
            {"campo": {"validacoes": [], "nome": "data-inicial", "tipo": "date", "label": "Primeiro dia para o qual se deseja o ateste de residência fiscal no Brasil", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 4}, "valor": cfg.data_inicial},
            {"campo": {"validacoes": [], "nome": "data-final", "tipo": "date", "label": "Último dia para o qual se deseja o ateste de residência fiscal no Brasil", "dica": "Não é possível atestar residência em data futura.", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": "", "valorMaximo": "0", "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 5}, "valor": cfg.data_final},
            {"campo": {"validacoes": [], "nome": "comunicacao", "tipo": "radio", "label": "Apresentou COMUNICAÇÃO DE SAÍDA do Brasil antes ou durante o período requerido ?", "dica": "", "prefixo": None, "sufixo": None, "opcoes": ["Sim", "Não"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 6}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "residia", "tipo": "radio", "label": "Residia no Brasil no período requerido ?", "dica": "", "prefixo": None, "sufixo": None, "opcoes": ["Sim", "Não"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 7}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "mudado", "tipo": "radio", "label": "Ficou ausente do Brasil por mais de 12 meses, antes do período requerido ?", "dica": "", "prefixo": None, "sufixo": None, "opcoes": ["Sim", "Não"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 8}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "ocupacao", "tipo": "text", "label": "Ocupação principal", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": 30, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 9}, "valor": cfg.ocupacao},
            {"campo": {"validacoes": [], "nome": "valor-rendimento", "tipo": "number", "label": "Valor dos rendimentos auferidos no exterior durante o período informado acima (em R$)", "dica": "Valor em R$ (reais)", "prefixo": "R$", "sufixo": "", "opcoes": [], "formato": "", "casasDecimais": "2", "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 10}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "valor-imposto", "tipo": "number", "label": "Valor do imposto sobre a renda retido no exterior no período informado acima (em R$)", "dica": "Valo em R$ (reais)", "prefixo": "R$", "sufixo": "", "opcoes": [], "formato": "", "casasDecimais": "2", "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 11}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "fonte-pais", "tipo": "country", "label": "País em que o rendimento foi auferido", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 12}, "valor": cfg.pais},
            {"campo": {"validacoes": [], "nome": "fonte-rendimento", "tipo": "text", "label": "Tipo de rendimento", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": 30, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 13}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "fonte-nome", "tipo": "text", "label": "Nome da fonte pagadora no exterior", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": 30, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 14}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "fonte-NI", "tipo": "text", "label": "Código ou número de identificação da fonte pagadora no exterior", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": 30, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 15}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "observacao", "tipo": "text", "label": "Observações", "dica": "O texto digitado neste campo será impresso no QUADRO 1 do formulário", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": 200, "obrigatorio": False, "adicionais": None, "vinculos": None, "sequencial": 16}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "label#6", "tipo": "label", "label": "O texto que for digitado nesse campo será impresso no QUADRO 1 do formulário. Pode ser usado, por exemplo, para identificar os dados de uma filial da pessoa jurídica.", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": None, "sequencial": 17}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "visto-tipo", "tipo": "radio", "label": "Tipo de residência no Brasil, de acordo com a CRNM", "dica": "Carteira de Registro Nacional Migratório", "prefixo": None, "sufixo": None, "opcoes": ["permanente", "temporária"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": ["{\"opcao\":\"temporária\",\"campos\":[{\"nome\":\"dias184\",\"tipo\":\"radio\"},{\"nome\":\"data-vinculo-emprega\",\"tipo\":\"date\"},{\"nome\":\"visto-data-final\",\"tipo\":\"date\"}]}"], "sequencial": 18}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "visto-data-emissao", "tipo": "date", "label": "Data de emissão da CRNM", "dica": "Carteira de Registro Nacional Migratório", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 19}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "visto-data-final", "tipo": "date", "label": "Data final de residência dado pela CRNM", "dica": "Carteira de Registro Nacional Migratório", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 20}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "visto-arquivo", "tipo": "upload", "label": "Enviar copia da CRNM", "dica": "Carteira de Registro Nacional Migratório", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": True, "adicionais": None, "vinculos": [], "sequencial": 21}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "data-vinculo-emprega", "tipo": "date", "label": "Data de INÍCIO do vínculo empregatício no Brasil", "dica": "", "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": "", "valorMaximo": "", "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 22}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "dias184", "tipo": "radio", "label": "Já havia completado ao menos 184 dias de permanência no Brasil nos 12 meses anteriores ao período requerido ?", "dica": "", "prefixo": None, "sufixo": None, "opcoes": ["Sim", "Não"], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 23}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "concordo-1", "tipo": "checkbox", "label": "Concordo em me submeter à tributação no Brasil no período informado acima", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 24}, "valor": "true"},
            {"campo": {"validacoes": [], "nome": "label#3", "tipo": "label", "label": "O ateste da autoridade tributária brasileira diz respeito, exclusivamente, ao domicílio tributário no Brasil durante todo o período abrangido pelas datas digitadas pelo interessado no formulário. Os demais dados informados ficarão disponíveis para os procedimentos de fiscalização brasileiros.", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 25}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "label#5", "tipo": "label", "label": "O atestado será emitido em até 5 dias. Acompanhe as comunicações enviadas para a caixa postal e retorne ao eCAC para obter a cópia do documento quando receber o alerta de que ele foi gerado. A verificação de autenticidade pode ser feita através do seguinte endereço eletrônico  https://www.sisen.receita.fazenda.gov.br/sisen/inicio.jsf", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 26}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [], "nome": "label#4", "tipo": "label", "label": "***** Se o botão \"Próximo\" não estiver disponível, é porque algum campo foi preenchido de maneira incorreta. Verifique os campos marcados em vermelho e resolva as pendências. *****", "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": [], "sequencial": 27}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [{"tipo": "SCRIPT", "valor": None}], "nome": "script#1", "tipo": "script", "label": None, "dica": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "adicionais": None, "vinculos": None, "sequencial": 28}, "valor": "## Não Informado ##"},
            {"campo": {"validacoes": [{"tipo": "BLOQUEIO", "valor": []}], "nome": "dte#28", "tipo": "dte", "label": None, "prefixo": None, "sufixo": None, "opcoes": [], "formato": None, "casasDecimais": None, "valorMinimo": None, "valorMaximo": None, "tamanho": None, "obrigatorio": False, "sequencial": 251208}, "valor": "## Não Informado ##"},
        ]}],
    }


def _make_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "*/*",
        "Accept-Language": "pt-BR,pt;q=0.9",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "DNT": "1",
        "Origin": "https://www3.cav.receita.fazenda.gov.br",
        "Pragma": "no-cache",
        "Referer": f"https://www3.cav.receita.fazenda.gov.br/contribuinte/formulario/{FORM_ID}/internet/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


def submit_requerimento(token: str, cookies: dict, cfg: Config) -> dict:
    """
    POST the requerimento to e-CAC and return the parsed JSON response.
    Raises httpx.HTTPStatusError on non-2xx responses.
    """
    payload = _build_payload(cfg)
    payload_json = json.dumps(payload, ensure_ascii=False)
    files = {"requerimento": (None, payload_json, "application/json")}

    print(f"[requerimento] Submitting for CNPJ {cfg.cnpj} | {cfg.data_inicial} → {cfg.data_final}")
    with httpx.Client(timeout=30, cookies=cookies) as client:
        response = client.post(ENDPOINT, headers=_make_headers(token), files=files)

    response.raise_for_status()
    print(f"[requerimento] Response status: {response.status_code}")
    return response.json()


def list_requerimentos(token: str, cookies: dict, cnpj: str, limit: int = 10) -> list[dict]:
    """Fetch all requerimentos for the given CNPJ (most recent first)."""
    cnpj_digits = re.sub(r"\D", "", cnpj)
    params = {
        "ni": cnpj_digits,
        "tiporequerimento": "eletronico",
        "offset": 0,
        "limit": limit,
    }
    with httpx.Client(timeout=30, cookies=cookies) as client:
        response = client.get(LIST_ENDPOINT, headers=_make_headers(token), params=params)
    response.raise_for_status()
    return response.json()["items"]


def get_requerimento_status(token: str, cookies: dict, cnpj: str, protocolo: str) -> dict | None:
    """
    Find a specific requerimento by protocolo and return its latest status.
    Returns None if not found.
    """
    items = list_requerimentos(token, cookies, cnpj)
    item = next((i for i in items if i["protocolo"] == protocolo), None)
    if item is None:
        return None

    movimentacoes = item.get("movimentacoes", [])
    ultima = movimentacoes[-1] if movimentacoes else None

    return {
        "protocolo": item["protocolo"],
        "id": item["id"],
        "situacao": ultima["tipo"] if ultima else "DESCONHECIDA",
        "ultima_movimentacao": ultima["data"] if ultima else None,
        "movimentacoes": [{"tipo": m["tipo"], "id": m["id"], "data": m["data"]} for m in movimentacoes],
    }


def wait_for_deferido(
    token: str,
    cookies: dict,
    cnpj: str,
    protocolo: str,
    poll_interval: int = 15,
    timeout: int = 600,
) -> dict:
    """
    Poll the requerimento list until situacao == EM_ANALISE_DEFERIDO.
    Returns the status dict when reached. Raises RuntimeError on timeout.
    """
    print(f"[status] Polling for EM_ANALISE_DEFERIDO (interval={poll_interval}s, timeout={timeout}s)...")
    deadline = time.time() + timeout

    while time.time() < deadline:
        status = get_requerimento_status(token, cookies, cnpj, protocolo)
        if status is None:
            raise RuntimeError(f"Protocolo {protocolo} not found in requerimento list.")

        situacao = status["situacao"]
        print(f"[status] {protocolo} → {situacao}")

        if situacao == "EM_ANALISE_DEFERIDO":
            return status

        if situacao in ("INDEFERIDO", "CANCELADO"):
            raise RuntimeError(f"Requerimento {protocolo} ended with status: {situacao}")

        time.sleep(poll_interval)

    raise RuntimeError(f"Timeout waiting for EM_ANALISE_DEFERIDO for protocolo {protocolo}.")


def acknowledge_movimentacao(token: str, cookies: dict, requerimento_id: str, id_movimentacao: str) -> None:
    """
    Acknowledge the EM_ANALISE_DEFERIDO movimentacao so the PDF becomes available.
    POST /contribuinte/servicos/requerimento/<id>/movimentacoes/internet
    """
    url = f"https://www3.cav.receita.fazenda.gov.br/contribuinte/servicos/requerimento/{requerimento_id}/movimentacoes/internet"
    headers = {
        **_make_headers(token),
        "Referer": f"https://www3.cav.receita.fazenda.gov.br/contribuinte/requerimento/timeline/{requerimento_id}/",
    }
    payload = {"idMovimentacao": id_movimentacao}

    print(f"[ack] Acknowledging movimentacao {id_movimentacao}...")
    print(f"[ack] URL: POST {url}")
    print(f"[ack] Headers: {json.dumps(headers, indent=2)}")
    print(f"[ack] Cookies: {json.dumps(cookies, indent=2)}")
    print(f"[ack] Payload: {json.dumps(payload)}")
    with httpx.Client(timeout=30, cookies=cookies) as client:
        response = client.post(url, headers=headers, json=payload)
    print(f"[ack] Response {response.status_code}: {response.text}")
    response.raise_for_status()
    print(f"[ack] Acknowledged.")


def download_pdf(
    token: str,
    cookies: dict,
    requerimento_id: str,
    id_movimentacao: str,
    output_path: str | None = None,
) -> Path:
    """
    Download the Atestado PDF.
    GET /contribuinte/api/relatorios/despacho/<id>/<id_movimentacao>/
    Saves to output_path (default: atestado_<requerimento_id>.pdf).
    Returns the Path where the file was saved.
    """
    url = f"https://www3.cav.receita.fazenda.gov.br/contribuinte/api/relatorios/despacho/{requerimento_id}/{id_movimentacao}/"
    dest = Path(output_path or f"atestado_{requerimento_id}.pdf")

    print(f"[pdf] Downloading PDF from {url}...")
    with httpx.Client(timeout=60, cookies=cookies) as client:
        response = client.get(url, headers=_make_headers(token))
    response.raise_for_status()

    dest.write_bytes(response.content)
    print(f"[pdf] Saved to: {dest.resolve()}")
    return dest
