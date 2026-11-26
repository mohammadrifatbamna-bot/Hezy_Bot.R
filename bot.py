import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", "8000"))
DATA_FILE = Path("results.json")
lock = Lock()


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        results = []

        if not isinstance(data, list):
            return []

        for item in data:
            try:
                if isinstance(item, dict):
                    number = int(item.get("number", -1))
                    period = str(item.get("period", ""))
                    timestamp = str(item.get("time", ""))
                else:
                    number = int(item)
                    period = ""
                    timestamp = ""

                if 0 <= number <= 9:
                    results.append({
                        "period": period,
                        "number": number,
                        "time": timestamp
                    })
            except (ValueError, TypeError):
                continue

        return results[-100:]

    except (OSError, json.JSONDecodeError):
        return []


results = load_results()


def save_results():
    DATA_FILE.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def make_period():
    if not results:
        return "1"

    try:
        return str(int(results[-1]["period"]) + 1)
    except (ValueError, TypeError):
        return str(len(results) + 1)


def analyze():
    recent = results[-20:]
    total = len(recent)

    big = sum(1 for item in recent if item["number"] >= 5)
    small = total - big

    if total == 0:
        signal = "WAIT"
        confidence = 0
    elif big > small:
        signal = "BIG"
        confidence = round((big / total) * 100)
    elif small > big:
        signal = "SMALL"
        confidence = round((small / total) * 100)
    else:
        signal = "WAIT"
        confidence = 50

    return {
        "status": "ACTIVE",
        "next_period": make_period(),
        "signal": signal,
        "confidence": confidence,
        "big": big,
        "small": small,
        "total": total,
        "last_update": datetime.now(timezone.utc).isoformat()
    }


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WINGO BIG SMALL BOT</title>
<style>
*{box-sizing:border-box}
body{
    margin:0;
    padding:16px;
    background:#101827;
    color:white;
    font-family:Arial,sans-serif;
}
.container{max-width:500px;margin:auto}
h2{text-align:center;color:#38bdf8}
.card{
    background:#1e293b;
    padding:18px;
    margin:13px 0;
    border-radius:14px;
    text-align:center;
}
.heading{color:#94a3b8;font-size:14px}
.signal{font-size:32px;font-weight:bold;margin:10px}
.big{color:#22c55e}
.small{color:#f87171}
.wait{color:#facc15}
.value{font-size:25px;font-weight:bold;margin:8px}
input{
    width:100%;
    padding:16px;
    font-size:24px;
    text-align:center;
    border:0;
    border-radius:10px;
    margin:12px 0;
}
button{
    width:100%;
    padding:15px;
    border:0;
    border-radius:10px;
    background:#0ea5e9;
    color:white;
    font-size:18px;
    font-weight:bold;
}
button:disabled{opacity:.5}
.note{font-size:12px;color:#94a3b8;line-height:1.5}
#message{margin-top:10px;color:#38bdf8}
.history{text-align:left}
.history-row{
    display:flex;
    justify-content:space-between;
    padding:10px;
    border-bottom:1px solid #334155;
}
</style>
</head>
<body>
<div class="container">

<h2>WINGO 30 SECONDS</h2>

<div class="card">
    <div class="heading">BOT STATUS</div>
    <div class="value big">ACTIVE</div>
    <div class="heading">NEXT PERIOD</div>
    <div class="value" id="period">Waiting</div>
</div>

<div class="card">
    <div class="heading">NEXT BIG / SMALL</div>
    <div class="signal wait" id="signal">WAIT</div>
    <div class="heading">Historical Share</div>
    <div class="value" id="confidence">0%</div>
    <div class="note">Statistical estimate from entered results, not a guaranteed prediction.</div>
</div>

<div class="card">
    <div class="heading">LIVE ANALYSIS</div>
    <div class="signal wait" id="live">WAIT</div>
    <div class="heading">BIG</div>
    <div class="value big" id="big">0</div>
    <div class="heading">SMALL</div>
    <div class="value small" id="small">0</div>
    <div class="heading">TOTAL RESULTS</div>
    <div class="value" id="total">0</div>
</div>

<div class="card">
    <div class="heading">ADD ONE RESULT ONLY</div>
    <input id="number" type="number" min="0" max="9"
           inputmode="numeric" placeholder="Enter 0 - 9">
    <button id="addButton" onclick="addResult()">ADD RESULT</button>
    <div id="message"></div>
</div>

<div class="card history">
    <div class="heading" style="text-align:center">RESULT HISTORY</div>
    <div id="history">No results yet</div>
</div>

<p class="note" style="text-align:center">
Analysis uses the last 20 entered results. It cannot guarantee the next outcome.
</p>

</div>

<script>
async function refresh(){
    try{
        const response = await fetch('/api/analyze');
        const data = await response.json();

        document.getElementById('period').textContent = data.next_period;
        document.getElementById('signal').textContent = data.signal;
        document.getElementById('live').textContent = data.signal;
        document.getElementById('confidence').textContent =
            data.confidence + '%';
        document.getElementById('big').textContent = data.big;
        document.getElementById('small').textContent = data.small;
        document.getElementById('total').textContent = data.total;

        const cls = data.signal === 'BIG' ? 'big' :
                    data.signal === 'SMALL' ? 'small' : 'wait';

        document.getElementById('signal').className = 'signal ' + cls;
        document.getElementById('live').className = 'signal ' + cls;

        const historyResponse = await fetch('/api/history');
        const historyData = await historyResponse.json();

        const box = document.getElementById('history');
        if(historyData.results.length === 0){
            box.textContent = 'No results yet';
        }else{
            box.innerHTML = historyData.results.slice().reverse().map(item => {
                const type = item.number >= 5 ? 'BIG' : 'SMALL';
                const color = item.number >= 5 ? 'big' : 'small';
                return `<div class="history-row">
                    <span>Period ${item.period}</span>
                    <b class="${color}">${item.number} - ${type}</b>
                </div>`;
            }).join('');
        }
    }catch(error){
        document.getElementById('message').textContent =
            'Connection error. Refresh the page.';
    }
}

async function addResult(){
    const input = document.getElementById('number');
    const button = document.getElementById('addButton');
    const message = document.getElementById('message');
    const value = input.value.trim();

    if(!/^[0-9]$/.test(value)){
        message.textContent = 'Please enter only one digit from 0 to 9.';
        return;
    }

    button.disabled = true;
    message.textContent = 'Adding result...';

    try{
        const response = await fetch('/api/add', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({number:Number(value)})
        });

        const data = await response.json();

        if(!response.ok){
            message.textContent = data.error || 'Could not add result.';
        }else{
            message.textContent = 'Result added successfully!';
            input.value = '';
            await refresh();
        }
    }catch(error){
        message.textContent = 'Connection error. Try again.';
    }finally{
        button.disabled = false;
        input.focus();
    }
}

document.getElementById('number').addEventListener('keydown', function(event){
    if(event.key === 'Enter') addResult();
});

refresh();
setInterval(refresh, 5000);
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

        elif path == "/api/analyze":
            with lock:
                self.send_json(analyze())

        elif path == "/api/history":
            with lock:
                self.send_json({"results": results})

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/api/add":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 1000:
                self.send_json({"error": "Invalid request"}, 400)
                return

            body = self.rfile.read(length)
            data = json.loads(body.decode("utf-8"))

            if not isinstance(data, dict):
                raise ValueError("Invalid data")

            number = data.get("number")

            if isinstance(number, bool) or not isinstance(number, int):
                raise ValueError("Enter one digit from 0 to 9")

            if not 0 <= number <= 9:
                raise ValueError("Enter one digit from 0 to 9")

            with lock:
                results.append({
                    "period": make_period(),
                    "number": number,
                    "time": datetime.now(timezone.utc).isoformat()
                })

                del results[:-100]
                save_results()
                answer = analyze()

            self.send_json({
                "success": True,
                "message": "Result added",
                "analysis": answer
            })

        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"error": "Enter only one number from 0 to 9"}, 400)
        except OSError:
            self.send_json({"error": "Could not save result"}, 500)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), BotHandler)
    print(f"Bot running on port {PORT}")
    server.serve_forever()