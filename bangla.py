from playwright.sync_api import sync_playwright
import json

URL = "https://ticket.cineplexbd.com/login"
API_KEYWORD = "/api/v1/guest-login"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    print("🔹 STEP 1: Visiting login page")
    page.goto(URL, wait_until="networkidle")
    print("Current URL:", page.url)

    print("🔹 STEP 2: Waiting for Guest Login button")
    page.wait_for_selector(
        "button.btn.btn-button.guest-login.btn-block",
        timeout=15000
    )

    print("🔹 STEP 3: Clicking Guest Login button")

    # ---- WAIT FOR API RESPONSE ----
    with page.expect_response(
        lambda r: API_KEYWORD in r.url and r.status == 200,
        timeout=15000
    ) as response_info:
        page.click("button.btn.btn-button.guest-login.btn-block")

    response = response_info.value

    print("✅ Guest login API hit:", response.url)

    # ---- PARSE JSON RESPONSE ----
    try:
        data = response.json()
    except Exception as e:
        print("❌ Failed to parse JSON:", e)
        browser.close()
        exit()

    print("\n📦 FULL API RESPONSE:")
    print(json.dumps(data, indent=4))

    # ---- EXTRACT TOKEN ----
    token = data.get("data", {}).get("token")
    if token:
        print("\n🔑 GUEST TOKEN:", token)
    else:
        print("\n⚠️ Token not found!")

    print("\n🔁 Final Page URL:", page.url)

    browser.close()
