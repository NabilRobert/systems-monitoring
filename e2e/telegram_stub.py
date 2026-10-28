"""A stand-in for Telegram's Bot API, so the end-to-end test needs no network.

Alertmanager's Telegram receiver is pointed at this server (its `api_url`).
Each sendMessage call is appended to /out/messages.jsonl with the time it
arrived, and answered the way Telegram answers.
"""

import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUT = "/out/messages.jsonl"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        method = self.path.rsplit("/", 1)[-1]
        try:
            body = json.loads(raw)
        except ValueError:
            body = {"unparsed": raw.decode(errors="replace")}
        if method == "sendMessage":
            with open(OUT, "a") as f:
                f.write(json.dumps({"received_at": time.time(), "body": body}) + "\n")
        result = {
            "message_id": int(time.time() * 1000) % 2**31,
            "date": int(time.time()),
            # Telegram's chat ID is a number; echoing the string Alertmanager
            # sends makes its client reject the reply and send again.
            "chat": {"id": int(body.get("chat_id", 0)), "type": "private"},
            "text": body.get("text", ""),
        }
        if method == "getMe":
            result = {"id": 1, "is_bot": True, "first_name": "stub", "username": "stub_bot"}
        payload = json.dumps({"ok": True, "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
