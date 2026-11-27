import os
import json
from pathlib import Path
from threading import Lock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
FILE = DATA_DIR / "results.json"

lock = Lock()
results = []
wins = 0
losses = 0
pending = None


def load_data():
    global results, wins, losses, pending
    try:
        d = json.loads(FILE.read_text(encoding="utf-8"))
        if isinstance(d, dict):
            results = [int(x) for x in d.get("results", [])
                       if str(x).isdigit() and 0 <= int(x) <= 9][-5000:]
            wins = int(d.get("wins", 0))
            losses = int(d.get("losses", 0))
            pending = d.get("pending")
    except (OSError, ValueError, TypeError):
        results, wins, losses, pending = [], 0, 0, None


def save_data():
    FILE.write_text(json.dumps({
        "results": results,
        "wins": wins,
        "losses": losses,
        "pending": pending
    }), encoding="utf-8")


def side(n):
    return "BIG" if n >= 5 else "SMALL"


def frequency(data):
    if not data:
        return 50, 50
    b = sum(x >= 5 for x in data)
    s = len(data) - b
    return b * 100 / len(data), s * 100 / len(data)


def markov(data):
    if len(data) < 3:
        return 50, 50
    last = side(data[-1])
    b = s = total = 0
    for i in range(len(data) - 1):
        if side(data[i]) == last:
            total += 1
            if side(data[i + 1]) == "BIG":
                b += 1
            else:
                s += 1
    return (b + 1) * 100 / (total + 2), (s + 1) * 100 / (total + 2)


def trend(data):
    recent = data[-5:]
    if not recent:
        return "WAIT"
    b = sum(x >= 5 for x in recent)
    s = len(recent) - b
    if b > s:
        return "BIG TREND"
    if s > b:
        return "SMALL TREND"
    return "NEUTRAL"


def backtest(data):
    tested = correct = 0
    for i in range(5, len(data)):
        bp, sp = frequency(data[max(0, i - 20):i])
        if bp == sp:
            continue
        prediction = "BIG" if bp > sp else "SMALL"
        tested += 1
        if prediction == side(data[i]):
            correct += 1
    accuracy = round(correct * 100 / tested, 1) if tested else 0
    return {"tested": tested, "correct": correct, "accuracy": accuracy}


def analyze():
    if len(results) < 5:
        return {
            "signal": "WAIT",
            "confidence": 0,
            "reason": "Need 5 results"
        }

    bp, sp = frequency(results[-20:])
    mb, ms = markov(results)
    t = trend(results)

    big_score = bp * 0.55 + mb * 0.45
    small_score = sp * 0.55 + ms * 0.45

    if t == "BIG TREND":
        big_score += 3
    elif t == "SMALL TREND":
        small_score += 3

    total = big_score + small_score
    big_score = big_score * 100 / total
    small_score = 100 - big_score

    if big_score > small_score:
        signal = "BIG"
        confidence = big_score
    else:
        signal = "SMALL"
        confidence = small_score

    if confidence < 55:
        signal = "WAIT"

    return {
        "signal": signal,
        "confidence": round(confidence, 1),
        "big_percent": round(bp, 1),
        "small_percent": round(sp, 1),
        "markov_big": round(mb, 1),
        "markov_small": round(ms, 1),
        "trend": t,
        "pattern": "".join("B" if x >= 5 else "S" for x in results[-5:]),
        "backtest": backtest(results),
        "reason": "Frequency + Trend + Markov analysis"
    }


def get_state():
    a = analyze()
    recent = results[-20:]
    return {
        **a,
        "count": len(results),
        "big": sum(x >= 5 for x in recent),
        "small": sum(x < 5 for x in recent),
        "wins": wins,
        "losses": losses,
        "checked": wins + losses,
        "history": results[-30:]
    }


HTML = r"""<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ADVANCED WINGO AI</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:15px;background:#080d19;color:white;font-family:Arial}
.main{max-width:650px;margin:auto}
h2{text-align:center;color:#30e5b0}
.card{background:#142036;border:1px solid #293b57;border-radius:14px;padding:17px;margin:13px 0}
.center{text-align:center}
.signal{font-size:40px;font-weight:bold;margin:15px}
.green{color:#2ee5a5}.red{color:#ff637b}.yellow{color:#ffd166}
input{width:100%;padding:15px;font-size:23px;text-align:center;background:#091426;color:white;border:1px solid #425b7a;border-radius:9px}
button{width:100%;padding:15px;margin-top:10px;border:0;border-radius:9px;background:#17c99a;color:#001b15;font-weight:bold;font-size:17px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{background:#0b1629;padding:13px;border-radius:9px;text-align:center}
.stat b{display:block;font-size:23px;margin-top:7px}
.bar{height:12px;background:#293a52;border-radius:20px;overflow:hidden}
.fill{height:100%;background:#20d7a0}
.history{display:flex;flex-wrap:wrap;gap:7px}
.num{background:#293a52;padding:9px 12px;border-radius:7px}
.muted{color:#a9bad0;font-size:13px}
</style>
</head>
<body>
<div class="main">
<h2>⚡ ADVANCED AI WINGO BOT</h2>

<div class="card center">
<div class="muted">NEXT PERIOD SIGNAL</div>
<div id="signal" class="signal yellow">WAIT</div>
<div>Confidence: <b id="confidence">0%</b></div>
<div class="bar"><div id="fill" class="fill" style="width:0%"></div></div>
<p class="muted" id="reason">Add 5 results to start analysis.</p>
</div>

<div class="card">
<b>ADD LAST RESULT (0–9)</b>
<input id="digit" type="number" min="0" max="9" placeholder="Enter one digit">
<button onclick="addResult()">ADD RESULT</button>
<p class="muted" id="status"></p>
</div>

<div class="card">
<b>LIVE ANALYSIS</b>
<div class="grid">
<div class="stat">BIG<b id="big">0</b></div>
<div class="stat">SMALL<b id="small">0</b></div>
<div class="stat">SAVED<b id="count">0</b></div>
<div class="stat">CHECKED<b id="checked">0</b></div>
</div>
</div>

<div class="card">
<b>AI PATTERN ANALYSIS</b>
<p>Pattern: <b id="pattern">-</b></p>
<p>Trend: <b id="trend">-</b></p>
<p>Markov BIG: <b id="mb">0%</b></p>
<p>Markov SMALL: <b id="ms">0%</b></p>
<p>Frequency BIG: <b id="bp">0%</b></p>
<p>Frequency SMALL: <b id="sp">0%</b></p>
</div>

<div class="card">
<b>BACKTESTING</b>
<p>Tested: <b id="tested">0</b></p>
<p>Correct: <b id="correct">0</b></p>
<p>Historical Accuracy: <b id="accuracy">0%</b></p>
</div>

<div class="card">
<b>WIN / LOSS TRACKER</b>
<div class="grid">
<div class="stat">WIN<b id="wins">0</b></div>
<div class="stat">LOSS<b id="losses">0</b></div>
</div>
</div>

<div class="card">
<b>RECENT RESULTS</b>
<div class="history" id="history"></div>
</div>

<div class="card muted">
Statistical analysis only. Random outcomes cannot be reliably predicted.
Confidence is not a guarantee of winning.
</div>
</div>

<script>
async function refresh(){
 try{
  let r=await fetch('/api/state');
  let d=await r.json();
  let el=document.getElementById('signal');
  el.textContent=d.signal;
  el.className='signal '+(d.signal==='BIG'?'green':d.signal==='SMALL'?'red':'yellow');
  document.getElementById('confidence').textContent=d.confidence+'%';
  document.getElementById('fill').style.width=d.confidence+'%';
  document.getElementById('reason').textContent=d.reason||'';
  for(let k of ['big','small','count','wins','losses','checked'])
   document.getElementById(k).textContent=d[k]??0;
  document.getElementById('pattern').textContent=d.pattern||'-';
  document.getElementById('trend').textContent=d.trend||'-';
  document.getElementById('mb').textContent=(d.markov_big??0)+'%';
  document.getElementById('ms').textContent=(d.markov_small??0)+'%';
  document.getElementById('bp').textContent=(d.big_percent??0)+'%';
  document.getElementById('sp').textContent=(d.small_percent??0)+'%';
  let bt=d.backtest||{};
  document.getElementById('tested').textContent=bt.tested??0;
  document.getElementById('correct').textContent=bt.correct??0;
  document.getElementById('accuracy').textContent=(bt.accuracy??0)+'%';
  document.getElementById('history').innerHTML=d.history.map(x=>'<span class="num">'+x+'</span>').join('');
 }catch(e){}
}

async function addResult(){
 let input=document.getElementById('digit');
 let status=document.getElementById('status');
 let v=input.value.trim();
 if(!/^[0-9]$/.test(v)){
  status.textContent='Enter one digit from 0 to 9.';
  return;
 }
 try{
  let r=await fetch('/api/add',{
   method:'POST',
   headers:{'Content-Type':'application/json'},
   body:JSON.stringify({digit:Number(v)})
  });
  let d=await r.json();
  if(!r.ok)throw new Error(d.error||'Error');
  input.value='';
  status.textContent='Result saved successfully.';
  refresh();
 }catch(e){status.textContent=e.message;}
}
document.getElementById('digit').addEventListener('keydown',e=>{
 if(e.key==='Enter')addResult();
});
refresh();
setInterval(refresh,5000);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def send_data(self, code, data, content_type="application/json; charset=utf-8"):
        body = data.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            self.send_data(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/health":
            self.send_data(200, json.dumps({"status": "ok"}))
        elif self.path == "/api/state":
            with lock:
                data = get_state()
            self.send_data(200, json.dumps(data))
        else:
            self.send_data(404, json.dumps({"error": "Not found"}))

    def do_POST(self):
        global pending, wins, losses

        if self.path != "/api/add":
            self.send_data(404, json.dumps({"error": "Not found"}))
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 10000:
                raise ValueError("Invalid request")

            payload = json.loads(self.rfile.read(length))
            digit = payload.get("digit")

            if isinstance(digit, bool) or not isinstance(digit, int) or not 0 <= digit <= 9:
                raise ValueError("Enter a digit from 0 to 9")

            with lock:
                if pending and pending.get("signal") in ("BIG", "SMALL"):
                    actual = side(digit)
                    if pending["signal"] == actual:
                        wins += 1
                    else:
                        losses += 1

                results.append(digit)
                del results[:-5000]

                signal_data = analyze()
                pending = {
                    "signal": signal_data["signal"],
                    "confidence": signal_data["confidence"]
                }

                save_data()
                data = get_state()

            self.send_data(200, json.dumps(data))

        except (ValueError, TypeError, json.JSONDecodeError) as e:
            self.send_data(400, json.dumps({"error": str(e)}))
        except OSError as e:
            print("Save error:", e, flush=True)
            self.send_data(500, json.dumps({"error": "Could not save data"}))

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    load_data()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("ADVANCED AI WINGO BOT ACTIVE", flush=True)
    print("Listening on port:", PORT, flush=True)
    server.serve_forever()