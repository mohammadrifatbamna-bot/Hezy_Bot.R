json
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
        if not isinstance(data, list):
            return []

        cleaned = []
        for item in data:
            try:
                if isinstance(item, dict):
                    number = int(item.get("number", -1))
                    if 0 <= number <= 9:
                        cleaned.append({
                            "period": str(item.get("period", "")),
                            "number": number,
                            "last_two": str(item.get("last_two", number)).zfill(2),
                            "time": str(item.get("time", "")),
                            "prediction": item.get("prediction", "WAIT"),
                            "outcome": item.get("outcome", "SKIP")
                        })
                else:
                    number = int(item)
                    if 0 <= number <= 9:
                        cleaned.append({
                            "period": "",
                            "number": number,
                            "last_two": str(number).zfill(2),
                            "time": "",
                            "prediction": "WAIT",
                            "outcome": "SKIP"
                        })
            except (ValueError, TypeError):
                continue

        return cleaned[-100:]

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


def get_stats():
    wins = sum(1 for r in results if r.get("outcome") == "WIN")
    losses = sum(1 for r in results if r.get("outcome") == "LOSS")
    checked = wins + losses
    accuracy = round(wins * 100 / checked) if checked else 0

    return {
        "wins": wins,
        "losses": losses,
        "checked": checked,
        "accuracy": accuracy
    }


def analyze():
    recent = results[-20:]
    total = len(recent)

    big = sum(1 for r in recent if r["number"] >= 5)
    small = total - big

    if total == 0:
        signal = "WAIT"
        confidence = 0
    elif big > small:
        signal = "BIG"
        confidence = round(big * 100 / total)
    elif small > big:
        signal = "SMALL"
        confidence = round(small * 100 / total)
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
        "stats": get_stats()
    }


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WINGO BIG SMALL BOT</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#101827;color:white;font-family:Arial}
.container{max-width:500px;margin:auto}
h2{text-align:center;color:#38bdf8}
.card{background:#1e293b;padding:18px;margin:13px 0;border-radius:14px;text-align:center}
.heading{color:#94a3b8;font-size:14px}
.signal{font-size:32px;font-weight:bold;margin:10px}
.big{color:#22c55e}
.small{color:#f87171}
.wait{color:#facc15}
.value{font-size:25px;font-weight:bold;margin:8px}
input{width:100%;padding:16px;font-size:25px;text-align:center;border:0;border-radius:10px;margin:12px 0}
button{width:100%;padding:15px;border:0;border-radius:10px;background:#0ea5e9;color:white;font-size:18px;font-weight:bold}
button:disabled{opacity:.5}
.note{font-size:12px;color:#94a3b8;line-height:1.5}
.history{text-align:left}
.history-row{display:flex;justify-content:space-between;gap:8px;padding:10px;border-bottom:1px solid #334155;font-size:13px}
.win{color:#22c55e}
.loss{color:#f87171}
.skip{color:#facc15}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{background:#334155;padding:12px 5px;border-radius:10px}
.stat b{display:block;font-size:23px;margin-top:7px}
#message{margin-top:10px;color:#38bdf8}
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
<div class="heading">NEXT BIG / SMALL SIGNAL</div>
<div class="signal wait" id="signal">WAIT</div>
<div class="heading">HISTORICAL SHARE</div>
<div class="value" id="confidence">0%</div>
<div class="note">Based on the last 20 results. Not guaranteed.</div>
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
<div class="heading">WIN / LOSS TRACKER</div>
<div class="stats">
<div class="stat"><span class="heading">WIN</span><b class="win" id="wins">0</b></div>
<div class="stat"><span class="heading">LOSS</span><b class="loss" id="losses">0</b></div>
<div class="stat"><span class="heading">ACCURACY</span><b id="accuracy">0%</b></div>
</div>
<div class="note">Checked predictions: <span id="checked">0</span></div>
</div>

<div class="card">
<div class="heading">ADD LAST TWO DIGITS</div>
<input id="lastTwo" type="text" inputmode="numeric"
maxlength="2" placeholder="Enter 00 - 99">
<button id="addButton" onclick="addResult()">ADD RESULT</button>
<div id="message"></div>
<div class="note">Example: 83517 হলে শুধু 17 লিখবে।</div>
</div>

<div class="card history">
<div class="heading" style="text-align:center">RESULT HISTORY</div>
<div id="history">No results yet</div>
</div>

<p class="note" style="text-align:center">
Accuracy is based on recorded past outcomes, not a guarantee of future results.
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
        document.getElementById('confidence').textContent = data.confidence + '%';
        document.getElementById('big').textContent = data.big;
        document.getElementById('small').textContent = data.small;
        document.getElementById('total').textContent = data.total;

        const cls = data.signal === 'BIG' ? 'big' :
                    data.signal === 'SMALL' ? 'small' : 'wait';

        document.getElementById('signal').className = 'signal ' + cls;
        document.getElementById('live').className = 'signal ' + cls;

        document.getElementById('wins').textContent = data.stats.wins;
        document.getElementById('losses').textContent = data.stats.losses;
        document.getElementById('accuracy').textContent = data.stats.accuracy + '%';
        document.getElementById('checked').textContent = data.stats.checked;

        const hr = await fetch('/api/history');
        const hd = await hr.json();
        const box = document.getElementById('history');

        if(hd.results.length === 0){
            box.textContent = 'No results yet';
        }else{
            box.innerHTML = hd.results.slice().reverse().map(item => {
                const color = item.number >= 5 ? 'big' : 'small';
                const outcome = item.outcome || 'SKIP';
                return `<div class="history-row">
                    <span>Period ${item.period}: ${item.last_two}</span>
                    <b class="${outcome.toLowerCase()}">${outcome}</b>
                </div>`;
            }).join('');
        }
    }catch(error){
        document.getElementById('message').textContent = 'Connection error.';
    }
}

async function addResult(){
    const input = document.getElementById('lastTwo');
    const button = document.getElementById('addButton');
    const message = document.getElementById('message');
    const value = input.value.trim();

    if(!/^[0-9]{2}$/.test(value)){
        message.textContent = 'Enter exactly two digits, such as 17.';
        return;
    }

    button.disabled = true;
    message.textContent = 'Adding result...';

    try{
        const response = await fetch('/api/add', {
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({last_two:value})
        });

        const data = await response.json();

        if(!response.ok){
            message.textContent = data.error || 'Could not add result.';
        }else{
            message.textContent = 'Result added: ' + data.outcome;
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

document.getElementById('lastTwo').addEventListener('keydown', function(event){
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

            data = json.loads(self.rfile.read(length).decode("utf-8"))

            if not isinstance(data, dict):
                raise ValueError("Invalid data")

            last_two = data.get("last_two")

            if not isinstance(last_two, str) or len(last_two) != 2 or not last_two.isdigit():
                raise ValueError("Enter exactly two digits")

            number = int(last_two[-1])

            with lock:
                prediction = analyze()["signal"]
                actual = "BIG" if number >= 5 else "SMALL"

                if prediction == "WAIT":
                    outcome = "SKIP"
                elif prediction == actual:
                    outcome = "WIN"
                else:
                    outcome = "LOSS"

                results.append({
                    "period": make_period(),
                    "number": number,
                    "last_two": last_two,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "prediction": prediction,
                    "outcome": outcome
                })

                del results[:-100]
                save_results()
                answer = analyze()

            self.send_json({
                "success": True,
                "outcome": outcome,
                "prediction": prediction,
                "actual": actual,
                "analysis": answer
            })

        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"error": "Enter exactly two digits from 00 to 99"}, 400)
        except OSError:
            self.send_json({"error": "Could not save result"}, 500)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), BotHandler)
    print(f"Bot running on port {PORT}")
    server.
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", 10000))
DATA_FILE = Path("results.json")
lock = Lock()


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        if not isinstance(data, list):
            return []
        return [
            item for item in data
            if isinstance(item, dict)
            and str(item.get("last_two", "")).isdigit()
            and len(str(item.get("last_two", ""))) == 2
        ][-100:]
    except (OSError, ValueError, TypeError):
        return []


results = load_results()


def save_results():
    DATA_FILE.write_text(json.dumps(results[-100:], indent=2))


def get_result(item):
    digit = int(str(item["last_two"])[-1])
    return "BIG" if digit >= 5 else "SMALL"


def analyze():
    recent = results[-50:]
    big = sum(get_result(x) == "BIG" for x in recent)
    small = len(recent) - big

    if len(recent) < 5:
        signal, confidence = "WAIT", 0
    elif big > small:
        signal = "BIG"
        confidence = round(big / len(recent) * 100)
    elif small > big:
        signal = "SMALL"
        confidence = round(small / len(recent) * 100)
    else:
        signal, confidence = "WAIT", 50

    return {
        "signal": signal,
        "confidence": confidence,
        "big": big,
        "small": small,
        "total": len(recent)
    }


def get_streak():
    if not results:
        return {"type": "NONE", "count": 0}

    latest = get_result(results[-1])
    count = 0

    for item in reversed(results):
        if get_result(item) != latest:
            break
        count += 1

    return {"type": latest, "count": count}


def get_stats():
    wins = sum(x.get("outcome") == "WIN" for x in results)
    losses = sum(x.get("outcome") == "LOSS" for x in results)
    total = wins + losses

    return {
        "wins": wins,
        "losses": losses,
        "accuracy": round(wins / total * 100) if total else 0
    }


def next_period():
    if not results:
        return "1"
    try:
        return str(int(results[-1]["period"]) + 1)
    except (ValueError, TypeError, KeyError):
        return str(len(results) + 1)


def get_state():
    return {
        "status": "ACTIVE",
        "next_period": next_period(),
        "analysis": analyze(),
        "streak": get_streak(),
        "stats": get_stats(),
        "history": list(reversed(results[-20:])),
        "last_update": datetime.now(timezone.utc).isoformat()
    }


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WINGO 30 SECONDS</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:15px;background:#101522;color:white;font-family:Arial}
.main{max-width:520px;margin:auto}
h2{text-align:center;color:#54d6ff}
.card{background:#1b2435;padding:17px;margin:12px 0;border-radius:14px;border:1px solid #303b50}
h3{font-size:14px;color:#9bb0d0;margin:0 0 13px}
.signal{text-align:center;font-size:36px;font-weight:bold;padding:14px}
.big{color:#28df91}.small{color:#ff7373}.wait{color:#ffc857}
.stats{display:flex;gap:7px}
.stat{flex:1;text-align:center;background:#111a29;padding:12px 4px;border-radius:9px;font-size:12px}
.stat b{display:block;font-size:22px;margin-top:7px}
input{width:100%;padding:16px;background:#101522;color:white;border:1px solid #53627a;border-radius:9px;font-size:22px;text-align:center}
button{width:100%;padding:15px;margin-top:10px;background:#13b981;color:white;border:0;border-radius:9px;font-size:17px;font-weight:bold}
button:disabled{opacity:.5}
.note{color:#aab7cc;font-size:12px;text-align:center}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:10px 4px;border-bottom:1px solid #354057;text-align:center}
#message{text-align:center;margin-top:10px;color:#54d6ff}
</style>
</head>
<body>
<div class="main">
<h2>WINGO 30 SECONDS</h2>

<div class="card">
<h3>BOT STATUS</h3>
<div class="signal big">ACTIVE</div>
<div class="stats">
<div class="stat">NEXT PERIOD<b id="period">1</b></div>
<div class="stat">TOTAL RESULTS<b id="total">0</b></div>
</div>
</div>

<div class="card">
<h3>NEXT BIG / SMALL SIGNAL</h3>
<div id="signal" class="signal wait">WAIT</div>
<p class="note">Confidence: <b id="confidence">0</b>%</p>
<p class="note">Statistical estimate, not guaranteed prediction.</p>
</div>

<div class="card">
<h3>LIVE ANALYSIS</h3>
<div class="stats">
<div class="stat">BIG<b class="big" id="big">0</b></div>
<div class="stat">SMALL<b class="small" id="small">0</b></div>
<div class="stat">TOTAL<b id="analysisTotal">0</b></div>
</div>
<p class="note" id="analysisNote">Need at least 5 results.</p>
</div>

<div class="card">
<h3>WIN / LOSS RECORD</h3>
<div class="stats">
<div class="stat">WIN<b class="big" id="wins">0</b></div>
<div class="stat">LOSS<b class="small" id="losses">0</b></div>
<div class="stat">ACCURACY<b id="accuracy">0%</b></div>
</div>
</div>

<div class="card">
<h3>CURRENT STREAK</h3>
<div class="signal" id="streak">NONE 0</div>
</div>

<div class="card">
<h3>ADD RESULT</h3>
<p class="note">83517 হলে 17 লিখুন। 26480 হলে 80 লিখুন।</p>
<input id="number" type="text" inputmode="numeric" maxlength="2" placeholder="Enter last 2 digits">
<button id="addButton" onclick="addResult()">ADD RESULT</button>
<div id="message"></div>
</div>

<div class="card">
<h3>RESULT HISTORY</h3>
<table>
<thead><tr><th>Period</th><th>Number</th><th>Result</th><th>Outcome</th></tr></thead>
<tbody id="history"></tbody>
</table>
</div>
<p class="note">Auto refresh every 5 seconds</p>
</div>

<script>
async function refresh(){
 try{
  const response = await fetch('/api/state');
  const d = await response.json();

  document.getElementById('period').textContent = d.next_period;
  document.getElementById('total').textContent = d.analysis.total;
  document.getElementById('big').textContent = d.analysis.big;
  document.getElementById('small').textContent = d.analysis.small;
  document.getElementById('analysisTotal').textContent = d.analysis.total;
  document.getElementById('confidence').textContent = d.analysis.confidence;

  const s = document.getElementById('signal');
  s.textContent = d.analysis.signal;
  s.className = 'signal ' + d.analysis.signal.toLowerCase();

  document.getElementById('analysisNote').textContent =
   d.analysis.total < 5 ? 'Need at least 5 results.' :
   'Analysis based on last ' + d.analysis.total + ' results.';

  document.getElementById('wins').textContent = d.stats.wins;
  document.getElementById('losses').textContent = d.stats.losses;
  document.getElementById('accuracy').textContent = d.stats.accuracy + '%';
  document.getElementById('streak').textContent =
   d.streak.type + ' ' + d.streak.count;

  document.getElementById('history').innerHTML = d.history.map(x => {
   const result = Number(x.last_two.slice(-1)) >= 5 ? 'BIG' : 'SMALL';
   return '<tr><td>' + x.period + '</td><td>' + x.last_two +
    '</td><td class="' + result.toLowerCase() + '">' + result +
    '</td><td>' + (x.outcome || 'SKIP') + '</td></tr>';
  }).join('');

 }catch(e){
  document.getElementById('message').textContent = 'Connecting...';
 }
}

async function addResult(){
 const input = document.getElementById('number');
 const button = document.getElementById('addButton');
 const message = document.getElementById('message');
 const value = input.value.trim();

 if(!/^[0-9]{2}$/.test(value)){
  message.textContent = 'Enter exactly 2 digits.';
  return;
 }

 button.disabled = true;
 message.textContent = 'Adding result...';

 try{
  const response = await fetch('/api/add', {
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({last_two:value})
  });

  const data = await response.json();

  if(!response.ok){
   message.textContent = data.error || 'Error adding result';
  }else{
   message.textContent = 'Result added successfully';
   input.value = '';
   await refresh();
  }
 }catch(e){
  message.textContent = 'Connection error';
 }finally{
  button.disabled = false;
 }
}

document.getElementById('number').addEventListener('keydown', e => {
 if(e.key === 'Enter') addResult();
});

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

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

        elif path == "/api/state":
            with lock:
                self.send_json(get_state())

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

            data = json.loads(self.rfile.read(length).decode("utf-8"))
            value = str(data.get("last_two", ""))

            if len(value) != 2 or not value.isdigit():
                self.send_json({"error": "Enter exactly 2 digits"}, 400)
                return

            with lock:
                previous_signal = analyze()["signal"]
                actual = "BIG" if int(value[-1]) >= 5 else "SMALL"

                if previous_signal == "WAIT":
                    outcome = "SKIP"
                elif previous_signal == actual:
                    outcome = "WIN"
                else:
                    outcome = "LOSS"

                item = {
                    "period": next_period(),
                    "last_two": value,
                    "outcome": outcome,
                    "time": datetime.now(timezone.utc).isoformat()
                }

                results.append(item)
                del results[:-100]
                save_results()

            self.send_j
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", "10000"))
DATA_FILE = Path("results.json")
lock = Lock()


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        if isinstance(data, list):
            return [
                int(n) for n in data
                if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 99
            ][-100:]
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


results = load_results()


def save_results():
    DATA_FILE.write_text(json.dumps(results[-100:]))


def category(number):
    return "BIG" if number % 10 >= 5 else "SMALL"


def analyze():
    recent = results[-50:]
    big = sum(1 for n in recent if category(n) == "BIG")
    small = len(recent) - big
    total = len(recent)

    if total < 5:
        prediction = "WAIT"
        confidence = 0
    elif big > small:
        prediction = "BIG"
        confidence = round(big / total * 100)
    elif small > big:
        prediction = "SMALL"
        confidence = round(small / total * 100)
    else:
        prediction = "WAIT"
        confidence = 50

    streak = 0
    streak_type = category(results[-1]) if results else "NONE"
    for n in reversed(results):
        if category(n) == streak_type:
            streak += 1
        else:
            break

    return {
        "status": "ACTIVE",
        "prediction": prediction,
        "confidence": confidence,
        "big": big,
        "small": small,
        "total": total,
        "streak": streak,
        "streak_type": streak_type,
        "history": [
            {"number": n, "type": category(n)}
            for n in reversed(results[-20:])
        ],
        "last_update": datetime.now(timezone.utc).isoformat()
    }


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WINGO Signal Bot</title>
<style>
*{box-sizing:border-box}
body{margin:0;background:#101827;color:#fff;font-family:Arial,sans-serif;padding:16px}
.container{max-width:520px;margin:auto}
h2{text-align:center;color:#38bdf8}
.card{background:#1e293b;border-radius:14px;padding:18px;margin:14px 0}
.center{text-align:center}
.signal{font-size:35px;font-weight:bold;margin:12px}
.big{color:#22c55e}
.small{color:#f87171}
.wait{color:#facc15}
.label{color:#94a3b8;font-size:13px}
.value{font-size:25px;font-weight:bold;margin-top:6px}
input{width:100%;padding:15px;border-radius:9px;border:1px solid #475569;background:#0f172a;color:white;font-size:22px;text-align:center;margin:12px 0}
button{width:100%;padding:14px;border:0;border-radius:9px;background:#0ea5e9;color:white;font-size:17px;font-weight:bold}
button:active{opacity:.7}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.item{background:#0f172a;padding:14px;border-radius:10px;text-align:center}
.history{display:flex;justify-content:space-between;padding:10px;border-bottom:1px solid #334155}
.note{font-size:12px;color:#94a3b8;text-align:center;line-height:1.6}
</style>
</head>
<body>
<div class="container">
<h2>WINGO 30 SECONDS</h2>

<div class="card center">
<div class="label">BOT STATUS</div>
<div class="value big" id="status">ACTIVE</div>
</div>

<div class="card center">
<div class="label">NEXT BIG / SMALL SIGNAL</div>
<div class="signal wait" id="prediction">WAIT</div>
<div>Confidence: <b id="confidence">0%</b></div>
<p class="note">Statistical estimate, not a guaranteed prediction.</p>
</div>

<div class="card">
<h3>LIVE ANALYSIS</h3>
<div class="grid">
<div class="item">
<div class="label">BIG</div>
<div class="value big" id="big">0</div>
</div>
<div class="item">
<div class="label">SMALL</div>
<div class="value small" id="small">0</div>
</div>
<div class="item">
<div class="label">TOTAL</div>
<div class="value" id="total">0</div>
</div>
<div class="item">
<div class="label">CURRENT STREAK</div>
<div class="value" id="streak">0</div>
</div>
</div>
<p class="note" id="message">Need at least 5 results for analysis.</p>
</div>

<div class="card">
<h3>ADD RESULT</h3>
<div class="label">Enter last two digits of period/result</div>
<input id="number" type="number" min="0" max="99" placeholder="Example: 17">
<button onclick="addResult()">ADD RESULT</button>
<p class="note" id="response"></p>
</div>

<div class="card">
<h3>RESULT HISTORY</h3>
<div id="history">No results yet.</div>
</div>

<p class="note">BIG = last digit 5–9 | SMALL = last digit 0–4<br>Dashboard refreshes every 5 seconds.</p>
</div>

<script>
async function refresh(){
  try{
    const r = await fetch('/api/state');
    const d = await r.json();

    document.getElementById('status').textContent=d.status;
    const p=document.getElementById('prediction');
    p.textContent=d.prediction;
    p.className='signal '+(d.prediction==='BIG'?'big':d.prediction==='SMALL'?'small':'wait');

    document.getElementById('confidence').textContent=d.confidence+'%';
    document.getElementById('big').textContent=d.big;
    document.getElementById('small').textContent=d.small;
    document.getElementById('total').textContent=d.total;
    document.getElementById('streak').textContent=d.streak+' '+d.streak_type;
    document.getElementById('message').textContent =
      d.total<5 ? 'Need at least 5 results for analysis.' : 'Analysis based on last '+d.total+' results.';

    const h=document.getElementById('history');
    if(!d.history.length){
      h.textContent='No results yet.';
    }else{
      h.innerHTML=d.history.map(x =>
        '<div class="history"><span>'+String(x.number).padStart(2,'0')+
        '</span><b class="'+(x.type==='BIG'?'big':'small')+'">'+x.type+'</b></div>'
      ).join('');
    }
  }catch(e){
    document.getElementById('status').textContent='CONNECTING';
  }
}

async function addResult(){
  const input=document.getElementById('number');
  const value=input.value.trim();
  const response=document.getElementById('response');

  if(!/^\d{1,2}$/.test(value)){
    response.textContent='Enter a number from 0 to 99.';
    return;
  }

  try{
    const r=await fetch('/api/add',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({number:Number(value)})
    });
    const d=await r.json();
    response.textContent=d.message || d.error;
    if(r.ok){
      input.value='';
      refresh();
    }
  }catch(e){
    response.textContent='Connection error. Try again.';
  }
}

refresh();
setInterval(refresh,5000);
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):

    def send_json(self, data, status=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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

        elif path == "/api/state":
            with lock:
                self.send_json(analyze())

        elif path == "/api/history":
            with lock:
                self.send_json({"results": results[-100:]})

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

            data = json.loads(self.rfile.read(length))
            number = data.get("number")

            if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= 99:
                self.send_json({"error": "Enter a number from 0 to 99"}, 400)
                return

            with lock:
                results.append(number)
                del results[:-100]
                save_results()

            self.send_json({
                "message": f"Result {number:02d} added successfully",
                "type": category(number)
            })

        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"error": "Invalid input"}, 400)
        except OSError:
            self.send_json({"error": "Could not save result"}, 500)

    def log_message(self, format, *args):
        print(format % args)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Bot running on port", PORT, flush=True)
    server.serve_forever()
 on port", PORT, flush=True)
    server.serve_for