import numpy as np
import pandas as pd
import yfinance as yf
import time
from datetime import datetime, date, timedelta
from datetime import time as dtime
from zoneinfo import ZoneInfo
from typing import Dict, Any, Optional

import lsmc_engine
from config import tickers, start_date, end_date, T, strike_type, strike_pct, M, I, r, thresh
from paper_trader import PaperTrader

STATE_PATH = "portfolio_state.json"

OPTION_TYPE = "Call"  #we trade calls; can generalize later

#compute strike model implemented with the idea of expansion
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
    else:  #put
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

    #parse expiry strings to dates
    exp_dates = []
    for s in expirations:
        try:
            y, m, d = map(int, s.split("-"))
            exp_dates.append((s, date(y, m, d)))
        except Exception:
            continue

    today = date.today()
    target = today + timedelta(days=int(round(float(T) * 365)))

    candidates = [(s, d, (d - target).days) for (s, d) in exp_dates if d >= today]
    if candidates:
        #minimize absolute difference but prefer non-negative distance
        candidates.sort(key=lambda x: (abs(x[2]), x[2]))
        expiry_str, expiry_date, _ = candidates[0]
    else:
        #fallback to soonest in future
        exp_dates.sort(key=lambda x: x[1])
        expiry_str, expiry_date = exp_dates[0]

    #choose model target strike consistent with policy
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

    df = side.copy()

    #coerce numeric, drop rows with no strike
    for col in ["strike", "bid", "ask", "lastPrice"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["strike"])
    if df.empty:
        return {"ok": False, "reason": "No strikes in chain"}

    #find nearest listed strike
    df["dist"] = (df["strike"] - float(strike)).abs()
    df = df.sort_values("dist")
    row = df.iloc[0]

    bid = float(row.get("bid") or 0)
    ask = float(row.get("ask") or 0)
    last = float(row.get("lastPrice") or 0)

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
    try:
        #spot ---
        tk = yf.Ticker(ticker)
        spot_hist = tk.history(period="1d", auto_adjust=True)
        if spot_hist is None or spot_hist.empty:
            return {"ok": False, "ticker": ticker, "reason": "No spot"}
        spot = float(spot_hist["Close"].iloc[-1])

        #history, making sigma 1-D
        prices = yf.download(
            ticker,
            start=start_date,
            end=end_date,
            progress=False,
            auto_adjust=True,
            group_by="column",
        )
        if prices is None or prices.empty:
            return {"ok": False, "ticker": ticker, "reason": "No historical data"}

        if "Close" in prices.columns:
            s = prices["Close"]
        elif "Adj Close" in prices.columns:
            s = prices["Adj Close"]
        else:
            s = prices.select_dtypes(include="number").iloc[:, 0]

        # ensure 1-D numeric ndarray
        arr = np.asarray(s, dtype="float64").reshape(-1)
        arr = arr[~np.isnan(arr)]
        if arr.size < 30:
            return {"ok": False, "ticker": ticker, "reason": "Insufficient history"}

        log_ret = np.diff(np.log(arr))
        sigma_daily = float(np.std(log_ret, ddof=1))
        hist_sigma = sigma_daily * np.sqrt(252.0)

        #exp and strike
        sel = select_strike_and_expiry(ticker, spot, OPTION_TYPE)
        if not sel.get("ok", False):
            return {"ok": False, "ticker": ticker, "reason": sel.get("reason", "expiry selection failed")}
        expiry_str = sel["expiry_str"]
        model_strike = float(sel["target_strike"])

        #mkt optn
        mkt = get_option_market_price(ticker, expiry_str, model_strike, OPTION_TYPE)
        if not mkt.get("ok", False):
            return {"ok": False, "ticker": ticker, "reason": mkt.get("reason", "quote retrieval failed")}
        listed_strike = float(mkt["listed_strike"])
        mid_price = float(mkt["mid_price"])

        #lsmc priced
        paths = lsmc_engine.genPricePaths(hist_sigma, spot, r, T, M, I)
        model_price = lsmc_engine.calcOptnPrice(paths, listed_strike, r, T, OPTION_TYPE)

        #decision
        edge = (model_price - mid_price) / max(mid_price, 1e-12)
        if edge > float(thresh):
            decision = "BUY"
        elif edge < -float(thresh):
            decision = "SELL"
        else:
            decision = "HOLD"

        #execution
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        optnID = f"{ticker}_{expiry_str}_{listed_strike:.2f}_{OPTION_TYPE}"

        executed = False
        if trader is not None:
            if decision == "BUY":
                executed = trader.buyOptn(optnID, listed_strike, 1, mid_price, OPTION_TYPE.lower(), expiry_str, spot, ts)
            elif decision == "SELL":
                executed = trader.sellOptn(optnID, mid_price, 1, ts, underlying_price=spot)

            if executed:
                #persist portfolio to disk after successful trade
                trader.save_state(STATE_PATH)

        #need to return some function
        return {
            "ok": True,
            "ticker": ticker,
            "spot": spot,
            "expiry": expiry_str,
            "listed_strike": listed_strike,
            "market_mid": mid_price,
            "model_price": model_price,
            "edge": edge,
            "decision": decision,
        }

    except Exception as e:
        #patch so it doesnt retun None
        return {"ok": False, "ticker": ticker, "reason": f"Unhandled error: {type(e).__name__}: {e}"}

def run_batch_once():
    trader = PaperTrader()
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        res = run_once_for_ticker(t, trader)
        if isinstance(res, dict) and res.get("ok"):
            print(f"{t} | {res['expiry']} @ {res['listed_strike']:.2f}: "
                  f"spot={res['spot']:.2f} mid={res['market_mid']:.2f} "
                  f"model={res['model_price']:.2f} edge={res['edge']*100:.2f}% "
                  f"decision={res['decision']}")
        elif isinstance(res, dict):
            print(f"{t} | SKIPPED - {res.get('reason', 'unknown reason')}")
        else:
            print(f"{t} | SKIPPED - run_once_for_ticker returned {type(res).__name__}")
    portfolio = trader.getPortfolio()
    print(f"\nCash: {portfolio['cash']:.2f}  |  Positions: {len(portfolio['positions'])}  |  PnL: {portfolio['PnL']}")
    return portfolio

def _seconds_until_next_open(now_et):
    open_t = dtime(9, 30)
    close_t = dtime(16, 0)

    #if it’s a weekday and before 9:30
    if now_et.weekday() < 5 and now_et.time() < open_t:
        next_open = now_et.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
        return (next_open - now_et).total_seconds()

    #otherwise find the next weekday and use 9:30 that day
    days_ahead = 1
    while True:
        candidate = now_et + timedelta(days=days_ahead)
        if candidate.weekday() < 5:
            next_open = candidate.replace(hour=open_t.hour, minute=open_t.minute, second=0, microsecond=0)
            return (next_open - now_et).total_seconds()
        days_ahead += 1

def run_market_hours_loop(poll_seconds=60):
    tz = ZoneInfo("America/Toronto")
    open_t = dtime(9, 0); close_t = dtime(16, 30)
    trader = PaperTrader.load_state(STATE_PATH, starting_cash=200.0, allow_multiple_lots_same_option=False)

    print("Starting market-hours loop. Ctrl+C to stop.")
    while True:
        now = datetime.now(tz)
        is_weekday = now.weekday() < 5
        in_session = is_weekday and (open_t <= now.time() < close_t)
        if in_session:
            try:
                for t in tickers:
                    t = t.strip().upper()
                    if not t: continue
                    res = run_once_for_ticker(t, trader)
                    if isinstance(res, dict) and res.get("ok"):
                        print(f"{t} | {res['expiry']} @ {res['listed_strike']:.2f}: "
                              f"spot={res['spot']:.2f} mid={res['market_mid']:.2f} "
                              f"model={res['model_price']:.2f} edge={res['edge']*100:.2f}% "
                              f"decision={res['decision']}")
                    elif isinstance(res, dict):
                        print(f"{t} | SKIPPED - {res.get('reason', 'unknown reason')}")
                #save snapshot each cycle
                trader.save_state(STATE_PATH)
            except Exception as e:
                print(f"[Loop] Error: {type(e).__name__}: {e}")
            time.sleep(poll_seconds)
        else:
            secs = _seconds_until_next_open(now)
            time.sleep(max(30, min(int(secs), 900)))


def main():
    trader = PaperTrader.load_state(STATE_PATH, starting_cash=200.0, allow_multiple_lots_same_option=False)
    results = []
    for t in tickers:
        t = t.strip().upper()
        if not t:
            continue
        res = run_once_for_ticker(t, trader)
        results.append(res)
        if isinstance(res, dict) and res.get("ok"):
            print(f"{t} | {res['expiry']} @ {res['listed_strike']:.2f}: "
                  f"spot={res['spot']:.2f} mid={res['market_mid']:.2f} "
                  f"model={res['model_price']:.2f} edge={res['edge']*100:.2f}% "
                  f"decision={res['decision']}")
        elif isinstance(res, dict):
            print(f"{t} | SKIPPED - {res.get('reason', 'unknown reason')}")
        else:
            print(f"{t} | SKIPPED - run_once_for_ticker returned {type(res).__name__}")
    #show portfolio
    portfolio = trader.getPortfolio()
    print(f"\nCash: {portfolio['cash']:.2f}  |  Positions: {len(portfolio['positions'])}  |  PnL: {portfolio['PnL']}")

if __name__ == "__main__":
    main()
