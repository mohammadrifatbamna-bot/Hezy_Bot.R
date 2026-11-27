t os
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock

PORT = int(os.environ.get("PORT", "8000"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "results.json"

MAX_RESULTS = 5000
MIN_HISTORY = 20
LOCK = RLock()

DATA = {
    "results": [],
    "wins": 0,
    "losses": 0,
    "checked": 0,
    "prediction_log": [],
    "updated": None
}


def now():
    return datetime.now(timezone.utc).isoformat()


def save_data():
    DATA["updated"] = now()
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps(DATA, ensure_ascii=False),
        encoding="utf-8"
    )
    temp.replace(DATA_FILE)


def load_data():
    global DATA

    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))

        results = loaded.get("results", [])
        results = [
            int(x) for x in results
            if isinstance(x, int) and not isinstance(x, bool)
            and 0 <= x <= 9
        ]

        DATA["results"] = results[-MAX_RESULTS:]
        DATA["wins"] = max(0, int(loaded.get("wins", 0)))
        DATA["losses"] = max(0, int(loaded.get("losses", 0)))
        DATA["checked"] = max(0, int(loaded.get("checked", 0)))
        DATA["prediction_log"] = loaded.get("prediction_log", [])[-500:]
        DATA["updated"] = loaded.get("updated")

    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def is_big(n):
    return n >= 5


def get_features(results):
    bits = [int(is_big(n)) for n in results]

    if not bits:
        return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    last = bits[-1]

    streak = 1
    for value in reversed(bits[:-1]):
        if value == last:
            streak += 1
        else:
            break

    def ratio(size):
        part = bits[-size:]
        return sum(part) / len(part) if part else 0.5

    return [
        1.0,
        float(last),
        min(streak, 10) / 10,
        ratio(5) - 0.5,
        ratio(10) - 0.5,
        ratio(20) - 0.5,
        ratio(50) - 0.5
    ]


def sigmoid(x):
    x = max(-25, min(25, x))
    return 1 / (1 + math.exp(-x))


def train_model(results):
    weights = [0.0] * 7

    if len(results) < MIN_HISTORY:
        return weights

    # Train using historical next-result examples.
    samples = []

    for i in range(10, len(results)):
        x = get_features(results[:i])
        target = int(is_big(results[i]))
        samples.append((x, target))

    if not samples:
        return weights

    learning_rate = 0.035
    regularization = 0.015

    # Regularized online logistic regression.
    for epoch in range(8):
        for x, target in samples:
            prediction = sigmoid(
                sum(w * v for w, v in zip(weights, x))
            )
            error = prediction - target

            for j in range(len(weights)):
                weights[j] -= learning_rate * (
                    error * x[j] + regularization * weights[j]
                )

    return weights


def analyze(results):
    total = len(results)

    if total < MIN_HISTORY:
        return {
            "signal": "WAIT",
            "confidence": 0,
            "big_probability": 50,
            "small_probability": 50,
            "total": total,
            "reason": f"Need {MIN_HISTORY - total} more results",
            "windows": {}
        }

    bits = [int(is_big(n)) for n in results]

    weights = train_model(results)
    features = get_features(results)

    ai_probability = sigmoid(
        sum(w * x for w, x in zip(weights, features))
    )

    # Transition probability
    last = bits[-1]
    transitions = [[], []]

    for i in range(1, len(bits)):
        transitions[bits[i - 1]].append(bits[i])

    transition_data = transitions[last]

    transition_probability = (
        (sum(transition_data) + 2) /
        (len(transition_data) + 4)
    )

    def ratio(size):
        part = bits[-size:]
        return sum(part) / len(part)

    recent5 = ratio(5)
    recent20 = ratio(20)
    recent50 = ratio(50)
    overall = sum(bits) / total

    # Combined statistical estimate
    probability = (
        ai_probability * 0.40 +
        transition_probability * 0.25 +
        recent5 * 0.10 +
        recent20 * 0.10 +
        recent50 * 0.10 +
        overall * 0.05
    )

    probability = max(0.05, min(0.95, probability))

    big_probability = probability * 100
    small_probability = (1 - probability) * 100

    confidence = max(big_probability, small_probability)

    if big_probability >= 58:
        signal = "BIG"
    elif small_probability >= 58:
        signal = "SMALL"
    else:
        signal = "WAIT"

    windows = {}

    for size in [5, 10, 20, 50, 100]:
        part = bits[-min(size, total):]
        big = sum(part)
        small = len(part) - big

        windows[str(size)] = {
            "big": big,
            "small": small,
            "total": len(part),
            "big_percent": round(big / len(part) * 100, 1)
        }

    return {
        "signal": signal,
        "confidence": round(confidence, 1),
        "big_probability": round(big_probability, 1),
        "small_probability": round(small_probability, 1),
        "total": total,
        "reason": "AI Model + Pattern + Trend + Transition",
        "windows": windows
    }


def backtest(results):
    # Walk-forward test: only earlier results are used.
    # This is a historical simulation, not a guarantee.
    start = max(MIN_HISTORY, len(results) - 200)
    wins = 0
    checked = 0

    for i in range(start, len(results)):
        prediction = analyze(results[:i])
        signal = prediction["signal"]

        if signal == "WAIT":
            continue

        actual = "BIG" if is_big(results[i]) else "SMALL"
        checked += 1

        if signal == actual:
            wins += 1

    accuracy = wins / checked * 100 if checked else 0

    return {
        "wins": wins,
        "checked": checked,
        "accuracy": round(accuracy, 1)
    }


def get_state():
    results = DATA["results"]
    analysis = analyze(results)

    actual_accuracy = (
        DATA["wins"] / DATA["checked"] * 100
        if DATA["checked"] else 0
    )

    return {
        "status": "ACTIVE",
        "period": len(results) + 1,
        "analysis": analysis,
        "wins": DATA["wins"],
        "losses": DATA["losses"],
        "checked": DATA["checked"],
        "accuracy": round(actual_accuracy, 1),
        "backtest": backtest(results),
        "history": results[-30:][::-1],
        "updated": DATA["updated"]
    }


HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Advanced AI Wingo</title>
<style>
*{box-sizing:border-box}
body{
 margin:0;background:#080d19;color:white;
 font-family:Arial,sans-serif;padding:15px
}
.container{max-width:650px;margin:auto}
h1{text-align:center;color:#36e6bb}
.sub{text-align:center;color:#91a2bb}
.card{
 background:#121d32;border:1px solid #263953;
 border-radius:15px;padding:17px;margin:13px 0
}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{
 background:#1b2b44;padding:13px;
 border-radius:10px;text-align:center
}
.stat small{color:#9db0c9}
.stat h2{margin:8px 0;color:#3ce4b7}
.signal{
 font-size:36px;font-weight:bold;
 text-align:center;padding:15px
}
.BIG{color:#28e5a3}
.SMALL{color:#ff7373}
.WAIT{color:#ffd36c}
input{
 width:100%;padding:15px;font-size:22px;
 text-align:center;background:#091426;
 color:white;border:1px solid #405675;border-radius:9px
}
button{
 width:100%;padding:14px;margin-top:10px;
 border:0;border-radius:9px;background:#18cba4;
 color:#001c16;font-size:17px;font-weight:bold
}
table{width:100%;border-collapse:collapse}
td,th{
 padding:10px;text-align:center;
 border-bottom:1px solid #293952
}
.muted{color:#94a7c0;font-size:13px}
.history{display:flex;flex-wrap:wrap;gap:7px}
.ball{background:#293e5c;padding:9px 12px;border-radius:8px}
#message{text-align:center;color:#38e4b9}
</style>
</head>
<body>
<div class="container">

<h1>🤖 ADVANCED AI WINGO</h1>
<p class="sub">Machine Learning • Smart Pattern • Live Analysis</p>

<div class="card">
 <div class="grid">
  <div class="stat"><small>BOT STATUS</small><h2>ACTIVE</h2></div>
  <div class="stat"><small>NEXT PERIOD</small><h2 id="period">1</h2></div>
 </div>
 <p class="sub">NEXT BIG / SMALL SIGNAL</p>
 <div class="signal WAIT" id="signal">WAIT</div>
 <p style="text-align:center">
 Model Confidence: <b id="confidence">0%</b>
 </p>
 <p class="muted" style="text-align:center" id="reason">
 Need more results
 </p>
</div>

<div class="card">
 <h3>📊 AI Probability</h3>
 <p>BIG: <b id="bigprob">50%</b></p>
 <div style="background:#293b53;height:12px;border-radius:10px">
  <div id="bigbar" style="height:12px;width:50%;background:#22d9a2;border-radius:10px"></div>
 </div>
 <p>SMALL: <b id="smallprob">50%</b></p>
 <div style="background:#293b53;height:12px;border-radius:10px">
  <div id="smallbar" style="height:12px;width:50%;background:#ff7474;border-radius:10px"></div>
 </div>
</div>

<div class="card">
 <h3>🏆 Actual WIN / LOSS</h3>
 <div class="grid">
  <div class="stat"><small>WIN</small><h2 id="wins">0</h2></div>
  <div class="stat"><small>LOSS</small><h2 id="losses">0</h2></div>
  <div class="stat"><small>CHECKED</small><h2 id="checked">0</h2></div>
  <div class="stat"><small>ACCURACY</small><h2 id="accuracy">0%</h2></div>
 </div>
 <p class="muted">Accuracy uses settled BIG/SMALL predictions only.</p>
</div>

<div class="card">
 <h3>🧪 Historical Backtesting</h3>
 <div class="grid">
  <div class="stat"><small>TEST WINS</small><h2 id="btwins">0</h2></div>
  <div class="stat"><small>TESTED</small><h2 id="bttotal">0</h2></div>
 </div>
 <p style="text-align:center">Backtest Accuracy: <b id="btaccuracy">0%</b></p>
 <p class="muted">Uses up to the latest 200 historical predictions.</p>
</div>

<div class="card">
 <h3>🧠 Period Analysis</h3>
 <table>
 <thead><tr><th>Period</th><th>BIG</th><th>SMALL</th><th>BIG %</th></tr></thead>
 <tbody id="windows"></tbody>
 </table>
</div>

<div class="card">
 <h3>➕ ADD ONE RESULT</h3>
 <p class="muted">Enter only the latest result from 0 to 9.</p>
 <input id="number" type="number" min="0" max="9" placeholder="0 - 9">
 <button onclick="addResult()">ADD RESULT</button>
 <p id="message"></p>
</div>

<div class="card">
 <h3>🕘 Recent Results</h3>
 <div id="history" class="history">No results</div>
</div>

<p class="muted" style="text-align:center">
 Statistical estimates only. No guaranteed prediction.
</p>
</div>

<script>
async function refresh(){
 try{
  const response=await fetch('/api/state');
  const d=await response.json();
  const a=d.analysis;

  document.getElementById('period').textContent=d.period;

  const signal=document.getElementById('signal');
  signal.textContent=a.signal;
  signal.className='signal '+a.signal;

  document.getElementById('confidence').textContent=a.confidence+'%';
  document.getElementById('reason').textContent=a.reason;

  document.getElementById('bigprob').textContent=a.big_probability+'%';
  document.getElementById('smallprob').textContent=a.small_probability+'%';

  document.getElementById('bigbar').style.width=a.big_probability+'%';
  document.getElementById('smallbar').style.width=a.small_probability+'%';

  document.getElementById('wins').textContent=d.wins;
  document.getElementById('losses').textContent=d.losses;
  document.getElementById('checked').textContent=d.checked;
  document.getElementById('accuracy').textContent=d.accuracy+'%';

  document.getElementById('btwins').textContent=d.backtest.wins;
  document.getElementById('bttotal').textContent=d.backtest.checked;
  document.getElementById('btaccuracy').textContent=d.backtest.accuracy+'%';

  let rows='';
  for(const [k,v] of Object.entries(a.windows)){
   rows+=`<tr><td>${k}</td><td>${v.big}</td><td>${v.small}</td><td>${v.big_percent}%</td></tr>`;
  }
  document.getElementById('windows').innerHTML=rows;

  document.getElementById('history').innerHTML=
   d.history.length
   ? d.history.map(n=>`<span class="ball">${n}</span>`).join('')
   : 'No results';

 }catch(e){
  document.getElementById('message').textContent='Connection error';
 }
}

async function addResult(){
 const input=document.getElementById('number');
 const n=input.value;

 if(n==='' || !Number.isInteger(Number(n)) ||
    Number(n)<0 || Number(n)>9){
  alert('Enter a number from 0 to 9');
  return;
 }

 try{
  const response=await fetch('/api/add',{
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({number:Number(n)})
  });

  const d=await response.json();

  if(!response.ok){
   alert(d.error || 'Could not add result');
   return;
  }

  input.value='';
  document.getElementById('message').textContent='Result added!';
  await refresh();

 }catch(e){
  alert('Server connection failed');
 }
}

document.getElementById('number').addEventListener('keydown',e=>{
 if(e.key==='Enter') addResult();
});

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
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/state":
            with LOCK:
                self.send_json(get_state())

        else:
            self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if self.path != "/api/add":
            self.send_json({"error": "Not found"}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))

            if length <= 0 or length > 10000:
                raise ValueError("Invalid request")

            payload = json.loads(self.rfile.read(length))

            if not isinstance(payload, dict):
                raise ValueError("Invalid data")

            n = payload.get("number")

            if isinstance(n, bool) or not isinstance(n, int) or not 0 <= n <= 9:
                raise ValueError("Number must be between 0 and 9")

            with LOCK:
                # The previous signal is evaluated against this new result.
                previous = analyze(DATA["results"])
                signal = previous["signal"]

                if signal in ("BIG", "SMALL"):
                    actual = "BIG" if is_big(n) else "SMALL"

                    DATA["checked"] += 1

                    DATA["prediction_log"].append({
                        "signal": signal,
                        "actual": actual,
                        "win": signal == actual,
                        "time": now()
                    })
                    DATA["prediction_log"] = DATA["prediction_log"][-500:]

                    if signal == actual:
                        DATA["wins"] += 1
                    else:
                        DATA["losses"] += 1

                DATA["results"].append(n)
                DATA["results"] = DATA["results"][-MAX_RESULTS:]

                save_data()
                state = get_state()

            self.send_json(state)

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send_json({"error": str(e)}, 400)

        except Exception:
            self.send_json({"error": "Internal server error"}, 500)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    load_data()

    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("ADVANCED AI WINGO BOT ACTIVE")
    print("Port:", PORT)
    server.serve_forever