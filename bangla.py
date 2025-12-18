from playwright.sync_api import sync_playwright
import requests
import json

LOGIN_URL = "https://ticket.cineplexbd.com/login"
API_KEYWORD = "/api/v1/guest-login"
SHOWDATE_URL = "https://cineplex-ticket-api.cineplexbd.com/api/v1/get-showdate"

def get_guest_token():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        print("🔹 Visiting login page...")
        page.goto(LOGIN_URL, wait_until="networkidle")

        page.wait_for_selector(
            "button.btn.btn-button.guest-login.btn-block",
            timeout=15000
        )

        print("🔹 Clicking Guest Login & waiting for API...")

        with page.expect_response(
            lambda r: API_KEYWORD in r.url and r.status == 200,
            timeout=15000
        ) as resp_info:
            page.click("button.btn.btn-button.guest-login.btn-block")

        response = resp_info.value
        data = response.json()

        print("📦 Guest Login Response:")
        print(json.dumps(data, indent=4))

        token = data.get("data", {}).get("token")
        if not token:
            raise RuntimeError("❌ Token not found")

        browser.close()
        return token


def get_show_dates(bearer_token):
    headers = {
        "accept": "application/json, text/plain, */*",
        "content-type": "application/json;charset=UTF-8",
        "authorization": f"Bearer {bearer_token}",
        "appsource": "web",
        "origin": "https://ticket.cineplexbd.com",
        "referer": "https://ticket.cineplexbd.com/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/143",
        "device-key": "dafd2b9ab4d02a9e120932ea62e4fd73307ced96193cb4e197b31e4c5d51e024"
    }

    payload = {
        "location": 1
    }

    print("🔹 Calling get-showdate API...")
    r = requests.post(SHOWDATE_URL, headers=headers, json=payload, timeout=20)

    print("📡 Status:", r.status_code)
    r.raise_for_status()

    print("\n📦 RAW JSON RESPONSE:")
    print(json.dumps(r.json(), indent=4))


if __name__ == "__main__":
    token = get_guest_token()
    print("\n🔑 BEARER TOKEN:")
    print("Bearer", token)

    get_show_dates(token)
