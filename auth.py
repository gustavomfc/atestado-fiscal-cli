"""
Handles the full authentication flow:
  1. Open e-CAC login page using real Chrome binary + persistent profile
  2. Click the "Acesso Gov BR" button
  3. Complete gov.br SSO login with CPF + password
  4. Switch e-CAC profile to CNPJ representative
  5. Wait for the natural redirect to www3 and capture CNPJ-context SISEN_TOKEN
"""

import re
import sys
import asyncio
import random
import base64
import json as _json
import logging
from pathlib import Path
from patchright.async_api import async_playwright, Page, BrowserContext

log = logging.getLogger("auth")

ECAC_URL = "https://www3.cav.receita.fazenda.gov.br/contribuinte"
ECAC_LOGIN_URL = "https://www3.cav.receita.fazenda.gov.br/autenticacao"
GOVBR_SSO_HOST = "sso.acesso.gov.br"

CAPTCHA_TIMEOUT_MS = 120_000  # 2 minutes

_CHROME_PATHS = {
    "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "win32":  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "linux":  "/usr/bin/google-chrome",
}

_PROFILE_DIR = Path.home() / ".atestado_api" / "chrome_profile"

_VIEWPORTS = [
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1280, "height": 720},
    {"width": 1920, "height": 1080},
]


async def _human_delay(min_ms: int = 400, max_ms: int = 1200) -> None:
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _move_mouse_randomly(page: Page, steps: int = 4) -> None:
    """Drift the mouse through random positions before an interaction."""
    vp = page.viewport_size or {"width": 1366, "height": 768}
    for _ in range(steps):
        x = random.randint(80, vp["width"] - 80)
        y = random.randint(80, vp["height"] - 80)
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.05, 0.18))


def _chrome_executable() -> str:
    path = _CHROME_PATHS.get(sys.platform)
    if not path or not Path(path).exists():
        raise RuntimeError(
            f"Google Chrome not found at '{path}'.\n"
            "Install Chrome or set the correct path in auth.py:_CHROME_PATHS."
        )
    return path


def _decode_jwt(token: str) -> dict:
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        return _json.loads(base64.b64decode(part))
    except Exception:
        return {}


def _jwt_context(token: str) -> tuple[str, str]:
    payload = _decode_jwt(token)
    user = payload.get("user", {})
    return user.get("papel", "?"), user.get("representando", {}).get("ni", "?")


async def _click_govbr_button(page: Page) -> None:
    log.debug("Waiting for e-CAC login page...")
    await page.wait_for_load_state("domcontentloaded")
    await _human_delay(800, 1800)
    await _move_mouse_randomly(page)
    govbr_btn = page.locator('input[type="image"][alt="Acesso Gov BR"]')
    await govbr_btn.wait_for(state="visible", timeout=10_000)
    await _human_delay(300, 700)
    await govbr_btn.click()
    log.debug("Gov BR button clicked.")


async def _login_govbr(page: Page, cpf: str, password: str) -> None:
    log.info("Aguardando redirecionamento para gov.br SSO...")
    await page.wait_for_url(f"**{GOVBR_SSO_HOST}**", timeout=CAPTCHA_TIMEOUT_MS)
    log.debug("Redirected to gov.br SSO.")

    await _human_delay(600, 1400)
    await _move_mouse_randomly(page)
    await page.wait_for_selector('input[name="accountId"]', timeout=10_000)
    await page.click('input[name="accountId"]')
    await _human_delay(200, 500)
    await page.type('input[name="accountId"]', re.sub(r"\D", "", cpf), delay=random.randint(60, 130))
    await _human_delay(400, 900)
    await page.click('button[type="submit"]')

    await _human_delay(500, 1000)
    await page.wait_for_selector('input[name="password"]', timeout=10_000)
    await page.click('input[name="password"]')
    await _human_delay(200, 500)
    await page.type('input[name="password"]', password, delay=random.randint(60, 130))
    await _human_delay(400, 900)
    await page.click('button[type="submit"]')
    log.debug("Credentials submitted.")


async def _switch_cnpj_profile(page: Page, cnpj: str) -> str | None:
    """
    Switch e-CAC profile to CNPJ context.
    Returns the REPRESENTANTE_LEGAL SISEN_TOKEN if captured from a redirect
    response Set-Cookie header, or None if not intercepted (fall back to cookies).
    """
    log.info("Alternando perfil para CNPJ %s...", _format_cnpj(cnpj))
    await page.wait_for_url("**cav.receita.fazenda.gov.br**", timeout=20_000)

    redirect_urls: list[str] = []
    token_cookies: list[str] = []

    async def _on_response(response) -> None:
        if response.status in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if "www3.cav.receita.fazenda.gov.br" in location:
                log.debug("Captured www3 redirect: %s", location[:120])
                redirect_urls.append(location)
        raw = response.headers.get("set-cookie", "")
        if "SISEN_TOKEN" in raw:
            m = re.search(r"SISEN_TOKEN=([^;,\s]+)", raw)
            if m:
                tok = m.group(1)
                papel, _ = _jwt_context(tok)
                log.debug("Intercepted SISEN_TOKEN from Set-Cookie (papel=%s)", papel)
                if papel == "REPRESENTANTE_LEGAL":
                    token_cookies.append(tok)

    page.on("response", _on_response)

    await page.click("#btnPerfil")
    await page.wait_for_selector("#txtNIPapel", timeout=10_000)
    await page.type("#txtNIPapel", re.sub(r"\D", "", cnpj), delay=80)
    await page.click('input.submit[value="Alterar"]')

    log.info("Resolvendo captcha do perfil (aguarde)...")

    # Wait for the captcha to be solved and the switch to complete.
    await page.wait_for_load_state("networkidle", timeout=CAPTCHA_TIMEOUT_MS)

    # Give 5s for a natural www3 redirect (rare but possible).
    try:
        await page.wait_for_url("**www3.cav.receita.fazenda.gov.br**", timeout=5_000)
        await page.wait_for_load_state("networkidle", timeout=20_000)
        page.remove_listener("response", _on_response)
        log.debug("Profile switched via natural redirect to www3.")
        return None
    except Exception:
        pass

    page.remove_listener("response", _on_response)

    # If we intercepted a direct token from Set-Cookie, return it.
    if token_cookies:
        log.debug("Token captured from Set-Cookie.")
        return token_cookies[-1]

    # Navigate to the CNPJ profile URL — this triggers the token exchange on cav.
    cnpj_profile_url = "https://cav.receita.fazenda.gov.br/eCAC/Aplicacao.aspx?id=10032"
    log.debug("Navigating to CNPJ profile URL to capture token...")
    try:
        await page.goto(cnpj_profile_url, wait_until="commit", timeout=30_000)
    except Exception:
        pass
    await page.wait_for_load_state("networkidle", timeout=20_000)
    return None


def _format_cnpj(cnpj: str) -> str:
    c = re.sub(r"\D", "", cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


async def get_auth_session(
    cpf: str,
    password: str,
    cnpj: str,
    headless: bool = False,
    capsolver_key: str | None = None,
) -> tuple[str, dict]:
    """
    Drive real Chrome through the full auth + profile-switch flow.
    Returns (bearer_token, cookies) valid for the CNPJ context.
    """
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        context: BrowserContext = await pw.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            executable_path=_chrome_executable(),
            headless=headless,
            slow_mo=random.randint(120, 200),
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport=random.choice(_VIEWPORTS),
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await context.new_page()

        log.info("Abrindo e-CAC: %s", ECAC_LOGIN_URL)
        await page.goto(ECAC_LOGIN_URL)

        await _click_govbr_button(page)
        await _login_govbr(page, cpf, password)
        intercepted_token = await _switch_cnpj_profile(page, cnpj)

        raw_cookies = await context.cookies()
        cookies = {c["name"]: c["value"] for c in raw_cookies}
        token = intercepted_token or cookies.get("SISEN_TOKEN", "")

        await context.close()

    papel, representando_ni = _jwt_context(token)
    log.debug("Token context — papel=%s, representando=%s", papel, representando_ni)
    log.debug("Full token (length=%d):\n%s", len(token), token)

    if papel != "REPRESENTANTE_LEGAL":
        raise RuntimeError(
            f"Token capturado está em contexto '{papel}' (esperado: REPRESENTANTE_LEGAL). "
            "A troca de perfil para CNPJ não foi concluída."
        )

    return token, cookies
