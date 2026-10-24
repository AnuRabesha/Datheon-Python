import csv
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

BASE = Path(__file__).parent
SP500_FILE   = BASE / "sp500_constituents.csv"
PRICES_FILE  = BASE / "sample_prices.csv"
SUMMARY_FILE = BASE / "portfolio_summary.csv"


def load_data():
    prices, info = {}, {}
    with open(SP500_FILE, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sym = row["Symbol"].upper()
            info[sym] = {
                "name":     row["Security"],
                "sector":   row["GICS Sector"],
                "industry": row["GICS Sub-Industry"],
            }
    with open(PRICES_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                prices[row["ticker"].upper()] = float(row["current_price"])
            except (ValueError, KeyError):
                continue
    return prices, info


@app.route("/")
def index():
    prices, info = load_data()
    sectors = sorted(set(v["sector"] for v in info.values()))
    return render_template("index.html", sectors=sectors)


@app.route("/api/tickers")
def get_tickers():
    sector = request.args.get("sector", "")
    prices, info = load_data()
    tickers = []
    for sym, v in sorted(info.items()):
        if sym not in prices:
            continue
        if sector and v["sector"] != sector:
            continue
        tickers.append({
            "symbol":   sym,
            "name":     v["name"],
            "sector":   v["sector"],
            "industry": v["industry"],
            "price":    prices[sym],
        })
    return jsonify(tickers)


@app.route("/api/summary", methods=["POST"])
def compute_summary():
    data = request.json  # [{ticker, buy_price, shares}, ...]
    prices, info = load_data()
    rows = []
    for item in data:
        ticker    = item["ticker"].upper()
        buy_price = float(item["buy_price"])
        shares    = float(item["shares"])
        if ticker not in prices:
            continue
        current      = prices[ticker]
        invested     = round(buy_price * shares, 2)
        market_value = round(current * shares, 2)
        gain_loss    = round(market_value - invested, 2)
        pct          = round((gain_loss / invested) * 100, 2) if invested else 0
        meta         = info.get(ticker, {})
        rows.append({
            "ticker":        ticker,
            "name":          meta.get("name", ""),
            "sector":        meta.get("sector", ""),
            "industry":      meta.get("industry", ""),
            "shares":        shares,
            "buy_price":     buy_price,
            "current_price": current,
            "invested":      invested,
            "market_value":  market_value,
            "gain_loss":     gain_loss,
            "gain_loss_pct": pct,
        })
    return jsonify(rows)


@app.route("/api/save", methods=["POST"])
def save_csv():
    rows = request.json
    fieldnames = ["timestamp", "ticker", "name", "sector", "industry",
                  "shares", "buy_price", "current_price",
                  "invested", "market_value", "gain_loss", "gain_loss_pct"]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(SUMMARY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()
        for r in rows:
            writer.writerow({"timestamp": ts, **r})
    return jsonify({"message": f"Saved {len(rows)} rows to {SUMMARY_FILE.name}"})


if __name__ == "__main__":
    app.run(debug=True)
