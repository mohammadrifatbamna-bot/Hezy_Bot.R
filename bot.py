#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wingo BIG/SMALL Ultra statistical ensemble dashboard.

This program uses several transparent statistical indicators. It is not a
trained machine-learning model and cannot guarantee future Wingo outcomes.
Digits are entered manually after each period has finished.
"""
import json
import os
import tempfile
from pathlib import Path
from threading import Lock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
DATA_DIR = Path(os.environ.get("DATA_DIR", "."))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "results.json"

lock = Lock()
results = []
wins = 0
losses = 0
pending = None
settled = []

# These are statistical engines, not separate trained AI models.
ENGINE_WEIGHTS = {
    "স্বল্পমেয়াদি ফ্রিকোয়েন্সি": 1.0,
    "দীর্ঘমেয়াদি ফ্রিকোয়েন্সি": 1.0,
    "ওয়েটেড রিসেন্সি": 1.2,
    "মার্কভ চেইন": 1.0,
    "দুই-ধাপ প্যাটার্ন": 0.8,
    "মোমেন্টাম": 0.8,
    "স্ট্রিক": 0.4,
    "ডিজিট বণ্টন": 0.5,
}


def side(digit):
    return "BIG" if digit >= 5 else "SMALL"


def load_data():
    global results, wins, losses, pending, settled
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Saved data must be an object")
        clean = []
        for value in data.get("results", []):
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 9:
                clean.append(value)
            elif isinstance(value, str) and value.isdigit() and 0 <= int(value) <= 9:
                clean.append(int(value))
        results = clean[-5000:]
        wins = max(0, int(data.get("wins", 0)))
        losses = max(0, int(data.get("losses", 0)))
        p = data.get("pending")
        pending = p if isinstance(p, dict) and p.get("signal") in ("BIG", "SMALL") else None
        history = data.get("settled", [])
        settled = [x for x in history if isinstance(x, dict)][-500:]
    except FileNotFoundError:
        results, wins, losses, pending, settled = [], 0, 0, None, []
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        results, wins, losses, pending, settled = [], 0, 0, None, []


def save_data():
    payload = {
        "results": results[-5000:],
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "settled": settled[-500:],
    }
    fd, temp_path = tempfile.mkstemp(prefix="wingo_", suffix=".tmp", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(temp_path, DATA_FILE)
    finally:
        try:
            if os.path.exists(temp_path):
                os.remove(temp_path)
        except OSError:
            pass


def smoothed_frequency(sample):
    if not sample:
        return 50.0
    big_count = sum(1 for n in sample if n >= 5)
    return (big_count + 1) * 100.0 / (len(sample) + 2)


def markov_engine(data):
    if len(data) < 4:
        return 50.0
    last = side(data[-1])
    big = total = 0
    for i in range(len(data) - 1):
        if side(data[i]) == last:
            total += 1
            if side(data[i + 1]) == "BIG":
                big += 1
    return (big + 1) * 100.0 / (total + 2)


def recency_engine(data):
    sample = data[-30:]
    if not sample:
        return 50.0
    weights = [0.94 ** (len(sample) - 1 - i) for i in range(len(sample))]
    total = sum(weights)
    big_weight = sum(w for w, digit in zip(weights, sample) if digit >= 5)
    return 100.0 * big_weight / total if total else 50.0


def pattern_engine(data):
    if len(data) < 6:
        return 50.0
    labels = ["B" if n >= 5 else "S" for n in data]
    last_pair = tuple(labels[-2:])
    big = total = 0
    for i in range(len(labels) - 2):
        if tuple(labels[i:i + 2]) == last_pair:
            total += 1
            if labels[i + 2] == "B":
                big += 1
    return (big + 1) * 100.0 / (total + 2)


def momentum_engine(data):
    if len(data) < 10:
        return 50.0
    short_rate = sum(n >= 5 for n in data[-5:]) / 5.0
    long_sample = data[-20:]
    long_rate = sum(n >= 5 for n in long_sample) / len(long_sample)
    # Keep the adjustment deliberately small.
    return max(38.0, min(62.0, 50.0 + (short_rate - long_rate) * 25.0))


def streak_engine(data):
    if len(data) < 3:
        return 50.0
    last_side = side(data[-1])
    length = 0
    for digit in reversed(data):
        if side(digit) != last_side:
            break
        length += 1
    bias = 3.0 if length == 1 else 1.5 if length == 2 else 0.0
    return 50.0 + bias if last_side == "BIG" else 50.0 - bias


def volatility(data):
    sample = data[-20:]
    if len(sample) < 2:
        return 0.0
    diffs = [abs(sample[i] - sample[i - 1]) for i in range(1, len(sample))]
    return round(sum(diffs) / len(diffs), 2)


def get_engines(data):
    return {
        "স্বল্পমেয়াদি ফ্রিকোয়েন্সি": smoothed_frequency(data[-10:]),
        "দীর্ঘমেয়াদি ফ্রিকোয়েন্সি": smoothed_frequency(data[-100:]),
        "ওয়েটেড রিসেন্সি": recency_engine(data),
        "মার্কভ চেইন": markov_engine(data),
        "দুই-ধাপ প্যাটার্ন": pattern_engine(data),
        "মোমেন্টাম": momentum_engine(data),
        "স্ট্রিক": streak_engine(data),
        "ডিজিট বণ্টন": smoothed_frequency(data[-40:]),
    }


def calculate_prediction(data):
    if len(data) < 30:
        return {
            "signal": "WAIT",
            "direction": "WAIT",
            "confidence": 0.0,
            "big_percent": 50.0,
            "small_percent": 50.0,
            "votes_big": 0,
            "votes_small": 0,
            "votes_neutral": len(ENGINE_WEIGHTS),
            "reason": f"কমপক্ষে ৩০টি ফলাফল দরকার। আরও {30 - len(data)}টি যোগ করো।",
            "engines": {},
            "volatility": volatility(data),
        }

    engines = get_engines(data)
    weight_sum = sum(ENGINE_WEIGHTS.values())
    big_score = sum(engines[name] * ENGINE_WEIGHTS[name] for name in ENGINE_WEIGHTS) / weight_sum
    small_score = 100.0 - big_score
    margin = abs(big_score - small_score)
    direction = "BIG" if big_score > small_score else "SMALL"

    votes_big = sum(1 for value in engines.values() if value > 53.0)
    votes_small = sum(1 for value in engines.values() if value < 47.0)
    votes_neutral = len(engines) - votes_big - votes_small
    agreement = max(votes_big, votes_small) / max(1, len(engines))

    # This is an agreement score, not a calibrated probability of winning.
    confidence = min(95.0, 50.0 + margin * 0.55 + agreement * 12.0)

    if max(votes_big, votes_small) < 6:
        signal, reason = "WAIT", "৮টি ইঞ্জিনের মধ্যে অন্তত ৬টি একমত নয়।"
    elif margin < 8.0:
        signal, reason = "WAIT", "BIG ও SMALL স্কোরের পার্থক্য কম।"
    elif volatility(data) >= 4.2:
        signal, reason = "WAIT", "সাম্প্রতিক ফলাফলে অস্থিরতা বেশি; ঝুঁকি এড়াতে WAIT।"
    else:
        signal, reason = direction, "একাধিক পরিসংখ্যানভিত্তিক ইঞ্জিন একই দিকে ইঙ্গিত করছে।"

    return {
        "signal": signal,
        "direction": direction,
        "confidence": round(confidence, 1),
        "big_percent": round(big_score, 1),
        "small_percent": round(small_score, 1),
        "votes_big": votes_big,
        "votes_small": votes_small,
        "votes_neutral": votes_neutral,
        "reason": reason,
        "engines": {
            name: round(value, 1) for name, value in engines.items()
        },
        "volatility": volatility(data),
    }


def backtest(data):
    """Walk-forward historical check; each estimate uses only earlier digits."""
    tested = correct = 0
    for index in range(30, len(data)):
        estimate = calculate_prediction(data[:index])["signal"]
        if estimate not in ("BIG", "SMALL"):
            continue
        tested += 1
        if estimate == side(data[index]):
            correct += 1
    return {
        "tested": tested,
        "correct": correct,
        "accuracy": round(100.0 * correct / tested, 1) if tested else 0.0,
    }


def analyze():
    output = calculate_prediction(results)
    output["pattern"] = "".join("B" if n >= 5 else "S" for n in results[-10:])
    if len(results) >= 10:
        recent_big = sum(n >= 5 for n in results[-10:])
        output["trend"] = "BIG TREND" if recent_big > 5 else (
            "SMALL TREND" if recent_big < 5 else "NEUTRAL"
        )
    else:
        output["trend"] = "WAIT"
    output["backtest"] = backtest(results) if len(results) >= 31 else {
        "tested": 0, "correct": 0, "accuracy": 0.0
    }
    return output


def get_state():
    prediction = analyze()
    last20 = results[-20:]
    last5 = settled[-5:]
    last5_wins = sum(1 for item in last5 if item.get("win") is True)
    last5_losses = sum(1 for item in last5 if item.get("win") is False)
    checked = wins + losses
    return {
        **prediction,
        "count": len(results),
        "big": sum(n >= 5 for n in last20),
        "small": sum(n < 5 for n in last20),
        "wins": wins,
        "losses": losses,
        "checked": checked,
        "win_rate": round(wins * 100.0 / checked, 1) if checked else 0.0,
        "history": results[-40:],
        "last5_wins": last5_wins,
        "last5_losses": last5_losses,
        "last5_total": len(last5),
        "last5": last5,
        "pending": pending,
    }


HTML = r"""<!doctype html>
<html lang="bn">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Wingo Ultra AI</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:13px;background:#070c17;color:#f4f7ff;font-family:Arial,sans-serif}
.main{max-width:740px;margin:auto}
h1{text-align:center;color:#42e6b1;font-size:25px}
.card{background:#121e33;border:1px solid #293c5b;border-radius:18px;padding:17px;margin:13px 0}
.center{text-align:center}
.muted{color:#a9bad0;font-size:13px;line-height:1.5}
.signal{font-size:clamp(65px,19vw,112px);font-weight:900;line-height:1.05;margin:12px 0}
.green{color:#27e6a3;text-shadow:0 0 22px #13a87855}
.red{color:#ff5f79;text-shadow:0 0 22px #d22d4d55}
.yellow{color:#ffd166}
.conf{font-size:30px;font-weight:800}
.bar{height:14px;background:#293a52;border-radius:20px;overflow:hidden;margin:12px 0}
.fill{height:100%;background:linear-gradient(90deg,#11b981,#7af0c4);width:0}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.stat{background:#0a1528;padding:13px;border-radius:11px;text-align:center;color:#b8c9df}
.stat b{display:block;font-size:25px;color:white;margin-top:7px}
input{width:100%;padding:15px;font-size:24px;text-align:center;background:#091426;color:white;border:1px solid #425b7a;border-radius:10px}
button{width:100%;padding:15px;margin-top:10px;border:0;border-radius:10px;background:#17c99a;color:#001b15;font-weight:bold;font-size:17px}
.engine{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.engine div{background:#0a1528;border-radius:9px;padding:10px;font-size:13px}
.history{display:flex;flex-wrap:wrap;gap:7px}
.num{background:#293a52;padding:9px 12px;border-radius:7px}
table{width:100%;border-collapse:collapse;font-size:13px}
td,th{padding:9px 5px;border-bottom:1px solid #293c5b;text-align:left}
.good{color:#2ee5a5}.bad{color:#ff7187}
</style></head>
<body><div class="main">
<h1>⚡ WINGO ULTRA AI</h1>
<div class="card center">
<div class="muted">পরের রাউন্ডের বিশ্লেষণ</div>
<div id="signal" class="signal yellow">WAIT</div>
<div class="muted">এটি ইঞ্জিনের সম্মতির স্কোর, জয়ের নিশ্চয়তা নয়</div>
<div id="confidence" class="conf">0%</div>
<div class="bar"><div id="fill" class="fill"></div></div>
<p id="reason" class="muted">বিশ্লেষণ শুরু করতে ফলাফল যোগ করো।</p>
<div class="grid">
<div class="stat">BIG স্কোর<b id="bp">50%</b></div>
<div class="stat">SMALL স্কোর<b id="sp">50%</b></div>
</div>
</div>
<div class="card">
<b>সর্বশেষ ফলাফল যোগ করো (০–৯)</b>
<input id="digit" type="number" min="0" max="9" inputmode="numeric" placeholder="একটি সংখ্যা লিখো">
<button onclick="addResult()">ফলাফল সেভ করো</button>
<p id="status" class="muted"></p>
<p class="muted">রাউন্ড শেষ হওয়ার পর প্রকৃত ফলাফল একবারই যোগ করবে।</p>
</div>
<div class="card">
<b>শেষ ৫টি যাচাই করা সিগন্যাল</b>
<div class="grid">
<div class="stat">সঠিক<b id="last5wins">0</b></div>
<div class="stat">ভুল<b id="last5losses">0</b></div>
</div>
<p class="muted" id="last5text">এখনও পর্যাপ্ত যাচাই করা সিগন্যাল নেই।</p>
</div>
<div class="card">
<b>পরিসংখ্যান</b>
<div class="grid">
<div class="stat">BIG · শেষ ২০<b id="big">0</b></div>
<div class="stat">SMALL · শেষ ২০<b id="small">0</b></div>
<div class="stat">মোট ফলাফল<b id="count">0</b></div>
<div class="stat">যাচাই হয়েছে<b id="checked">0</b></div>
<div class="stat">মোট WIN<b id="wins">0</b></div>
<div class="stat">মোট LOSS<b id="losses">0</b></div>
</div>
</div>
<div class="card">
<b>AI / Statistical Engines</b>
<div class="engine" id="engines"></div>
<p class="muted">ইঞ্জিনগুলো হলো পরিসংখ্যানভিত্তিক নিয়ম; এগুলো আলাদা প্রশিক্ষিত AI মডেল নয়।</p>
</div>
<div class="card">
<b>ব্যাকটেস্ট</b>
<p>পরীক্ষিত: <b id="tested">0</b></p>
<p>সঠিক: <b id="correct">0</b></p>
<p>ঐতিহাসিক সঠিকতার হার: <b id="accuracy">0%</b></p>
<p class="muted">অতীতের ফল ভবিষ্যতের ফল নিশ্চিত করে না।</p>
</div>
<div class="card">
<b>প্যাটার্ন ও ট্রেন্ড</b>
<p>প্যাটার্ন: <b id="pattern">-</b></p>
<p>ট্রেন্ড: <b id="trend">-</b></p>
<p>ভোলাটিলিটি: <b id="volatility">0</b></p>
</div>
<div class="card">
<b>সাম্প্রতিক ফলাফল</b>
<div class="history" id="history"></div>
</div>
<div class="card muted">Wingo ফলাফল অনিশ্চিত বা র‍্যান্ডম হতে পারে। কোনো AI বা অ্যালগরিদম ৫টির মধ্যে ৩–৪টি সিগন্যাল সঠিক হওয়ার নিশ্চয়তা দিতে পারে না। ঝুঁকি বুঝে ব্যবহার করো।</div>
</div>
<script>
async function refresh(){
 try{
  const response=await fetch('/api/state',{cache:'no-store'});
  const d=await response.json();
  const signal=document.getElementById('signal');
  signal.textContent=d.signal;
  signal.className='signal '+(d.signal==='BIG'?'green':d.signal==='SMALL'?'red':'yellow');
  document.getElementById('confidence').textContent=(d.confidence??0)+'%';
  document.getElementById('fill').style.width=Math.min(100,Math.max(0,d.confidence??0))+'%';
  document.getElementById('reason').textContent=d.reason||'';
  document.getElementById('bp').textContent=(d.big_percent??50)+'%';
  document.getElementById('sp').textContent=(d.small_percent??50)+'%';
  ['big','small','count','checked','wins','losses','last5_wins','last5_losses'].forEach(k=>{
   const target=k==='last5_wins'?'last5wins':k==='last5_losses'?'last5losses':k;
   const el=document.getElementById(target); if(el) el.textContent=d[k]??0;
  });
  document.getElementById('last5text').textContent='শেষ '+(d.last5_total??0)+'টি যাচাই করা সিগন্যালের মধ্যে '+(d.last5_wins??0)+'টি সঠিক, '+(d.last5_losses??0)+'টি ভুল।';
  document.getElementById('pattern').textContent=d.pattern||'-';
  document.getElementById('trend').textContent=d.trend||'-';
  document.getElementById('volatility').textContent=d.volatility??0;
  const bt=d.backtest||{};
  document.getElementById('tested').textContent=bt.tested??0;
  document.getElementById('correct').textContent=bt.correct??0;
  document.getElementById('accuracy').textContent=(bt.accuracy??0)+'%';
  document.getElementById('history').innerHTML=(d.history||[]).map(n=>'<span class="num">'+n+'</span>').join('');
  const engineBox=document.getElementById('engines');
  engineBox.innerHTML='';
  Object.entries(d.engines||{}).forEach(([name,value])=>{
   const item=document.createElement('div');
   item.textContent=name+': '+value+'% BIG';
   engineBox.appendChild(item);
  });
 }catch(e){document.getElementById('status').textContent='সার্ভারের সঙ্গে সংযোগ হচ্ছে না।';}
}
async function addResult(){
 const input=document.getElementById('digit');
 const status=document.getElementById('status');
 const value=input.value.trim();
 if(!/^[0-9]$/.test(value)){status.textContent='০ থেকে ৯-এর মধ্যে একটি সংখ্যা দাও।';return;}
 try{
  const response=await fetch('/api/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({digit:Number(value)})});
  const data=await response.json();
  if(!response.ok)throw new Error(data.error||'সেভ করা যায়নি');
  input.value='';
  status.textContent='ফলাফল সেভ হয়েছে।';
  await refresh();
 }catch(e){status.textContent=e.message;}
}
document.getElementById('digit').addEventListener('keydown',e=>{if(e.key==='Enter')addResult();});
refresh();
setInterval(refresh,5000);
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def send_text(self, status, body, content_type="application/json; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_text(200, HTML, "text/html; charset=utf-8")
        elif self.path == "/health":
            self.send_text(200, json.dumps({"status": "ok"}))
        elif self.path == "/api/state":
            with lock:
                data = get_state()
            self.send_text(200, json.dumps(data, ensure_ascii=False))
        else:
            self.send_text(404, json.dumps({"error": "Not found"}))

    def do_POST(self):
        global pending, wins, losses, results, settled
        if self.path != "/api/add":
            self.send_text(404, json.dumps({"error": "Not found"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            digit = payload.get("digit") if isinstance(payload, dict) else None
            if isinstance(digit, bool) or not isinstance(digit, int) or not 0 <= digit <= 9:
                raise ValueError("০ থেকে ৯-এর মধ্যে একটি পূর্ণসংখ্যা দাও")

            with lock:
                # Score the previous prediction against this newly entered result.
                if pending and pending.get("signal") in ("BIG", "SMALL"):
                    actual = side(digit)
                    won = pending["signal"] == actual
                    if won:
                        wins += 1
                    else:
                        losses += 1
                    settled.append({
                        "signal": pending["signal"],
                        "actual": actual,
                        "digit": digit,
                        "win": won,
                    })
                    settled = settled[-500:]

                results.append(digit)
                results = results[-5000:]
                next_prediction = calculate_prediction(results)
                pending = {
                    "signal": next_prediction["signal"],
                    "confidence": next_prediction["confidence"],
                } if next_prediction["signal"] in ("BIG", "SMALL") else None
                save_data()
                state = get_state()
            self.send_text(200, json.dumps(state, ensure_ascii=False))
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_text(400, json.dumps({"error": str(error)}, ensure_ascii=False))
        except OSError as error:
            print("Save error:", repr(error), flush=True)
            self.send_text(500, json.dumps({"error": "ডেটা সেভ করা যায়নি"}, ensure_ascii=False))

    def log_message(self, fmt, *args):
        print(fmt % args, flush=True)


if __name__ == "__main__":
    load_data()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("WINGO ULTRA AI DASHBOARD STARTED", flush=True)
    print("Listening on port:", PORT, flush=True)
    server.serve_forever()