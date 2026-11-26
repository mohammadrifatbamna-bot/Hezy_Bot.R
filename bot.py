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
    bs = "BIG" if number >= 5 else "SMALL"

    if number == 0:
        color = "RED + VIOLET"
    elif number == 5:
        color = "GREEN + VIOLET"
    elif number in (1, 3, 7, 9):
        color = "GREEN"
    else:
        color = "RED"

    return bs, color


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        if not isinstance(data, list):
            return []

        results = []

        for i, item in enumerate(data):
            if isinstance(item, dict):
                period = str(item.get("period", "")).strip()
                number = item.get("number")
            else:
                period = "OLD-" + str(i + 1)
                number = item

            if (
                period
                and isinstance(number, int)
                and not isinstance(number, bool)
                and 0 <= number <= 9
            ):
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


def make_period(results):
    numeric = [
        int(r["period"])
        for r in results
        if str(r["period"]).isdigit()
    ]
    return str(max(numeric, default=0) + 1)


def analyze(results):
    recent = results[-20:]
    total = len(recent)

    big = sum(r["number"] >= 5 for r in recent)
    small = total - big

    if total < 5:
        signal = "WAIT"
        confidence = 0
        message = "Need at least 5 results for analysis."

    elif big > small:
        signal = "BIG"
        confidence = round(big / total * 100)
        message = "BIG appeared more often in recent results."

    elif small > big:
        signal = "SMALL"
        confidence = round(small / total * 100)
        message = "SMALL appeared more often in recent results."

    else:
        signal = "WAIT"
        confidence = 0
        message = "BIG and SMALL are equal."

    return {
        "signal": signal,
        "next_signal": signal,
        "next_period": make_period(results),
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
    font-family:Arial,sans-serif;
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
.signal {
    font-size:35px;
    font-weight:bold;
}
.prediction {
    font-size:30px;
    font-weight:bold;
    color:#22c55e;
}
textarea,button {
    padding:12px;
    margin:6px;
    border-radius:8px;
    border:0;
    font-size:16px;
    max-width:95%;
}
textarea {
    width:90%;
    height:130px;
    background:#f1f5f9;
    color:#111827;
}
button {
    background:#0ea5e9;
    color:white;
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
.small {
    color:#94a3b8;
    font-size:12px;
}
</style>
</head>
<body>

<h1>WINGO 30 SECONDS</h1>

<div class="card">
<h2>BOT STATUS</h2>
<div id="status">Connecting...</div>
</div>

<div class="card">
<h2>NEXT PERIOD</h2>
<div class="prediction" id="nextPeriod">Waiting</div>
<h2>NEXT BIG / SMALL</h2>
<div class="signal" id="nextSignal">WAIT</div>
<p>Historical Share: <span id="nextConfidence">0</span>%</p>
<p class="small">Statistical estimate, not guaranteed.</p>
</div>

<div class="card">
<h2>LIVE ANALYSIS</h2>
<div class="signal" id="signal">WAIT</div>
<p>Historical Share: <span id="confidence">0</span>%</p>
<p>BIG: <span id="big">0</span></p>
<p>SMALL: <span id="small">0</span></p>
<p>TOTAL: <span id="total">0</span></p>
<p id="message">Waiting for results...</p>
<p class="small" id="updated">--</p>
</div>

<div class="card">
<h2>ADD NUMBERS ONLY</h2>
<p class="small">0 থেকে 9 পর্যন্ত সংখ্যা লেখো। প্রতি লাইনে একটি।</p>
<textarea id="bulk" placeholder="8
3
5
1
7"></textarea>
<br>
<button onclick="addResults()">ADD NUMBERS</button>
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
Dashboard refreshes every 30 seconds.
Numbers must be entered manually.
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
        document.getElementById('total').innerText = a.total_results;
        document.getElementById('message').innerText = a.message;
        document.getElementById('updated').innerText =
            'Last update: ' + a.updated;

        document.getElementById('nextPeriod').innerText =
            a.next_period;
        document.getElementById('nextSignal').innerText =
            a.next_signal;
        document.getElementById('nextConfidence').innerText =
            a.confidence;

        const h = await fetch('/api/history');
        if (!h.ok) throw new Error("History error");

        const history = await h.json();
        const tbody = document.getElementById('history');
        tbody.replaceChildren();

        history.results.slice().reverse().forEach(r => {
            const tr = document.createElement('tr');

            [r.period,r.number,r.big_small,r.color].forEach(value => {
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
    const numbers = [];

    for (const line of lines) {
        if (!line.trim()) continue;

        const value = line.trim();

        if (!/^\\d$/.test(value)) {
            responseBox.innerText =
                'শুধু 0 থেকে 9 পর্যন্ত Number লেখো।';
            return;
        }

        numbers.push(Number(value));
    }

    if (numbers.length < 1 || numbers.length > 10) {
        responseBox.innerText =
            'একবারে 1 থেকে 10টি Number দাও।';
        return;
    }

    try {
        const response = await fetch('/api/add-bulk', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({numbers:numbers})
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed');
        }

        responseBox.innerText = 'Added: ' + data.added;
        textarea.value = '';
        await refresh();

    } catch (error) {
        responseBox.innerText = error.message;
    }
}

refresh();
setInterval(refresh,30000);
</script>
</body>
</html>
"""


class BotHandler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(
            data, ensure_ascii=False
        ).encode("utf-8")

        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8"
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/html; charset=utf-8"
            )
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
            self.send_json({"error":"Not found"},404)

    def do_POST(self):
        path = self.path.split("?")[0]

        if path != "/api/add-bulk":
            self.send_json({"error":"Not found"},404)
            return

        try:
            length = int(self.headers.get("Content-Length","0"))

            if length <= 0 or length > 10000:
                self.send_json({"error":"Invalid request size"},400)
                return

            data = json.loads(self.rfile.read(length))
            numbers = data.get("numbers")

            if not isinstance(numbers,list) or not 1 <= len(numbers) <= 10:
                self.send_json({"error":"Enter 1 to 10 numbers"},400)
                return

            for number in numbers:
                if (
                    isinstance(number,bool)
                    or not isinstance(number,int)
                    or not 0 <= number <= 9
                ):
                    self.send_json({"error":"Numbers must be 0 to 9"},400)
                    return

            with lock:
                results = load_results()
                added = 0

                for number in numbers:
                    period = make_period(results)
                    bs,color = details(number)

                    results.append({
                        "period":period,
                        "number":number,
                        "big_small":bs,
                        "color":color
                    })
                    added += 1

                results = results[-100:]
                save_results(results)
                analysis = analyze(results)

            self.send_json({
                "status":"success",
                "added":added,
                "analysis":analysis
            })

        except (ValueError,TypeError,KeyError):
            self.send_json({"error":"Invalid result data"},400)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    print("Wingo 30 Seconds Bot ACTIVE")
    print("Port:",PORT)

    server = ThreadingHTTPServer(
        ("0.0.0.0",PORT),
        BotHandler
    )
    server.serve_forever()