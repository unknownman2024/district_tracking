import requests

URL = "https://ticket.cineplexbd.com/home"

headers = {
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/120 Safari/537.36",
    "accept": "text/html,application/xhtml+xml",
}

try:
    r = requests.get(URL, headers=headers, timeout=20)

    print("STATUS:", r.status_code)
    print("FINAL URL:", r.url)
    print("RESPONSE SIZE:", len(r.text))

    if r.status_code == 200:
        print("✅ BD HOME PAGE ACCESSIBLE")
    else:
        print("⚠ Unexpected status")

except Exception as e:
    print("❌ REQUEST FAILED")
    print(e)
