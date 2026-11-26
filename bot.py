import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "8000"))
DATA_FILE = Path("results.json")


def load_results():
    try:
        data = json.loads(DATA_FILE.read_text())
        return [int(n) for n in data if 0 <= int(n) <= 9][-500:]
    except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
        return []


results = load_results()


def save_results():
    DATA_FILE.write_text(json.dumps(results[-500:]))


def analyze():
    recent = results[-20:]
    total = len(recent)
    big = sum(n >= 5 for n in recent)
    small = total - big

    if total < 5:
        signal = "WAIT"
        reason = "কমপক্ষে ৫টি ফলাফল যোগ করুন"
    elif big / total >= 0.60:
        signal = "BIG"
        reason = "সাম্প্রতিক ফলাফলে BIG বেশি"
    elif small / total >= 0.60:
        signal = "SMALL"
        reason = "সাম্প্রতিক ফলাফলে SMALL বেশি"
    else:
        signal = "WAIT"
        reason = "স্পষ্ট প্রবণতা পাওয়া যায়নি"

    return {
        "signal": signal,
        "big": big,
        "small": small,
        "total": total,
        "reason": reason,
        "history": recent[::-1]
    }


HTML = """<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>WinGo 30s Analyzer</title>
<style>
*{box-sizing:border-box}
body{margin:0;padding:16px;background:#07111f;color:white;font-family:Arial}
h1{text-align:center;color:#facc15}
.card{background:#12233b;border:1px solid #29476b;border-radius:16px;padding:18px;margin:14px auto;max-width:500px}
.signal{text-align:center;font-size:42px;font-weight:bold;padding:18px;border-radius:12px;background:#063d2a;color:#20f58a}
.signal.SMALL{background:#45151e;color:#ff6677}
.signal.WAIT{background:#39300e;color:#ffe16a}
.stats{display:flex;justify-content:space-around;text-align:center}
.num{font-size:28px;font-weight:bold}
input{width:100%;padding:14px;border-radius:9px;border:0;font-size:20px}
button{width:100%;padding:14px;margin-top:10px;border:0;border-radius:9px;background:#0878ff;color:white;font-size:18px;font-weight:bold}
.history{display:flex;flex-wrap:wrap;gap:8px}
.ball{padding:10px 13px;border-radius:50%;background:#087b43;font-weight:bold}
.ball.small{background:#c32636}
.note{color:#b7c7da;text-align:center;font-size:13px}
</style>
</head>
<body>
<h1>WinGo 30 Seconds</h1>

<div class="card">
<p class="note">CURRENT ANALYSIS</p>
<div id="signal" class="signal WAIT">WAIT</div>
<p id="reason" style="text-align:center">Loading...</p>
</div>

<div class="card stats">
<div><div class="num" id="big">0</div>BIG</div>
<div><div class="num" id="small">0</div>SMALL</div>
<div><div class="num" id="total">0</div>TOTAL</div>
</div>

<div class="card">
<h3>Add New Result (0-9)</h3>
<input id="number" type="number" min="0" max="9" placeholder="Enter number 0-9">
<button onclick="addResult()">ADD RESULT</button>
<p id="message" class="note"></p>
</div>

<div class="card">
<h3>Recent Results</h3>
<div id="history" class="history"></div>
<button onclick="refreshData()">REFRESH ANALYSIS</button>
</div>

<p class="note">Manual results only. No live HGNICE feed connected.
Past frequency cannot guarantee future results.</p>

<script>
async function refreshData(){
  try{
    const response = await fetch('/api/analyze');
    const data = await response.json();

    const signal = document.getElementById('signal');
    signal.textContent = data.signal;
    signal.className = 'signal ' + data.signal;

    document.getElementById('reason').textContent = data.reason;
    document.getElementById('big').textContent = data.big;
    document.getElementById('small').textContent = data.small;
    document.getElementById('total').textContent = data.total;

    const history = document.getElementById('history');
    history.replaceChildren();

    data.history.forEach(n => {
      const ball = document.createElement('span');
      ball.className = 'ball' + (n < 5 ? ' small' : '');
      ball.textContent = n;
      history.appendChild(ball);
    });
  }catch(error){
    document.getElementById('reason').textContent = 'Server connection error';
  }
}

async function addResult(){
  const input = document.getElementById('number');
  const n = input.value;
  const message = document.getElementById('message');

  if(n === '' || !Number.isInteger(Number(n)) ||
     Number(n) < 0 || Number(n) > 9){
    message.textContent = 'Enter a number from 0 to 9';
    return;
  }

  try{
    const response = await fetch('/api/add', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({number:Number(n)})
    });

    const data = await response.json();
    message.textContent = data.message;

    if(response.ok){
      input.value = '';
      await refreshData();
    }
  }catch(error){
    message.textContent = 'Could not connect to server';
  }
}

refreshData();
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
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/api/analyze":
            self.send_json(analyze())

        elif self.path == "/api/history":
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
                raise ValueError("Invalid request")

            data = json.loads(self.rfile.read(length))
            number = data.get("number")

            if isinstance(number, bool) or not isinstance(number, int):
                raise ValueError("Number must be an integer")

            if not 0 <= number <= 9:
                raise ValueError("Number must be 0 to 9")

            results.append(number)
            del results[:-500]
            save_results()

            self.send_json({
                "message": "Result added successfully",
                "analysis": analyze()
            })

        except (ValueError, TypeError, json.JSONDecodeError):
            self.send_json({"message": "Invalid number. Enter 0 to 9."}, 400)

    def log_message(self, format, *args):
        pass


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"WinGo Analyzer running on port {PORT}")
    server.serve_forever()
