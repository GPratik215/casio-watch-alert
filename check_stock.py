"""
Casio watch stock/availability checker.

Watches one or more Casio product pages for ANY change on the page
(since Casio doesn't show a plain "Out of Stock" text label in the
raw HTML - the buy button state is likely set by client-side JS).
On the first run for a URL it just records a baseline. On every
run after that, if the page content differs from last time, it
sends you a free push notification via ntfy.sh with the link.

Because this watches for "any change," it may occasionally notify
you about something unrelated (a banner update, price text, etc).
That's a deliberate trade-off: it's better to get one extra ping
than to silently miss a real restock. Open the link and check.
"""

import hashlib
import json
import os
import sys
import urllib.request

import requests

STATE_FILE = "state.json"

# Add/remove watch URLs here
URLS = [
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


def fetch_hash(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return hashlib.sha256(resp.text.encode("utf-8")).hexdigest()


def notify(url: str) -> None:
    if not NTFY_TOPIC:
        print("NTFY_TOPIC not set - skipping notification, just logging.")
        print(f"CHANGE DETECTED: {url}")
        return
    msg = f"Casio watch page changed - check stock:\n{url}".encode("utf-8")
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=msg,
        headers={
            "Title": "Casio watch page changed",
            "Priority": "urgent",
            "Tags": "watch",
        },
    )
    urllib.request.urlopen(req, timeout=10)


def main() -> None:
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    changed_any = False
    for url in URLS:
        try:
            current_hash = fetch_hash(url)
        except Exception as e:
            print(f"Error fetching {url}: {e}", file=sys.stderr)
            continue

        previous_hash = state.get(url)
        if previous_hash is None:
            print(f"First run for {url} - recording baseline.")
        elif previous_hash != current_hash:
            print(f"CHANGE DETECTED: {url}")
            notify(url)
            changed_any = True
        else:
            print(f"No change: {url}")

        state[url] = current_hash

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    if changed_any:
        print("At least one page changed this run.")


if __name__ == "__main__":
    main()
