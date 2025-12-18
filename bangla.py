from playwright.sync_api import sync_playwright

URL = "https://ticket.cineplexbd.com/login"

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
    with page.expect_navigation(timeout=15000):
        page.click("button.btn.btn-button.guest-login.btn-block")

    print("✅ Click done")
    print("🔁 Redirected / Final URL:", page.url)

    browser.close()
