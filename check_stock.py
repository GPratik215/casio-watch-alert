"""
Casio watch stock/availability checker.

Two kinds of URLs are watched, checked differently:

1. RESELLER_URLS (casiostore.bhawar.com) - these print the literal
   text "Sold out" in the page HTML when unavailable. We check for
   that exact phrase disappearing - a precise, low-false-alarm signal.

2. OFFICIAL_URLS (casio.com) - these don't show plain stock text in
   the raw HTML (likely set by client-side JS), so we fall back to
   hashing the whole page and flagging ANY change. Noisier, but
   won't silently miss a real restock.

Either way, on a real signal it sends a free push notification via
ntfy.sh with the link straight to your phone.
"""

import hashlib
import json
import os
import sys
import urllib.request

import requests

STATE_FILE = "state.json"

# Reseller pages - explicit "Sold out" text, precise signal
RESELLER_URLS = [
    "https://casiostore.bhawar.com/products/mtp-b195d-1a",
    "https://casiostore.bhawar.com/products/mtp-b195l-1a",
]
SOLD_OUT_PHRASE = "XXXTestXXX"

# Official Casio pages - no plain stock text, fall back to full-page diff
OFFICIAL_URLS = [
    "https://www.casio.com/in/watches/casio/product.MTP-B195D-1AV/",
    "https://www.casio.com/in/watches/casio/product.MTP-B195L-1AV/",
]

# Set this as a GitHub Actions secret named NTFY_TOPIC (see README).
# It should be a long, hard-to-guess string - anyone who knows your
# topic name can read your notifications, since ntfy.sh topics are
# public by name.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0 Safari/537.36"
    )
}


def fetch_page(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def notify(url: str, reason: str) -> None:
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set - skipping notification, just logging.")
        print(f"ALERT ({reason}): {url}")
        return
    print(f"Attempting ntfy push to topic: '{NTFY_TOPIC}' (len={len(NTFY_TOPIC)})")
    msg = f"{reason}\n{url}".encode("utf-8")
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg,
        headers={
            "Title": "Casio watch may be back in stock!",
            "Priority": "urgent",
            "Tags": "watch,rotating_light",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"ntfy response status: {resp.status}")
            print(f"ntfy response body: {resp.read().decode('utf-8', errors='replace')}")
    except Exception as e:
        print(f"ntfy request FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        raise


def check_reseller_url(url: str, state: dict) -> bool:
    """Returns True if this run detected a real restock signal."""
    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return False

    is_sold_out_now = SOLD_OUT_PHRASE in html
    was_sold_out_before = state.get(url)  # True/False/None(first run)

    if was_sold_out_before is None:
        print(f"First run for {url} - currently {'SOLD OUT' if is_sold_out_now else 'IN STOCK'}.")
    elif was_sold_out_before and not is_sold_out_now:
        print(f"RESTOCK DETECTED: {url}")
        notify(url, "Back in stock on Bhawar Casio store!")
        state[url] = is_sold_out_now
        return True
    else:
        print(f"No change ({'sold out' if is_sold_out_now else 'in stock'}): {url}")

    state[url] = is_sold_out_now
    return False


def check_official_url(url: str, state: dict) -> bool:
    """Full-page-diff fallback for pages with no plain stock text."""
    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return False

    current_hash = hashlib.sha256(html.encode("utf-8")).hexdigest()
    previous_hash = state.get(url)

    if previous_hash is None:
        print(f"First run for {url} - recording baseline.")
    elif previous_hash != current_hash:
        print(f"CHANGE DETECTED: {url}")
        notify(url, "Official Casio page changed - check stock")
        state[url] = current_hash
        return True
    else:
        print(f"No change: {url}")

    state[url] = current_hash
    return False


def main() -> None:
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    changed_any = False
    for url in RESELLER_URLS:
        if check_reseller_url(url, state):
            changed_any = True
    for url in OFFICIAL_URLS:
        if check_official_url(url, state):
            changed_any = True

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    if changed_any:
        print("At least one restock/change detected this run.")


if __name__ == "__main__":
    main()
