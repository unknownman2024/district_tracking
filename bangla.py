import requests

LOGIN_PAGE = "https://ticket.cineplexbd.com/login"
LOGIN_API  = "https://cineplex-ticket-api.cineplexbd.com/api/v1/guest-login"

session = requests.Session()
session.headers.update({
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36",
    "accept": "*/*",
    "origin": "https://ticket.cineplexbd.com",
    "referer": LOGIN_PAGE,
})

print("🔹 STEP 1: Visiting login page")
r = session.get(LOGIN_PAGE, timeout=20)

print("STATUS:", r.status_code)
print("FINAL URL:", r.url)

if r.status_code != 200:
    print("❌ Login page not accessible")
    exit(1)

print("✅ Login page loaded (JS content ignored, expected)")

# --------------------------------------------------

print("\n🔹 STEP 2: Attempting Guest Login (backend click simulation)")

payload = {
    # Real site fills this via JS + recaptcha
    # Leaving empty intentionally for test
}

resp = session.post(
    LOGIN_API,
    json=payload,
    allow_redirects=False,   # IMPORTANT: capture redirect
    timeout=20
)

print("LOGIN STATUS:", resp.status_code)

# Redirect detection
if "Location" in resp.headers:
    print("🔁 REDIRECT URL:", resp.headers["Location"])
else:
    print("ℹ️ No redirect header")

print("\nRESPONSE HEADERS:")
for k, v in resp.headers.items():
    print(f"{k}: {v}")

print("\nRESPONSE BODY (first 300 chars):")
print(resp.text[:300])

print("\n✅ Guest-login click ATTEMPT completed (block expected)")
