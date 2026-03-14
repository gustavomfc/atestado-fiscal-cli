"""
Handles the full authentication flow:
  1. Open e-CAC login page using real Chrome binary + persistent profile
  2. Click the "Acesso Gov BR" button
  3. Complete gov.br SSO login with CPF + password
  4. Switch e-CAC profile to CNPJ representative
  5. Capture the Bearer token from the post-switch requests
"""

import re
import sys
import base64
import json as _json
from pathlib import Path
from patchright.async_api import async_playwright, Page, BrowserContext, Response

ECAC_URL = "https://www3.cav.receita.fazenda.gov.br/contribuinte"
ECAC_LOGIN_URL = "https://cav.receita.fazenda.gov.br/autenticacao/login"
GOVBR_SSO_HOST = "sso.acesso.gov.br"

CAPTCHA_TIMEOUT_MS = 120_000  # 2 minutes — for manual captcha fallback

# Real Chrome binary paths per OS
_CHROME_PATHS = {
    "darwin": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "win32":  r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "linux":  "/usr/bin/google-chrome",
}

# Dedicated Chrome profile directory (separate from the user's real profile)
_PROFILE_DIR = Path.home() / ".atestado_api" / "chrome_profile"


def _chrome_executable() -> str:
    path = _CHROME_PATHS.get(sys.platform)
    if not path or not Path(path).exists():
        raise RuntimeError(
            f"Google Chrome not found at '{path}'.\n"
            "Install Chrome or set the correct path in auth.py:_CHROME_PATHS."
        )
    return path


async def _click_govbr_button(page: Page) -> None:
    print("[auth] Waiting for e-CAC login page...")
    await page.wait_for_load_state("domcontentloaded")
    govbr_btn = page.locator('input[type="image"][alt="Acesso Gov BR"]')
    await govbr_btn.wait_for(state="visible", timeout=10_000)
    await govbr_btn.click()
    print("[auth] Gov BR button clicked.")


async def _wait_for_govbr_redirect(page: Page) -> None:
    """Wait for hCaptcha to pass and the redirect to gov.br SSO to happen."""
    print(f"[auth] Waiting for redirect to gov.br (up to {CAPTCHA_TIMEOUT_MS // 1000}s)...")
    await page.wait_for_url(f"**{GOVBR_SSO_HOST}**", timeout=CAPTCHA_TIMEOUT_MS)
    print("[auth] Redirected to gov.br SSO.")


async def _login_govbr(page: Page, cpf: str, password: str) -> None:
    await page.wait_for_selector('input[name="accountId"]', timeout=10_000)
    await page.type('input[name="accountId"]', re.sub(r"\D", "", cpf), delay=80)
    await page.click('button[type="submit"]')  # "Continuar"

    await page.wait_for_selector('input[name="password"]', timeout=10_000)
    await page.type('input[name="password"]', password, delay=80)
    await page.click('button[type="submit"]')  # "Entrar"

    print("[auth] Credentials submitted, waiting for redirect to e-CAC...")


async def _switch_cnpj_profile(page: Page, cnpj: str) -> None:
    """Switch e-CAC profile to CNPJ and wait for the switch to complete."""
    print(f"[auth] Switching profile to CNPJ {cnpj}...")
    await page.wait_for_url("**cav.receita.fazenda.gov.br**", timeout=20_000)

    # Intercept responses from the e-CAC API to capture the new token
    # issued after the profile switch. The switch endpoint returns the new JWT.
    captured: list[str] = []

    async def _on_response(response: Response) -> None:
        if "cav.receita.fazenda.gov.br" not in response.url:
            return
        set_cookie = response.headers.get("set-cookie", "")
        ct = response.headers.get("content-type", "")
        print(f"[auth:debug] {response.status} {response.url}")
        if set_cookie:
            print(f"[auth:debug]   Set-Cookie: {set_cookie[:200]}")
        try:
            if "json" in ct:
                body = await response.json()
                print(f"[auth:debug]   Body keys: {list(body.keys()) if isinstance(body, dict) else type(body).__name__}")
                token = body.get("token") or body.get("access_token") or body.get("sisen_token")
                if token and _is_cnpj_token(token, cnpj):
                    captured.append(token)
                    print(f"[auth] CNPJ-context token intercepted from response body.")
        except Exception:
            pass

    page.on("response", _on_response)

    await page.click("#btnPerfil")

    cnpj_digits = re.sub(r"\D", "", cnpj)
    await page.wait_for_selector("#txtNIPapel", timeout=10_000)
    await page.type("#txtNIPapel", cnpj_digits, delay=80)

    await page.click('input.submit[value="Alterar"]')

    print(f"[auth] Profile captcha triggered — waiting up to {CAPTCHA_TIMEOUT_MS // 1000}s...")

    # Wait for the switch to redirect the browser to www3 (the main e-CAC app).
    # The switch always ends with a redirect to www3.cav.receita.fazenda.gov.br.
    await page.wait_for_url("**www3.cav.receita.fazenda.gov.br**", timeout=CAPTCHA_TIMEOUT_MS)
    await page.wait_for_load_state("networkidle", timeout=20_000)
    page.remove_listener("response", _on_response)
    print(f"[auth] Profile switched to CNPJ {_format_cnpj(cnpj)} — now on www3")


def _format_cnpj(cnpj: str) -> str:
    c = re.sub(r"\D", "", cnpj)
    return f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"


def _is_cnpj_token(token: str, cnpj: str) -> bool:
    """Return True if the JWT payload shows REPRESENTANTE_LEGAL for the given CNPJ."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = _json.loads(base64.b64decode(part))
        user = payload.get("user", {})
        representando_ni = user.get("representando", {}).get("ni", "")
        return user.get("papel") == "REPRESENTANTE_LEGAL" and representando_ni == re.sub(r"\D", "", cnpj)
    except Exception:
        return False


def _decode_jwt_context(token: str) -> tuple[str, str]:
    """Return (papel, representando_ni) from a JWT. Returns ('?','?') on failure."""
    try:
        part = token.split(".")[1]
        part += "=" * (-len(part) % 4)
        payload = _json.loads(base64.b64decode(part))
        user = payload.get("user", {})
        return user.get("papel", "?"), user.get("representando", {}).get("ni", "?")
    except Exception:
        return "?", "?"


async def get_auth_session(
    cpf: str,
    password: str,
    cnpj: str,
    headless: bool = False,
    capsolver_key: str | None = None,  # kept for future use
) -> tuple[str, dict]:
    """
    Drive real Chrome through the full auth + profile-switch flow.
    Returns (bearer_token, cookies) valid for the CNPJ context.
    """
    _PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # Use the real Chrome binary + a persistent dedicated profile.
        # This makes the browser fingerprint identical to regular Chrome,
        # which prevents hCaptcha from triggering.
        context: BrowserContext = await pw.chromium.launch_persistent_context(
            user_data_dir=str(_PROFILE_DIR),
            executable_path=_chrome_executable(),
            headless=headless,
            slow_mo=150,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await context.new_page()

        # 1. Navigate to e-CAC login
        print(f"[auth] Opening e-CAC login: {ECAC_LOGIN_URL}")
        await page.goto(ECAC_LOGIN_URL)

        # 2. Click gov.br button — with real Chrome, hCaptcha should not trigger
        await _click_govbr_button(page)
        await _wait_for_govbr_redirect(page)

        # 3. gov.br login
        await _login_govbr(page, cpf, password)

        # 4. Switch to CNPJ profile on cav.receita.fazenda.gov.br
        await _switch_cnpj_profile(page, cnpj)

        # 5. The switch redirects to www3 automatically (handled inside _switch_cnpj_profile).
        #    Collect cookies — SISEN_TOKEN on www3 is now CNPJ-context.
        raw_cookies = await context.cookies()
        cookies = {c["name"]: c["value"] for c in raw_cookies}
        token = cookies.get("SISEN_TOKEN", "")

        await context.close()

    papel, representando_ni = _decode_jwt_context(token)
    print(f"[auth] Token context — papel={papel}, representando={representando_ni}")
    if papel != "REPRESENTANTE_LEGAL":
        raise RuntimeError(
            f"Token is in '{papel}' context, expected REPRESENTANTE_LEGAL. "
            "The CNPJ profile switch did not complete correctly."
        )

    print(f"[auth] Full token (length={len(token)}):\n{token}\n")
    return token, cookies
