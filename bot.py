import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", 8000))
DATA_FILE = Path("results.json")
lock = Lock()


def details(number):
    big_small = "BIG" if number >= 5 else "SMALL"

    if number == 0:
        color = "RED + VIOLET"
    elif number == 5:
        color = "GREEN + VIOLET"
    elif number in (1, 3, 7, 9):
        color = "GREEN"
    else:
        color = "RED"

    return big_small, color


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        results = []

        if not isinstance(data, list):
            return []

        for i, item in enumerate(data):
            if isinstance(item, dict):
                period = str(item.get("period", ""))
                number = item.get("number")
            else:
                period = "OLD-" + str(i + 1)
                number = item

            if (isinstance(number, int)
                    and not isinstance(number, bool)
                    and 0 <= number <= 9):

                bs, color = details(number)

                results.append({
                    "period": period,
                    "number": number,
                    "big_small": bs,
                    "color": color
                })

        return results[-100:]

    except (OSError, ValueError, TypeError):
        return []


def save_results(results):
    DATA_FILE.write_text(
        json.dumps(results[-100:], ensure_ascii=False)
    )


def analyze(results):
    recent = results[-10:]

    big = sum(r["number"] >= 5 for r in recent)
    small = len(recent) - big

    if len(recent) < 5:
        signal = "WAIT"
        confidence = 0
        message = "Need at least 5 results"
    else:
        signal = (
            "BIG" if big > small
            else "SMALL" if small > big
            else "WAIT"
        )
        confidence = round(max(big, small) / len(recent) * 100)
        message = "Statistical estimate, not a guaranteed prediction."

    return {
        "signal": signal,
        "confidence": confidence,
        "big": big,
        "small": small,
        "last_results": recent,
        "total_results": len(results),
        "updated": datetime.now(timezone.utc).isoformat(),
        "message": message
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
    padding:12px;
}
.card {
    background:#1e293b;
    padding:18px;
    margin:15px auto;
    border-radius:12px;
    max-width:550px;
}
h1 {color:#38bdf8;}
.signal {font-size:35px;font-weight:bold;}
input,textarea,button {
    padding:12px;
    margin:6px;
    border-radius:8px;
    border:0;
    font-size:16px;
    max-width:95%;
}
textarea {
    width:90%;
    height:150px;
    background:#f1f5f9;
    color:#111827;
}
button {
    background:#0ea5e9;
    color:white;
    cursor:pointer;
}
table {
    width:100%;
    border-collapse:collapse;
    font-size:12px;
}
td,th {
    padding:9px 3px;
    border-bottom:1px solid #475569;
}
.small {color:#94a3b8;font-size:12px;}
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
<p class="small" id="updated">--</p>
</div>

<div class="card">
<h2>ADD MULTIPLE RESULTS</h2>
<p class="small">Format: Period,Number (one per line)</p>

<textarea id="bulk" placeholder="20261126100052360,7
20261126100052359,8
20261126100052358,4"></textarea>

<br>
<button onclick="addResults()">ADD RESULTS</button>
<p id="response"></p>
</div>

<div class="card">
<h2>RESULT HISTORY</h2>
<div style="overflow-x:auto">
<table>
<thead>
<tr>
<th>Period</th>
<th>Number</th>
<th>BIG/SMALL</th>
<th>Color</th>
</tr>
</thead>
<tbody id="history"></tbody>
</table>
</div>
</div>

<p class="small">
Analysis refreshes every 30 seconds.
Results are entered manually.
Statistical estimates are not guaranteed predictions.
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
        document.getElementById('big').innerText = a.big;
        document.getElementById('small').innerText = a.small;
        document.getElementById('message').innerText = a.message;
        document.getElementById('updated').innerText =
            a.updated || 'Waiting for results';

        const h = await fetch('/api/history');
        const history = await h.json();
        const tbody = document.getElementById('history');

        tbody.replaceChildren();

        history.results.slice().reverse().forEach(r => {
            const tr = document.createElement('tr');

            [r.period, r.number, r.big_small, r.color].forEach(value => {
                const td = document.createElement('td');
                td.textContent = value;
                tr.appendChild(td);
            });

            tbody.appendChild(tr);
        });

    } catch (error) {
        document.getElementById('status').innerText =
            'CONNECTION ERROR';
    }
}


async function addResults() {
    const textarea = document.getElementById('bulk');
    const responseBox = document.getElementById('response');

    const lines = textarea.value.trim().split(/\\r?\\n/);
    const results = [];

    for (const line of lines) {
        if (!line.trim()) continue;

        const parts = line.split(',').map(x => x.trim());

        if (parts.length !== 2 ||
            !parts[0] ||
            !/^\\d+$/.test(parts[1])) {
            responseBox.innerText =
                'Invalid format: use Period,Number';
            return;
        }

        const number = Number(parts[1]);

        if (!Number.isInteger(number) || number < 0 || number > 9) {
            responseBox.innerText =
                'Number must be between 0 and 9';
            return;
        }

        results.push({
            period: parts[0],
            number: number
        });
    }

    if (results.length < 1 || results.length > 10) {
        responseBox.innerText =
            'Enter between 1 and 10 results';
        return;
    }

    try {
        const response = await fetch('/api/add-bulk', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({results})
        });

        const data = await response.json();

        if (!response.ok) throw new Error(data.error);

        responseBox.innerText =
            'Added: ' + data.added +
            ' | Skipped: ' + data.skipped;

        textarea.value = '';
        await refresh();

    } catch (error) {
        responseBox.innerText = error.message;
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
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
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
        path = self.path.split("?")[0]

        if path not in ("/api/add", "/api/add-bulk"):
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 10000:
                self.send_json({"error": "Invalid request size"}, 400)
                return

            data = json.loads(self.rfile.read(length))

            if path == "/api/add":
                items = [{
                    "period": str(data.get("period", "")).strip(),
                    "number": data.get("number")
                }]
            else:
                items = data.get("results")

            if not isinstance(items, list) or not 1 <= len(items) <= 10:
                self.send_json({"error": "Enter 1 to 10 results"}, 400)
                return

            for item in items:
                if not isinstance(item, dict):
                    raise ValueError()

                period = str(item.get("period", "")).strip()
                number = item.get("number")

                if not period or len(period) > 40:
                    raise ValueError()

                if (isinstance(number, bool)
                        or not isinstance(number, int)
                        or not 0 <= number <= 9):
                    raise ValueError()

            added = 0
            skipped = 0

            with lock:
                results = load_results()
                existing = {r["period"] for r in results}

                for item in items:
                    period = str(item["period"]).strip()

                    if period in existing:
                        skipped += 1
                        continue

                    number = item["number"]
                    bs, color = details(number)

                    results.append({
                        "period": period,
                        "number": number,
                        "big_small": bs,
                        "color": color
                    })

                    existing.add(period)
                    added += 1

                results = results[-100:]
                save_results(results)
                analysis = analyze(results)

            self.send_json({
                "status": "success",
                "added": added,
                "skipped": skipped,
                "analysis": analysis
            })

        except (ValueError, TypeError, KeyError, json.JSONDecodeError):
            self.send_json({"error": "Invalid result data"}, 400)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Wingo 30 Seconds Analysis Dashboard ACTIVE")
    print("Port:", PORT)

    server = ThreadingHTTPServer(("0.0.0.0", PORT), BotHandler)
    server.serve_forever()