import requests
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

url = "https://ics.fixtur.es/v2/fc-barcelona.ics"

print(f"Trying to download from: {url}")

# هدرهای کامل مرورگر با نسخه به‌روز
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/calendar,application/calendar+json,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="131", "Google Chrome";v="131"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
}

# ایجاد Session با Retry برای هندل کردن مشکلات شبکه
session = requests.Session()
retry_strategy = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
adapter = HTTPAdapter(max_retries=retry_strategy)
session.mount("https://", adapter)
session.headers.update(headers)

try:
    # افزایش تایم‌آوت به 30 ثانیه
    print("Test 3: With Headers & 30s Timeout...")
    r = session.get(url, timeout=30, verify=False)
    print(f"Success! Status: {r.status_code}, Size: {len(r.content)} bytes")
    if r.status_code == 200:
        print("Content Preview:")
        print(r.content[:200])  # نمایش ۲۰۰ بایت اول
except Exception as e:
    print(f"Test 3 Failed: {e}")
finally:
    session.close()