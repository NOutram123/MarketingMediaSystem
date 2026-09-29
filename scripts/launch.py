"""Start the loopback studio and open the browser only after its health check passes."""
import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn


def main():
    with socket.socket() as probe:
        try:
            probe.bind(('127.0.0.1', 8787))
        except OSError:
            raise SystemExit('Port 8787 is already in use. Close the previous studio or open http://127.0.0.1:8787 if it is already running.')
    def open_when_ready():
        for _ in range(60):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8787/api/health', timeout=1) as response:
                    if response.status == 200:
                        webbrowser.open('http://127.0.0.1:8787')
                        return
            except OSError:
                time.sleep(1)
    threading.Thread(target=open_when_ready, daemon=True).start()
    uvicorn.run('backend.main:app', host='127.0.0.1', port=8787)


if __name__ == '__main__':
    main()
