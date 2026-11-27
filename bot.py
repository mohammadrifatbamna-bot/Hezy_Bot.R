import json
import os
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock

PORT = int(os.environ.get("PORT", "10000"))
DATA_FILE = Path("results.json")
lock = Lock()
results = []


def load_results():
    global results
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            results = [
                x for x in data
                if isinstance(x, dict)
                and isinstance(x.get("period"), str)
                and len(x["period"]) == 5
                and x["period"].isdigit()
                and isinstance(x.get("number"), int)
                and not isinstance(x.get("number"), bool)
                and 0 <= x["number"] <= 9
            ][-100:]
    except (OSError, ValueError):
        results = []


def save_results():
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(results), encoding="utf-8")
    temp.replace(DATA_FILE)


def get_side(number):
    return "BIG" if number >= 5 else "SMALL"


def get_next_period():
    if not results:
        return "-----"
    return f"{(int(results[-1]['period']) + 1) % 100000:05d}"


def analyze():
    recent = results[-20:]
    total = len(recent)
    big = sum(1 for x in recent if get_side(x["number"]) == "BIG")
    small = total - big

    if total < 5 or big == small:
        signal = "WAIT"
        confidence = 0
    elif big > small:
        signal = "BIG"
        confidence = round(big * 100 / total)
    else:
        signal = "SMALL"
        confidence = round(small * 100 / total)

    wins = sum(1 for x in results if x.get("outcome") == "WIN")
    losses = sum(1 for x in results if x.get("outcome") == "LOSS")
    checked = wins + losses

    return {
        "status": "ACTIVE",
        "next_period": get_next_period(),
        "signal": signal,
        "confidence": confidence,
        "big": big,
        "small": small,
        "total": len(results),
        "wins": wins,
        "losses": losses,
        "checked": checked,
        "accuracy": round(wins * 100 / checked) if checked else 0
    }


HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WINGO 5 DIGIT BOT</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:15px;background:#101827;color:white;font-family:Arial}
.main{max-width:500px;margin:auto}
h2{text-align:center;color:#38bdf8}
.card{background:#1e293b;padding:18px;margin:12px 0;border-radius:13px}
.heading{color:#94a3b8;font-size:13px}
.signal{text-align:center;font-size:36px;font-weight:bold;padding:13px}
.big{color:#22c55e}
.small{color:#f87171}
.wait{color:#facc15}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}
.stat{background:#334155;padding:12px 5px;border-radius:9px;text-align:center;font-size:12px}
.stat b{display:block;font-size:22px;margin-top:7px}
input{width:100%;padding:15px;margin:10px 0;background:#101827;color:white;border:1px solid #475569;border-radius:9px;font-size:22px;text-align:center}
button{width:100%;padding:15px;background:#0ea5e9;color:white;border:0;border-radius:9px;font-size:17px;font-weight:bold}
button:disabled{opacity:.5}
.history{display:flex;justify-content:space-between;padding:10px 2px;border-bottom:1px solid #475569;font-size:13px;gap:5px}
.note{font-size:12px;color:#94a3b8;text-align:center;line-height:1.6}
#message{text-align:center;color:#38bdf8;margin-top:10px}
</style>
</head>
<body>
<div class="main">
<h2>WINGO 5 DIGIT BOT</h2>

<div class="card">
<div class="heading">BOT STATUS</div>
<div class="signal big">ACTIVE</div>
<div class="stats">
<div class="stat">NEXT PERIOD<b id="next">-----</b></div>
<div class="stat">TOTAL<b id="total">0</b></div>
<div class="stat">ACCURACY<b id="accuracy">0%</b></div>
</div>
</div>

<div class="card">
<div class="heading">NEXT BIG / SMALL SIGNAL</div>
<div id="signal" class="signal wait">WAIT</div>
<div class="note">Confidence: <b id="confidence">0%</b></div>
<p class="note">Statistical estimate, not guaranteed.</p>
</div>

<div class="card">
<div class="heading">LIVE ANALYSIS</div>
<div class="stats">
<div class="stat">BIG<b class="big" id="big">0</b></div>
<div class="stat">SMALL<b class="small" id="small">0</b></div>
<div class="stat">TOTAL<b id="count">0</b></div>
</div>
<p class="note" id="analysisNote">Need at least 5 results.</p>
</div>

<div class="card">
<div class="heading">WIN / LOSS TRACKER</div>
<div class="stats">
<div class="stat">WIN<b class="big" id="wins">0</b></div>
<div class="stat">LOSS<b class="small" id="losses">0</b></div>
<div class="stat">CHECKED<b id="checked">0</b></div>
</div>
</div>

<div class="card">
<div class="heading">ADD RESULT</div>
<p class="note">Example: 83517 লিখবে।</p>
<input id="period" type="text" inputmode="numeric"
maxlength="5" placeholder="Enter 5 digit period">
<input id="number" type="number" inputmode="numeric"
min="0" max="9" placeholder="Result number 0-9">
<button id="addButton" onclick="addResult()">ADD RESULT</button>
<div id="message"></div>
<p class="note">BIG = 5-9 | SMALL = 0-4</p>
</div>

<div class="card">
<div class="heading" style="text-align:center">RESULT HISTORY</div>
<div id="history">No results yet</div>
</div>

<p class="note">Auto refresh every 5 seconds.</p>
</div>

<script>
async function refresh(){
 try{
  const r = await fetch('/api/state');
  const d = await r.json();

  document.getElementById('next').textContent = d.next_period;
  document.getElementById('total').textContent = d.total;
  document.getElementById('count').textContent = d.total;
  document.getElementById('accuracy').textContent = d.accuracy + '%';
  document.getElementById('confidence').textContent = d.confidence + '%';
  document.getElementById('big').textContent = d.big;
  document.getElementById('small').textContent = d.small;
  document.getElementById('wins').textContent = d.wins;
  document.getElementById('losses').textContent = d.losses;
  document.getElementById('checked').textContent = d.checked;

  const signal = document.getElementById('signal');
  signal.textContent = d.signal;
  signal.className = 'signal ' + d.signal.toLowerCase();

  document.getElementById('analysisNote').textContent =
    d.total < 5 ? 'Need at least 5 results.' :
    'Analysis uses latest ' + Math.min(d.total, 20) + ' results.';

  const h = await fetch('/api/history');
  const hd = await h.json();

  document.getElementById('history').innerHTML =
    hd.results.slice().reverse().map(x =>
      '<div class="history"><span>' + x.period +
      '</span><b>' + x.number + '</b><span>' +
      x.side + '</span><b>' + x.outcome + '</b></div>'
    ).join('') || 'No results yet';

 }catch(e){
  document.getElementById('message').textContent = 'Connection error';
 }
}

async function addResult(){
 const p = document.getElementById('period').value.trim();
 const n = document.getElementById('number').value.trim();
 const msg = document.getElementById('message');
 const btn = document.getElementById('addButton');

 if(!/^[0-9]{5}$/.test(p)){
  msg.textContent = 'Enter exactly 5 period digits';
  return;
 }

 if(!/^[0-9]$/.test(n)){
  msg.textContent = 'Enter result number 0-9';
  return;
 }

 btn.disabled = true;
 msg.textContent = 'Adding result...';

 try{
  const r = await fetch('/api/add',{
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({period:p,number:Number(n)})
  });

  const d = await r.json();
  msg.textContent = d.message || d.error;

  if(r.ok){
   document.getElementById('period').value = '';
   document.getElementById('number').value = '';
   await refresh();
  }
 }catch(e){
  msg.textContent = 'Connection error';
 }finally{
  btn.disabled = false;
 }
}

refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""


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

        elif path == "/health":
            self.send_json({"status": "ACTIVE"})

        elif path == "/api/state":
            with lock:
                data = analyze()
            self.send_json(data)

        elif path == "/api/history":
            with lock:
                data = list(results)
            self.send_json({"results": data})

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path.split("?")[0] != "/api/add":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 1000:
                raise ValueError("Invalid request")

            data = json.loads(self.rfile.read(length).decode("utf-8"))

            if not isinstance(data, dict):
                raise ValueError("Invalid data")

            period = data.get("period")
            number = data.get("number")

            if not isinstance(period, str) or len(period) != 5 or not period.isdigit():
                raise ValueError("Enter exactly 5 period digits")

            if isinstance(number, bool) or not isinstance(number, int) or not 0 <= number <= 9:
                raise ValueError("Enter result number 0-9")

            with lock:
                if any(x["period"] == period for x in results):
                    raise ValueError("This period already exists")

                prediction = analyze()["signal"]
                actual = get_side(number)

                if prediction == "WAIT":
                    outcome = "SKIP"
                elif prediction == actual:
                    outcome = "WIN"
                else:
                    outcome = "LOSS"

                results.append({
                    "period": period,
                    "number": number,
                    "side": actual,
                    "prediction": prediction,
                    "outcome": outcome,
                    "time": datetime.now(timezone.utc).isoformat()
                })

                del results[:-100]
                save_results()

            self.send_json({
                "success": True,
                "message": "Result added: " + outcome,
                "prediction": prediction,
                "actual": actual,
                "outcome": outcome
            })

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send_json({"error": str(e)}, 400)
        except OSError:
            self.send_json({"error": "Could not save result"}, 500)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    load_results()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("WINGO BOT ACTIVE ON PORT", PORT, flush=True)
    server.serve_forever()