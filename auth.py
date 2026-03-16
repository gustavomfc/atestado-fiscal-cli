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
import base64
import json as _json
from pathlib import Path
from patchright.async_api import async_playwright, Page, BrowserContext

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
    print("[auth] Waiting for e-CAC login page...")
    await page.wait_for_load_state("domcontentloaded")
    govbr_btn = page.locator('input[type="image"][alt="Acesso Gov BR"]')
    await govbr_btn.wait_for(state="visible", timeout=10_000)
    await govbr_btn.click()
    print("[auth] Gov BR button clicked.")


async def _login_govbr(page: Page, cpf: str, password: str) -> None:
    print(f"[auth] Waiting for redirect to gov.br (up to {CAPTCHA_TIMEOUT_MS // 1000}s)...")
    await page.wait_for_url(f"**{GOVBR_SSO_HOST}**", timeout=CAPTCHA_TIMEOUT_MS)
    print("[auth] Redirected to gov.br SSO.")

    await page.wait_for_selector('input[name="accountId"]', timeout=10_000)
    await page.type('input[name="accountId"]', re.sub(r"\D", "", cpf), delay=80)
    await page.click('button[type="submit"]')

    await page.wait_for_selector('input[name="password"]', timeout=10_000)
    await page.type('input[name="password"]', password, delay=80)
    await page.click('button[type="submit"]')
    print("[auth] Credentials submitted, waiting for redirect to e-CAC...")


async def _switch_cnpj_profile(page: Page, cnpj: str) -> str | None:
    """
    Switch e-CAC profile to CNPJ context.
    Returns the REPRESENTANTE_LEGAL SISEN_TOKEN if captured from a redirect
    response Set-Cookie header, or None if not intercepted (fall back to cookies).
    """
    print(f"[auth] Switching profile to CNPJ {cnpj}...")
    await page.wait_for_url("**cav.receita.fazenda.gov.br**", timeout=20_000)

    # After the profile switch, cav sends an HTTP redirect (302) to www3 with a
    # special token parameter in the URL. Intercepting that Location URL lets us
    # navigate to it explicitly even if the browser didn't follow it automatically.
    redirect_urls: list[str] = []
    token_cookies: list[str] = []

    async def _on_response(response) -> None:
        if response.status in (301, 302, 303, 307, 308):
            location = response.headers.get("location", "")
            if "www3.cav.receita.fazenda.gov.br" in location:
                print(f"[auth] Captured www3 redirect: {location[:120]}")
                redirect_urls.append(location)
        # Also try to grab SISEN_TOKEN from Set-Cookie (belt-and-suspenders)
        raw = response.headers.get("set-cookie", "")
        if "SISEN_TOKEN" in raw:
            m = re.search(r"SISEN_TOKEN=([^;,\s]+)", raw)
            if m:
                tok = m.group(1)
                papel, _ = _jwt_context(tok)
                print(f"[auth] Intercepted SISEN_TOKEN from Set-Cookie (papel={papel})")
                if papel == "REPRESENTANTE_LEGAL":
                    token_cookies.append(tok)

    page.on("response", _on_response)

    await page.click("#btnPerfil")
    await page.wait_for_selector("#txtNIPapel", timeout=10_000)
    await page.type("#txtNIPapel", re.sub(r"\D", "", cnpj), delay=80)
    await page.click('input.submit[value="Alterar"]')

    print(f"[auth] Profile captcha triggered — waiting up to {CAPTCHA_TIMEOUT_MS // 1000}s...")

    # Wait for captcha + switch. The SPA may redirect to www3 on its own.
    try:
        await page.wait_for_url("**www3.cav.receita.fazenda.gov.br**", timeout=CAPTCHA_TIMEOUT_MS)
        await page.wait_for_load_state("networkidle", timeout=20_000)
        page.remove_listener("response", _on_response)
        print(f"[auth] Profile switched to CNPJ {_format_cnpj(cnpj)} (natural redirect to www3)")
        return None  # SISEN_TOKEN in cookies will be REPRESENTANTE_LEGAL

    except Exception:
        # Auto-redirect didn't happen — browser stayed on cav
        pass

    page.remove_listener("response", _on_response)

    # If we captured an HTTP 302 redirect URL to www3, follow it to trigger token exchange
    if redirect_urls:
        target = redirect_urls[-1]
        print(f"[auth] Following intercepted www3 redirect...")
        try:
            await page.goto(target, wait_until="commit", timeout=30_000)
        except Exception:
            pass
        await page.wait_for_load_state("networkidle", timeout=20_000)
        print(f"[auth] Profile switched to CNPJ {_format_cnpj(cnpj)} (via intercepted redirect)")
        return None

    # If we grabbed the token directly from Set-Cookie, return it
    if token_cookies:
        print(f"[auth] Profile switched to CNPJ {_format_cnpj(cnpj)} (token from Set-Cookie)")
        return token_cookies[-1]

    # Last resort: navigate to www3 directly (SISEN_TOKEN may still be TITULAR)
    print(f"[auth] WARNING: no www3 redirect captured — navigating directly (token may be TITULAR)")
    try:
        await page.goto(ECAC_URL, wait_until="commit", timeout=30_000)
    except Exception:
        pass
    await page.wait_for_load_state("networkidle", timeout=20_000)
    print(f"[auth] Profile switched to CNPJ {_format_cnpj(cnpj)}")
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
            slow_mo=150,
            locale="pt-BR",
            timezone_id="America/Sao_Paulo",
            viewport={"width": 1280, "height": 800},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = await context.new_page()

        print(f"[auth] Opening e-CAC login: {ECAC_LOGIN_URL}")
        await page.goto(ECAC_LOGIN_URL)

        await _click_govbr_button(page)
        await _login_govbr(page, cpf, password)
        intercepted_token = await _switch_cnpj_profile(page, cnpj)

        raw_cookies = await context.cookies()
        cookies = {c["name"]: c["value"] for c in raw_cookies}
        token = intercepted_token or cookies.get("SISEN_TOKEN", "")

        await context.close()

    papel, representando_ni = _jwt_context(token)
    print(f"[auth] Token context — papel={papel}, representando={representando_ni} (tipoNi={'PJ' if representando_ni != re.sub(r'\\D','',cpf) else 'PF'})")

    if papel != "REPRESENTANTE_LEGAL":
        print("[auth] WARNING: token is not in CNPJ context — profile switch may not have completed.")

    print(f"[auth] Full token (length={len(token)}):\n{token}\n")
    return token, cookies
