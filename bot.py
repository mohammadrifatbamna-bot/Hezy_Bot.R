import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", 8000))
DATA_FILE = Path("results.json")
lock = Lock()


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        return [int(n) for n in data if 0 <= int(n) <= 9][-100:]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return []


def save_results(results):
    DATA_FILE.write_text(json.dumps(results[-100:]))


def analyze(results):
    recent = results[-10:]

    if len(recent) < 5:
        return {
            "signal": "WAIT",
            "confidence": 0,
            "message": "Need at least 5 results"
        }

    big = sum(n >= 5 for n in recent)
    small = len(recent) - big

    if big > small:
        signal = "BIG"
    elif small > big:
        signal = "SMALL"
    else:
        signal = "WAIT"

    confidence = round(max(big, small) / len(recent) * 100)

    return {
        "signal": signal,
        "confidence": confidence,
        "big": big,
        "small": small,
        "last_results": recent,
        "total_results": len(results),
        "updated": datetime.now(timezone.utc).isoformat(),
        "note": "Statistical estimate, not a guaranteed prediction."
    }


class BotHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?")[0]

        with lock:
            results = load_results()

        if path == "/":
            self.send_json({
                "bot": "Wingo 30 Seconds Analyzer",
                "status": "ACTIVE",
                "interval": 30,
                "endpoints": [
                    "/api/analyze",
                    "/api/history"
                ]
            })

        elif path == "/api/analyze":
            self.send_json({
                "status": "ACTIVE",
                "analysis": analyze(results)
            })

        elif path == "/api/history":
            self.send_json({
                "total": len(results),
                "results": results
            })

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/add":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 10000:
                self.send_json({"error": "Invalid request size"}, 400)
                return

            data = json.loads(self.rfile.read(length))
            number = data.get("number")

            if isinstance(number, bool) or not isinstance(number, int):
                raise ValueError("Number must be an integer")

            if not 0 <= number <= 9:
                self.send_json({"error": "Number must be 0-9"}, 400)
                return

            with lock:
                results = load_results()
                results.append(number)
                results = results[-100:]
                save_results(results)
                analysis = analyze(results)

            self.send_json({
                "status": "success",
                "added": number,
                "analysis": analysis
            })

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_json({"error": "Invalid JSON or number"}, 400)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Wingo 30 Seconds Analyzer ACTIVE")
    print("Port:", PORT)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), BotHandler)
    server.serve_forever()