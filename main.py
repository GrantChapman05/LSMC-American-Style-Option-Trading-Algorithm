import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional

import lsmc_engine
from config import tickers, start_date, end_date, T, strike_type, strike_pct, M, I, r, thresh
from paper_trader import PaperTrader

OPTION_TYPE = "Call"  # Tonight we trade calls; can generalize later

def compute_model_strike(spot: float, option_type: str) -> float:
    st = strike_type.upper()
    pct = float(strike_pct)
    if option_type.lower() == "call":
        if st == "ATM":
            return float(spot)
        elif st == "ITM":
            return float(spot) * (1 - pct)
        elif st == "OTM":
            return float(spot) * (1 + pct)
    else:  # put
        if st == "ATM":
            return float(spot)
        elif st == "ITM":
            return float(spot) * (1 + pct)
        elif st == "OTM":
            return float(spot) * (1 - pct)
    raise ValueError("STRIKE_TYPE must be one of ITM/ATM/OTM")

def select_strike_and_expiry(ticker: str, spot: float, option_type: str) -> Dict[str, Any]:
    tk = yf.Ticker(ticker)
    expirations = tk.options or []
    if not expirations:
        return {"ok": False, "reason": "No expirations"}

    # Parse expiry strings to dates
    exp_dates = []
    for s in expirations:
        try:
            y, m, d = map(int, s.split("-"))
            exp_dates.append((s, date(y, m, d)))
        except Exception:
            continue

    today = date.today()
    target = today + timedelta(days=int(round(float(T) * 365)))

    # Choose expiry >= today closest to target; if none, choose soonest > today
    candidates = [(s, d, (d - target).days) for (s, d) in exp_dates if d >= today]
    if candidates:
        # minimize absolute difference but prefer non-negative distance
        candidates.sort(key=lambda x: (abs(x[2]), x[2]))
        expiry_str, expiry_date, _ = candidates[0]
    else:
        # fallback to soonest in future
        exp_dates.sort(key=lambda x: x[1])
        expiry_str, expiry_date = exp_dates[0]

    # Choose model target strike consistent with policy
    target_strike = compute_model_strike(spot, option_type)
    return {"ok": True, "expiry_str": expiry_str, "expiry_date": expiry_date, "target_strike": float(target_strike)}

def get_option_market_price(ticker: str, expiry_str: str, strike: float, option_type: str) -> Dict[str, Any]:
    tk = yf.Ticker(ticker)
    try:
        chain = tk.option_chain(expiry_str)
    except Exception as e:
        return {"ok": False, "reason": f"Option chain error: {e}"}

    side = chain.calls if option_type.lower() == "call" else chain.puts
    if side is None or side.empty:
        return {"ok": False, "reason": "Empty option side"}

    # Choose listed strike nearest to our target strike
    side = side.copy()
    side["dist"] = (side["strike"] - float(strike)).abs()
    side = side.sort_values("dist")
    row = side.iloc[0]

    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    last = float(row.get("lastPrice", 0) or 0)

    mid = None
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2.0
    elif last > 0:
        mid = last
    elif bid > 0 and ask == 0:
        mid = bid
    elif ask > 0 and bid == 0:
        mid = ask

    if mid is None or mid <= 0:
        return {"ok": False, "reason": "No valid quotes"}

    return {
        "ok": True,
        "listed_strike": float(row["strike"]),
        "bid": bid if bid > 0 else None,
        "ask": ask if ask > 0 else None,
        "last": last if last > 0 else None,
        "mid_price": float(mid),
        "contract_symbol": row.get("contractSymbol", None)
    }

def run_once_for_ticker(ticker: str, trader: Optional[PaperTrader]) -> Dict[str, Any]:
    # Spot
    try:
        hist = yf.Ticker(ticker).history(period="1d")
        if hist is None or hist.empty:
            return {"ok": False, "ticker": ticker, "reason": "No spot"}
        spot = float(hist["Close"].iloc[-1])
    except Exception as e:
        return {"ok": False, "ticker": ticker, "reason": f"Spot error: {e}"}

    # History for vol
    try:
        prices = yf.download(ticker, start=start_date, end=end_date, progress=False)
        adj = prices["Adj Close"].dropna()
        if len(adj) < 30:
            return {"ok": False, "ticker": ticker, "reason": "Insufficient history"}
        log_ret = np.log(adj / adj.shift(1)).dropna()
        hist_sigma = float(log_ret.std()) * np.sqrt(252.0)
    except Exception as e:
        return {"ok": False, "ticker": ticker, "reason": f"History error: {e}"}

    # Select expiry/strike
    sel = select_strike_and_expiry(ticker, spot, OPTION_TYPE)
    if not sel.get("ok", False):
        return {"ok": False, "ticker": ticker, "reason": sel.get("reason", "expiry fail")}
    expiry_str = sel["expiry_str"]
    model_strike = float(sel["target_strike"])

    # Market price
    mkt = get_option_market_price(ticker, expiry_str, model_strike, OPTION_TYPE)
    if not mkt.get("ok", False):
        return {"ok": False, "ticker": ticker, "reason": mkt.get("reason", "quote fail")}
    listed_strike = float(mkt["listed_strike"])
    mid_price = float(mkt["mid_price"])

    # Paths + LSMC
    paths = lsmc_engine.genPricePaths(hist_sigma, spot, r, T, M, I)
    model_price = lsmc_engine.calcOptnPrice(paths, listed_strike, r, T, OPTION_TYPE)

    # Decision
    edge = (model_price - mid_price) / mid_price
    decision = "HOLD"
    if edge > float(thresh):
        decision = "BUY"
    elif edge < -float(thresh):
        decision = "SELL"

    # Execute (only if BUY/SELL and trader provided)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    optnID = f"{ticker}_{expiry_str}_{listed_strike:.2f}_{OPTION_TYPE}"
    if trader is not None:
        if decision == "BUY":
            trader.buyOptn(optnID, listed_strike, 1, mid_price, OPTION_TYPE.lower(), expiry_str, spot, ts)
        elif decision == "SELL":
            trader.sellOptn(optnID, mid_price, 1, ts, underlying_price=spot)

    return {
        "ok": True,
        "ticker": ticker,
        "spot": spot,
        "expiry": expiry_str,
        "listed_strike": listed_strike,
        "market_mid": mid_price,
        "model_price": model_price,
        "edge": edge,
        "decision": decision
    }

def main():
    trader = PaperTrader()
    results = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        res = run_once_for_ticker(t, trader)
        results.append(res)
        if res.get("ok"):
            print(f"{t} | {res['expiry']} @ {res['listed_strike']:.2f}: spot={res['spot']:.2f} mid={res['market_mid']:.2f} model={res['model_price']:.2f} edge={res['edge']*100:.2f}% decision={res['decision']}")
        else:
            print(f"{t} | SKIPPED - {res.get('reason')}")

    # Optional: show remaining cash
    portfolio = trader.getPortfolio()
    print(f\"\"\"\\nCash: {portfolio['cash']:.2f}  |  Positions: {len(portfolio['positions'])}  |  PnL: {portfolio['PnL']}\"\"\")

if __name__ == "__main__":
    main()
