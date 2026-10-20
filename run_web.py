"""Start the local web app without a separate frontend build or Studio."""

import argparse
import os
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

from dotenv import load_dotenv
import uvicorn


def main():
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    parser = argparse.ArgumentParser(description="Start the ChatBot web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    if len(os.getenv("CHAT_PASSWORD", "")) < 8:
        parser.exit(1, "Please set CHAT_PASSWORD in .env to a password with at least 8 characters.\n")
    url = f"http://127.0.0.1:{args.port}"
    print(f"ChatBot: {url}", flush=True)
    if args.host != "127.0.0.1":
        print(f"Also listening on {args.host}:{args.port}; use this computer's LAN address on your phone.", flush=True)
    if not args.no_browser:
        def open_when_ready():
            for _ in range(60):
                try:
                    with urllib.request.urlopen(f"{url}/health", timeout=1) as response:
                        if response.status == 200:
                            webbrowser.open(url)
                            return
                except OSError:
                    time.sleep(0.5)
        threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run("webapp:app", app_dir=str(Path(__file__).resolve().parent), host=args.host, port=args.port, workers=1)


if __name__ == "__main__":
    main()
