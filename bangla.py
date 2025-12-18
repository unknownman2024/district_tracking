import requests
from bs4 import BeautifulSoup

HOME_URL = "https://ticket.cineplexbd.com/home"
LOGIN_API = "https://cineplex-ticket-api.cineplexbd.com/api/v1/guest-login"

session = requests.Session()
session.headers.update({
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36",
    "accept": "text/html,application/xhtml+xml",
})

print("🔹 STEP 1: Fetching home page")
r = session.get(HOME_URL, timeout=20)

print("STATUS:", r.status_code)
if r.status_code != 200:
    print("❌ Home page not accessible")
    exit(1)

soup = BeautifulSoup(r.text, "html.parser")

print("🔹 STEP 2: Searching Guest Login button")
btn = soup.select_one("button.guest-login")

if not btn:
    print("❌ Guest Login button NOT found")
    exit(1)

print("✅ Guest Login button FOUND")
print("Button text:", btn.get_text(strip=True))

print("🔹 STEP 3: Simulating click (POST attempt)")

payload = {
    # real site me ye JS se bharta hai
    # yaha empty attempt jaan-bujh ke
}

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://ticket.cineplexbd.com",
    "referer": HOME_URL,
}

resp = session.post(
    LOGIN_API,
    json=payload,
    headers=headers,
    timeout=20
)

print("LOGIN STATUS:", resp.status_code)
print("RESPONSE (first 300 chars):")
print(resp.text[:300])

if resp.status_code == 200:
    print("⚠️ Unexpected success (check response)")
else:
    print("✅ Click attempt executed (server-side block expected)")
