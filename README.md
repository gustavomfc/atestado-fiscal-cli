# atestado-api

CLI para emissão automatizada de **Atestado de Residência Fiscal no Brasil** via e-CAC (Receita Federal), sem depender de APIs públicas — o fluxo completo é realizado por automação de browser + chamadas diretas às APIs internas do portal.

## Pré-requisitos

- Python 3.11+
- [Google Chrome](https://www.google.com/chrome/) instalado no caminho padrão do sistema operacional
- Conta gov.br com acesso ao e-CAC e representação legal da empresa (CNPJ)

## Instalação

```bash
pip install -r requirements.txt
python -m patchright install chromium
```

## Uso

```bash
python main.py \
  --cpf 000.000.000-00 \
  --password "sua_senha_govbr" \
  --cnpj 00.000.000/0001-00 \
  --data-inicial 2026-01-01 \
  --data-final 2026-12-31 \
  [--pais PORTUGAL] \
  [--ocupacao "CNAE 62.04.0-00"] \
  [--headless] \
  [--verbose]
```

### Argumentos

| Argumento | Obrigatório | Descrição |
|---|---|---|
| `--cpf` | sim | CPF do representante legal (usado no login gov.br) |
| `--password` | sim | Senha da conta gov.br |
| `--cnpj` | sim | CNPJ da empresa para a qual o atestado será emitido |
| `--data-inicial` | sim | Primeiro dia do período (`YYYY-MM-DD`) |
| `--data-final` | sim | Último dia do período (`YYYY-MM-DD`) |
| `--pais` | não | País de destino do atestado (padrão: `PORTUGAL`) |
| `--ocupacao` | não | Ocupação principal (padrão: `CNAE 62.04.0-00`) |
| `--headless` | não | Executa o browser sem interface gráfica |
| `--verbose` / `-v` | não | Exibe logs detalhados: tokens, headers, payloads |

### Exemplo de saída

```
Abrindo e-CAC: https://www3.cav.receita.fazenda.gov.br/autenticacao
Aguardando redirecionamento para gov.br SSO...
Alternando perfil para CNPJ 22.111.312/0001-11...
Resolvendo captcha do perfil (aguarde)...
Autenticação concluída.
Submetendo requerimento para CNPJ 22111312000111 (2026-01-01 → 2026-12-31)...
Requerimento submetido — protocolo: 0012312.123123.4.3.123.1.8-42
Aguardando análise do requerimento 0012312.123123.2.4.123.1.8-42...
Requerimento deferido (id: 69b82129e8a14756d5123123123).
Registrando ciência da movimentação...
Baixando PDF do atestado...
PDF salvo em: /caminho/atestado_69b82129e8a14756d5de123123.pdf
```

O PDF é salvo no diretório de trabalho atual com o nome `atestado_<id>.pdf`.

## Fluxo de execução

```
1. Browser: login gov.br (CPF + senha)  →  hCaptcha manual se necessário
2. Browser: troca de perfil e-CAC para CNPJ  →  captura SISEN_TOKEN (REPRESENTANTE_LEGAL)
3. API: POST requerimento  →  retorna protocolo
4. API: GET poll status  →  aguarda EM_ANALISE_DEFERIDO
5. API: GET detalhe (Next.js)  →  obtém ID correto da movimentação
6. API: POST ciência  →  libera o PDF
7. API: GET PDF  →  salva arquivo local
```

Veja [docs/requests.md](docs/requests.md) para detalhes completos de todas as requisições.

## Perfil Chrome persistente

O browser usa um perfil Chrome dedicado em `~/.atestado_api/chrome_profile/`. Isso mantém cookies e histórico entre execuções, evitando que o hCaptcha seja acionado repetidamente.

## Estrutura do projeto

```
main.py          — ponto de entrada CLI, orquestra o fluxo completo
auth.py          — automação de browser (login gov.br + troca de perfil e-CAC)
requerimento.py  — todas as chamadas de API REST após a autenticação
config.py        — dataclass com parâmetros da execução
captcha.py       — integração Capsolver (não utilizada atualmente)
requirements.txt — dependências Python
docs/
  requests.md    — documentação detalhada de todas as requisições
```
