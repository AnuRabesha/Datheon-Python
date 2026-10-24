import csv
from datetime import datetime, timezone
from pathlib import Path

SP500_FILE   = Path(__file__).parent / "sp500_constituents.csv"
PRICES_FILE  = Path(__file__).parent / "sample_prices.csv"
SUMMARY_FILE = Path(__file__).parent / "portfolio_summary.csv"


def load_data() -> tuple[dict, dict]:
    """Returns prices dict and company info dict keyed by ticker."""
    for path in (SP500_FILE, PRICES_FILE):
        if not path.exists():
            raise FileNotFoundError(
                f"Required data file not found: '{path}'\n"
                "Please ensure sp500_constituents.csv and sample_prices.csv "
                "are in the same directory as portfolio.py."
            )

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
                continue   # skip malformed price rows silently

    return prices, info


def get_input(prompt: str, cast, validate=None):
    """Prompt until a valid castable value passing validate() is entered."""
    while True:
        raw = input(prompt).strip()
        try:
            value = cast(raw)
        except (ValueError, TypeError):
            print(f"  Expected a valid {cast.__name__}, got '{raw}'. Try again.")
            continue
        if validate and not validate(value):
            print(f"  Value '{value}' is out of range. Try again.")
            continue
        return value


def browse_sectors(info):
    """Let user filter tickers by sector before picking."""
    sectors = sorted(set(v["sector"] for v in info.values()))
    print("\nAvailable sectors:")
    for i, s in enumerate(sectors, 1):
        print(f"  {i:>2}. {s}")
    choice = input("\nFilter by sector number (or press Enter to skip): ").strip()
    if not choice:
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(sectors):
            return sectors[idx]
    except ValueError:
        pass
    return None


def enter_holdings(prices, info):
    portfolio = {}

    sector_filter = browse_sectors(info)
    if sector_filter:
        visible = {k: v for k, v in info.items() if v["sector"] == sector_filter and k in prices}
        print(f"\n[{sector_filter}] — {len(visible)} tickers:")
        for sym, v in sorted(visible.items()):
            print(f"  {sym:<8} {v['name']}")
    else:
        print(f"\nAll {len(prices)} S&P 500 tickers available.")

    print("\nType 'done' when finished.\n")

    while True:
        ticker = input("Enter ticker symbol: ").upper().strip()
        if ticker == "DONE":
            break
        if ticker not in prices:
            print(f"  '{ticker}' not in S&P 500 price list.")
            continue
        if ticker in portfolio:
            print(f"  '{ticker}' already added.")
            continue

        company = info.get(ticker, {}).get("name", "")
        print(f"  {company} — current price: ${prices[ticker]:,.2f}")

        buy_price = get_input(f"  Buy price:        $", float, lambda x: x > 0)
        shares    = get_input(f"  Number of shares:  ", float, lambda x: x > 0)

        portfolio[ticker] = {"buy_price": buy_price, "shares": shares}
        print(f"  Added {ticker}.\n")

    return portfolio


def compute_summary(portfolio, prices, info):
    rows = []
    for ticker, data in portfolio.items():
        buy_price    = data["buy_price"]
        shares       = data["shares"]
        current      = prices[ticker]
        invested     = round(buy_price * shares, 2)
        market_value = round(current * shares, 2)
        gain_loss    = round(market_value - invested, 2)
        pct          = round((gain_loss / invested) * 100, 2)
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
    return rows


def print_summary(rows):
    total_invested = sum(r["invested"] for r in rows)
    total_value    = sum(r["market_value"] for r in rows)
    total_gl       = round(total_value - total_invested, 2)
    total_pct      = round((total_gl / total_invested) * 100, 2) if total_invested else 0

    print("\n" + "=" * 90)
    print(f"{'TICKER':<8} {'COMPANY':<28} {'SECTOR':<24} {'SHARES':>7} "
          f"{'BUY $':>9} {'NOW $':>9} {'G/L':>10} {'G/L %':>8}")
    print("-" * 90)

    for r in rows:
        sign = "+" if r["gain_loss"] >= 0 else "-"
        print(f"{r['ticker']:<8} {r['name'][:27]:<28} {r['sector'][:23]:<24} "
              f"{r['shares']:>7.2f} {r['buy_price']:>9.2f} {r['current_price']:>9.2f} "
              f"{r['gain_loss']:>10.2f} {sign}{abs(r['gain_loss_pct']):>6.2f}%")

    print("=" * 90)
    sign = "+" if total_gl >= 0 else "-"
    print(f"{'TOTAL':<8} {'':28} {'':24} {'':>7} "
          f"{'Invested':>9}  {'Value':>8} {total_gl:>10.2f} {sign}{abs(total_pct):>6.2f}%")
    print(f"{'':8} {'':28} {'':24} {'':>7} "
          f"{total_invested:>9,.2f}  {total_value:>8,.2f}")
    print("=" * 90)


def save_csv(rows: list[dict]) -> None:
    fieldnames = ["timestamp", "ticker", "name", "sector", "industry",
                  "shares", "buy_price", "current_price",
                  "invested", "market_value", "gain_loss", "gain_loss_pct"]

    # UTC-aware ISO 8601 timestamp (fixes naive datetime finding)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Atomic header check: open once in append mode, write header only if file is empty
    with open(SUMMARY_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:          # file was empty (new or just created)
            writer.writeheader()
        for r in rows:
            writer.writerow({"timestamp": ts, **r})

    print(f"\nSummary appended to '{SUMMARY_FILE}'")


def main() -> None:
    print("=" * 50)
    print("     S&P 500 Investment Portfolio Tracker")
    print("=" * 50)

    try:
        prices, info = load_data()
    except FileNotFoundError as exc:
        print(f"\nError: {exc}")
        return

    portfolio = enter_holdings(prices, info)

    if not portfolio:
        print("No holdings entered. Exiting.")
        return

    rows = compute_summary(portfolio, prices, info)
    print_summary(rows)
    save_csv(rows)


if __name__ == "__main__":
    main()
