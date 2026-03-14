"""
hCaptcha solving via Capsolver REST API.
https://capsolver.com — create an account and fund it to get an API key.
"""

import re
import time
import httpx
from patchright.async_api import Page

CAPSOLVER_API = "https://api.capsolver.com"


def _extract_sitekey(html: str) -> str | None:
    m = re.search(r'data-sitekey=["\']([^"\']+)["\']', html)
    return m.group(1) if m else None


def _solve_hcaptcha_sync(api_key: str, sitekey: str, page_url: str) -> str:
    """
    Submit hCaptcha task to Capsolver and poll until solved.
    Raises RuntimeError on failure.
    """
    with httpx.Client(timeout=30) as client:
        # Create task
        payload = {
            "clientKey": api_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": page_url,
                "websiteKey": sitekey,
            },
        }
        print(f"[captcha] Sending to Capsolver: {payload}")
        resp = client.post(f"{CAPSOLVER_API}/createTask", json=payload)
        print(f"[captcha] Capsolver response {resp.status_code}: {resp.text}")
        resp.raise_for_status()
        data = resp.json()

        if data.get("errorId"):
            raise RuntimeError(f"Capsolver createTask error: {data.get('errorDescription')}")

        task_id = data["taskId"]
        print(f"[captcha] Task created: {task_id} — polling for solution...")

        # Poll for result (up to 120s)
        for _ in range(40):
            time.sleep(3)
            resp = client.post(f"{CAPSOLVER_API}/getTaskResult", json={
                "clientKey": api_key,
                "taskId": task_id,
            })
            resp.raise_for_status()
            result = resp.json()

            if result.get("errorId"):
                raise RuntimeError(f"Capsolver getTaskResult error: {result.get('errorDescription')}")

            if result.get("status") == "ready":
                token = result["solution"]["gRecaptchaResponse"]
                print(f"[captcha] Solved! Token length={len(token)}")
                return token

        raise RuntimeError("Capsolver timed out waiting for hCaptcha solution.")


async def solve_and_submit_hcaptcha(page: Page, api_key: str, js_callback: str) -> None:
    """
    Solve hCaptcha on the current page and trigger the site's JS callback.
    """
    page_url = page.url

    # Extract sitekey — try data-sitekey first, then iframe src
    html = await page.content()
    sitekey = _extract_sitekey(html)

    if not sitekey:
        src = await page.locator('iframe[src*="hcaptcha.com"]').first.get_attribute("src")
        if src:
            m = re.search(r'sitekey=([^&#]+)', src)
            sitekey = m.group(1) if m else None

    if not sitekey:
        raise RuntimeError("Could not find hCaptcha sitekey on page.")

    print(f"[captcha] sitekey={sitekey[:16]}... | page={page_url}")

    token = _solve_hcaptcha_sync(api_key, sitekey, page_url)

    # Inject token into all hCaptcha response fields
    await page.evaluate(f"""
        document.querySelectorAll('[name="h-captcha-response"], [name="g-recaptcha-response"]')
            .forEach(el => el.value = {repr(token)});
    """)

    # Trigger the site's own submission callback
    await page.evaluate(js_callback)
    print(f"[captcha] Callback '{js_callback}' triggered.")
