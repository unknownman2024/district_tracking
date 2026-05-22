from playwright.sync_api import sync_playwright

def get_seat_token():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)  # keep visible first
        context = browser.new_context()
        page = context.new_page()

        token_data = {}

        print("🌐 Opening login page...")
        page.goto("https://ticket.cineplexbd.com/login")

        # 🔥 listen for API response
        def handle_response(response):
            if "guest-login" in response.url:
                try:
                    data = response.json()
                    print("📦 Guest Login Response:", data)

                    if data.get("status") == "success":
                        token_data["token"] = data["data"]

                except:
                    pass

        page.on("response", handle_response)

        # wait for button
        page.wait_for_selector("button.guest-login")

        print("👆 Clicking Guest Login...")
        page.click("button.guest-login")

        # wait for API to complete
        page.wait_for_timeout(5000)

        browser.close()

        if "token" in token_data:
            return "Bearer " + token_data["token"]

        return None


# 🚀 RUN
seat_auth = get_seat_token()

print("\n🔥 FINAL SEAT_AUTH:")
print(seat_auth)
