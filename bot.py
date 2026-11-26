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
        return [
            int(n) for n in data
            if not isinstance(n, bool) and str(n).isdigit()
            and 0 <= int(n) <= 9
        ][-100:]
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
            "message": "Need at least 5 results",
            "total_results": len(results)
        }

    big = sum(n >= 5 for n in recent)
    small = len(recent) - big

    if big > small:
        signal = "BIG"
    elif small > big:
        signal = "SMALL"
    else:
        signal = "WAIT"

    return {
        "signal": signal,
        "confidence": round(max(big, small) / len(recent) * 100),
        "big": big,
        "small": small,
        "last_results": recent,
        "total_results": len(results),
        "updated": datetime.now(timezone.utc).isoformat(),
        "note": "Statistical estimate, not a guaranteed prediction."
    }


HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wingo 30 Seconds Bot</title>
<style>
body {
    background:#101827;
    color:white;
    font-family:Arial;
    text-align:center;
    padding:20px;
}
.card {
    background:#1e293b;
    padding:20px;
    margin:15px auto;
    border-radius:12px;
    max-width:450px;
}
h1 {color:#38bdf8;}
.signal {font-size:35px;font-weight:bold;}
input,button {
    padding:12px;
    margin:6px;
    border-radius:8px;
    border:0;
    font-size:17px;
}
button {background:#0ea5e9;color:white;}
.small {color:#94a3b8;font-size:13px;}
</style>
</head>
<body>

<h1>WINGO 30 SECONDS</h1>
<div class="card">
<h2>BOT STATUS</h2>
<div id="status">Connecting...</div>
</div>

<div class="card">
<h2>LIVE ANALYSIS</h2>
<div class="signal" id="signal">WAIT</div>
<p>Confidence: <span id="confidence">0</span>%</p>
<p>BIG: <span id="big">0</span></p>
<p>SMALL: <span id="small">0</span></p>
<p id="message">Waiting for results...</p>
<p class="small">Last update: <span id="updated">--</span></p>
</div>

<div class="card">
<h2>ADD RESULT</h2>
<input id="number" type="number" min="0" max="9"
placeholder="Enter 0-9">
<button onclick="addResult()">ADD RESULT</button>
<p id="response"></p>
</div>

<div class="card">
<h2>RESULT HISTORY</h2>
<p id="history">No results</p>
</div>

<p class="small">
Analysis refreshes every 30 seconds.
This dashboard does not automatically collect Wingo results.
</p>

<script>
async function refresh() {
    try {
        const response = await fetch('/api/analyze');
        if (!response.ok) throw new Error("API error");

        const data = await response.json();
        const a = data.analysis;

        document.getElementById('status').innerText = 'ACTIVE';
        document.getElementById('signal').innerText = a.signal;
        document.getElementById('confidence').innerText = a.confidence;
        document.getElementById('big').innerText = a.big ?? 0;
        document.getElementById('small').innerText = a.small ?? 0;
        document.getElementById('message').innerText = a.message || a.note;
        document.getElementById('updated').innerText =
            a.updated || 'Waiting for results';

        const h = await fetch('/api/history');
        const history = await h.json();

        document.getElementById('history').innerText =
            history.results.length
            ? history.results.join(' | ')
            : 'No results yet';

    } catch (error) {
        document.getElementById('status').innerText = 'CONNECTION ERROR';
    }
}

async function addResult() {
    const input = document.getElementById('number');
    const number = Number(input.value);

    if (input.value === '' || !Number.isInteger(number) ||
        number < 0 || number > 9) {
        document.getElementById('response').innerText =
            'Enter a number from 0 to 9';
        return;
    }

    try {
        const response = await fetch('/api/add', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({number})
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.error);

        document.getElementById('response').innerText =
            'Result added successfully';

        input.value = '';
        await refresh();

    } catch (error) {
        document.getElementById('response').innerText = error.message;
    }
}

refresh();
setInterval(refresh, 30000);
</script>

</body>
</html>
"""


class BotHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        with lock:
            results = load_results()

        if path == "/api/analyze":
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
                result = analyze(results)

            self.send_json({
                "status": "success",
                "added": number,
                "analysis": result
            })

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_json({"error": "Invalid JSON or number"}, 400)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Wingo 30 Seconds Analysis Dashboard ACTIVE")
    print("Port:", PORT)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), BotHandler)
    server.serve_forever()