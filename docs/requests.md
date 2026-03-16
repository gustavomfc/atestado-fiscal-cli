# Requisições — Detalhamento Técnico

Documentação de todas as requisições realizadas pelo CLI, na ordem de execução.

---

## Autenticação (Browser Automation)

As etapas 1 e 2 são realizadas pelo módulo `auth.py` via [patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright) (fork do Playwright com anti-detecção de automação), usando o binário real do Chrome e um perfil persistente em `~/.atestado_api/chrome_profile/`.

### 1. Acesso à página de login do e-CAC

```
GET https://www3.cav.receita.fazenda.gov.br/autenticacao
```

Carrega o formulário de login do e-CAC. O script aguarda o botão `Acesso Gov BR` ficar visível e clica nele (`input[type="image"][alt="Acesso Gov BR"]`), que pode acionar um hCaptcha antes do redirecionamento para o gov.br.

### 2. Login gov.br SSO

```
GET https://sso.acesso.gov.br/...
```

Após o hCaptcha (se acionado), o browser é redirecionado para o SSO do gov.br. O script preenche:

- Campo CPF: `input[name="accountId"]` — apenas dígitos
- Clica em "Continuar"
- Campo senha: `input[name="password"]`
- Clica em "Entrar"

Após o login bem-sucedido, o SSO redireciona de volta para o e-CAC em `cav.receita.fazenda.gov.br`.

### 3. Troca de perfil para CNPJ

```
Browser interaction: cav.receita.fazenda.gov.br/ecac/#
```

Com o perfil padrão (CPF/TITULAR), o script realiza a troca de perfil para o CNPJ da empresa:

1. Clica em `#btnPerfil`
2. Preenche `#txtNIPapel` com os dígitos do CNPJ
3. Clica em `input.submit[value="Alterar"]`
4. Aguarda networkidle (pode acionado hCaptcha — resolução manual)
5. Tenta capturar o redirect para `www3.cav.receita.fazenda.gov.br` por 5s
6. Se não ocorrer, navega para `https://cav.receita.fazenda.gov.br/eCAC/Aplicacao.aspx?id=10032` para forçar o refresh do token

Após a troca, o cookie `SISEN_TOKEN` no domínio `www3.cav.receita.fazenda.gov.br` passa de `papel=TITULAR` para `papel=REPRESENTANTE_LEGAL`.

**Validação:** Se o token capturado não tiver `papel=REPRESENTANTE_LEGAL`, o CLI aborta com erro.

#### Estrutura do SISEN_TOKEN (JWT)

```json
{
  "aud": "https://www3.cav.receita.fazenda.gov.br/contribuinte",
  "exp": 1773676039,
  "iat": 1773674239,
  "user": {
    "ni": "11111122233",
    "nome": "FULANO DE TAL",
    "papel": "REPRESENTANTE_LEGAL",
    "representando": {
      "ni": "123456789101112",
      "nome": "EMPRESA LTDA",
      "tipoNi": "PJ"
    },
    "roles": ["ECAC"],
    "tipoNi": "PF"
  }
}
```

---

## API REST (após autenticação)

Todas as requisições abaixo usam o `SISEN_TOKEN` como Bearer token e os cookies capturados do browser. Os headers comuns são:

```
Authorization: Bearer <SISEN_TOKEN>
Accept: */*
Accept-Language: pt-BR,pt;q=0.9
Cache-Control: no-cache
Connection: keep-alive
DNT: 1
Origin: https://www3.cav.receita.fazenda.gov.br
Pragma: no-cache
Sec-Fetch-Dest: empty
Sec-Fetch-Mode: cors
Sec-Fetch-Site: same-origin
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...
sec-ch-ua: "Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "macOS"
```

---

### 4. Submissão do Requerimento

```
POST https://www3.cav.receita.fazenda.gov.br/contribuinte/servicos/requerimento
```

**Headers adicionais:**
```
Referer: https://www3.cav.receita.fazenda.gov.br/contribuinte/formulario/69248f628a51d597f886ac9d/internet/
```

**Content-Type:** `multipart/form-data` com um único campo `requerimento` do tipo `application/json`.

**Payload (`requerimento` field):**

```json
{
  "usuario": { "ni": "<CPF_DIGITS>" },
  "contribuinte": { "cnpj": "<CNPJ_DIGITS>" },
  "formulario": { "id": "69248f628a51d597f886ac9d" },
  "beneficio": { "id": "68b88fdf3089db035f17d57e" },
  "consolidacaoRespostas": [{
    "respostas": [
      { "campo": { "nome": "tipo-requerente", "tipo": "radio", ... }, "valor": "Pessoa Jurídica" },
      { "campo": { "nome": "data-inicial",    "tipo": "date",  ... }, "valor": "2026-01-01" },
      { "campo": { "nome": "data-final",      "tipo": "date",  ... }, "valor": "2026-12-31" },
      { "campo": { "nome": "ocupacao",        "tipo": "text",  ... }, "valor": "CNAE 62.04.0-00" },
      { "campo": { "nome": "fonte-pais",      "tipo": "country", ... }, "valor": "PORTUGAL" },
      { "campo": { "nome": "concordo-1",      "tipo": "checkbox", ... }, "valor": "true" },
      ...
    ]
  }]
}
```

O campo `consolidacaoRespostas[].respostas` contém **todos os campos do formulário** (incluindo os não preenchidos com `"## Não Informado ##"`). A ausência de qualquer campo faz o backend rejeitar silenciosamente (status fica em `TRANSMITIDO` para sempre). Os `vinculos` do campo `tipo-requerente` são strings JSON escapadas que controlam visibilidade condicional dos campos no frontend.

**Campos notáveis:**
- `data-final.valorMaximo = "0"` — restrição de data futura
- `script#1.validacoes = [{"tipo":"SCRIPT","valor":null}]` — script server-side de validação
- `dte#28` — campo de DTE (Domicílio Tributário Eletrônico), sem chaves `adicionais`/`vinculos`

**Resposta de sucesso (201):**
```json
{
  "protocolo": "000000.111111.2.2.333.1.8-33",
  "beneficio": {
    "nome": "ATESTADO DE RESIDÊNCIA FISCAL NO BRASIL",
    "codigo": "148"
  },
  "tipoRequerimento": "4"
}
```

---

### 5. Polling de status

```
GET https://www3.cav.receita.fazenda.gov.br/contribuinte/api/requerimento/list/
    ?ni=<CNPJ_DIGITS>
    &tiporequerimento=eletronico
    &offset=0
    &limit=10
```

**Headers adicionais:**
```
Referer: https://www3.cav.receita.fazenda.gov.br/contribuinte/formulario/69248f628a51d597f886ac9d/internet/
```

Executado a cada 15 segundos até que a `situacao` do protocolo seja `EM_ANALISE_DEFERIDO`. Timeout máximo: 600 segundos.

**Resposta:**
```json
{
  "items": [
    {
      "id": "69b82129e8a14756d512312314",
      "protocolo": "000000.111111.2.2.333.1.8-33",
      "movimentacoes": [
        { "id": "...", "tipo": "TRANSMITIDO",        "data": "2026-03-16T12:26:34..." },
        { "id": "...", "tipo": "EM_ANALISE_DEFERIDO", "data": "2026-03-16T12:26:38..." }
      ]
    }
  ]
}
```

> **Atenção:** Os IDs de movimentação retornados por este endpoint são **incorretos** para uso no ACK. Usar o endpoint de detalhe (próxima etapa) para obter os IDs reais.

**Situações possíveis:**

| Situação | Descrição |
|---|---|
| `TRANSMITIDO` | Aguardando processamento pelo servidor |
| `EM_ANALISE_DEFERIDO` | Deferido — pronto para ciência e download |
| `INDEFERIDO` | Indeferido — verificar motivo |
| `CANCELADO` | Cancelado |

---

### 6. Detalhe do Requerimento (Next.js)

```
GET https://www3.cav.receita.fazenda.gov.br/contribuinte/_next/data/<BUILD_ID>/requerimento/timeline/<REQUERIMENTO_ID>.json
    ?id=<REQUERIMENTO_ID>
```

**Headers adicionais:**
```
x-nextjs-data: 1
Referer: https://www3.cav.receita.fazenda.gov.br/contribuinte/requerimento/contribuinte/
```

O `BUILD_ID` é extraído dinamicamente da página HTML — está embutido no `<script id="__NEXT_DATA__">` de qualquer página do portal e-CAC. Exemplo: `UN-CkjYhvfArM06n-ZAk7`.

**Por que este endpoint e não `/api/requerimento/<id>/`?**
O endpoint REST direto retorna 404. O endpoint Next.js é a única forma de obter os IDs corretos das movimentações e o campo `podeTomarCiencia`.

**Resposta (simplificada):**
```json
{
  "pageProps": {
    "requerimento": {
      "id": "69b82129e8a1475123124fe212311",
      "protocolo": "000000.111111.2.2.333.1.8-33",
      "movimentacoes": [
        {
          "id": "69b8212ae8a14324234234234",
          "tipo": "TRANSMITIDO",
          "podeTomarCiencia": false,
          ...
        },
        {
          "id": "69b8212f2ddfdf2342342",
          "tipo": "EM_ANALISE_DEFERIDO",
          "podeTomarCiencia": true,
          "prazoCiencia": "2026-03-31T00:00:00.000-03:00",
          "despachoDecisorio": { ... },
          ...
        }
      ]
    }
  }
}
```

O CLI usa a movimentação onde `podeTomarCiencia == true` para obter o `id` correto para as etapas seguintes.

---

### 7. Registro de Ciência (ACK)

```
POST https://www3.cav.receita.fazenda.gov.br/contribuinte/servicos/requerimento/<REQUERIMENTO_ID>/movimentacoes/internet
```

**Headers adicionais:**
```
Content-Type: application/json
Referer: https://www3.cav.receita.fazenda.gov.br/contribuinte/requerimento/timeline/<REQUERIMENTO_ID>/
```

**Payload:**
```json
{ "idMovimentacao": "69b8212f2ec87e338a52234234235" }
```

O `idMovimentacao` deve vir do detalhe Next.js (etapa 6), não do endpoint de lista.

**Requisito crítico:** O `SISEN_TOKEN` deve ter `papel=REPRESENTANTE_LEGAL`. Com `papel=TITULAR` (contexto CPF) a API retorna `500` interno ou `422 UNPROCESSABLE_ENTITY`.

**Resposta de sucesso:** `200 OK` (corpo vazio ou `{}`).

---

### 8. Download do PDF

```
GET https://www3.cav.receita.fazenda.gov.br/contribuinte/api/relatorios/despacho/<REQUERIMENTO_ID>/<ID_MOVIMENTACAO>/
```

**Headers adicionais:**
```
Referer: https://www3.cav.receita.fazenda.gov.br/contribuinte/formulario/69248f628a51d2342342342/internet/
```

Usa o mesmo `ID_MOVIMENTACAO` da etapa 7.

**Resposta:** binário PDF (`Content-Type: application/pdf`), salvo em `atestado_<REQUERIMENTO_ID>.pdf`.

---

## Diagrama de fluxo

```
Browser (patchright + Chrome real)
  │
  ├─ GET  www3.cav/autenticacao          → página de login e-CAC
  ├─ ── clica "Acesso Gov BR"            → hCaptcha (se acionado)
  ├─ GET  sso.acesso.gov.br/...          → SSO gov.br
  ├─ ── preenche CPF + senha
  ├─ GET  cav.receita.fazenda.gov.br/ecac/#  → SPA e-CAC (token TITULAR)
  ├─ ── clica #btnPerfil, preenche CNPJ  → hCaptcha (se acionado)
  └─ GET  cav.receita.../eCAC/Aplicacao.aspx?id=10032  → token REPRESENTANTE_LEGAL

httpx (com SISEN_TOKEN + cookies)
  │
  ├─ POST www3.cav/contribuinte/servicos/requerimento
  │        └─ multipart: campo "requerimento" (JSON completo do formulário)
  │        └─ → 201 { protocolo, beneficio, tipoRequerimento }
  │
  ├─ GET  www3.cav/contribuinte/api/requerimento/list/?ni=...
  │        └─ polling a cada 15s até EM_ANALISE_DEFERIDO
  │
  ├─ GET  www3.cav/contribuinte/_next/data/<BUILD_ID>/requerimento/timeline/<ID>.json
  │        └─ → IDs corretos de movimentação + podeTomarCiencia
  │
  ├─ POST www3.cav/contribuinte/servicos/requerimento/<ID>/movimentacoes/internet
  │        └─ { idMovimentacao: "..." }
  │        └─ → 200 OK
  │
  └─ GET  www3.cav/contribuinte/api/relatorios/despacho/<ID>/<ID_MOV>/
           └─ → PDF binário → atestado_<ID>.pdf
```

---

## Notas sobre autenticação e sessão

- O `SISEN_TOKEN` expira em **30 minutos** (campo `exp` do JWT).
- O perfil Chrome persiste em `~/.atestado_api/chrome_profile/` — reutilizar o perfil entre execuções reduz a chance de hCaptcha.
- Ao usar `--headless`, o hCaptcha **não pode ser resolvido manualmente**. Recomendado apenas em ambientes onde o perfil já está "aquecido" e o hCaptcha não costuma ser acionado.
- O portal e-CAC usa múltiplas camadas de proteção anti-bot (Cloudflare, TS* cookies, fingerprint). O uso do binário real do Chrome + patchright + perfil persistente contorna essas proteções.
