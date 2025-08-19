import dotenv as load_dotenv
import os
import yfinance as yf
import numpy as np
import pandas as pd
import lsmc_engine

#Find a way to make loopable through the day


#reads ticker symbol from a .env and calls to fetch market data
def loadconfig(smbl, start_date, end_date):
    load_dotenv()
    
    smbl = os.getenv("TICKERS").split(",")
    start_date = os.getenv("START_DATE")
    end_date = os.getenv("END_DATE")
    
    data = yf.download(smbl, start = start_date, end = end_date)
    data = data[['Open', 'High', 'Low', 'Close', 'Adj Close', 'Volume']].dropna()
    
    marketData = fetchMarketData(smbl)
    
    return {
        'symbol':smbl, 'historicalPrices':data, 'spotPrice': marketData['spot_price'],
        'expirations':marketData['expirations']
    }

#Fetches 
def fetchMarketData(smbl):
    ticker = yf.Ticker(smbl)
    
    hist = ticker.history(period="1d")
    if not hist.empty:
        spot_price = hist['Close'].iloc[-1]
    
    #Fetch option expiration dates
    expirations = ticker.options
    
    return {
        'spot_price' : spot_price, 'expirations' : expirations
    }
    
#market data and params to run LSMC and price the option
#core of strat
def priceOptnLSMC():
    #import functions for LSMC calcs and 
    from config import tickers, start_date, end_date, T, strike_type, strike_pct, M, I, r
    
    config = loadconfig(tickers[0], start_date, end_date)
    spotPrice = config['spotPrice']
    prices = config['historicalPrices']
    
    #compute historical volatility
    log_returns = np.log(prices['Adj Close'] / prices['Adj Close'].shift(1)).dropna() #Gets rid of NaN used
    hist_sigma = log_returns.std() * np.sqrt(252) #num of trad days in a year for annualized amnt
    
    #find whether strike choice was at/in/on the money
    if strike_type == "ATM":
        strike = spotPrice
    elif strike_type == "OTM":
        strike = spotPrice * (1 + float(strike_pct))
    elif strike_type == "ITM":
        strike = spotPrice * (1 - float(strike_pct))
    else: 
        strike = spotPrice
    
    #call for price paths and calculating the option
    paths = lsmc_engine.genPricePaths(hist_sigma, spotPrice, r, M, I)
    price = lsmc_engine.calcOptnPrice(paths, strike, r, T)

    return price

#check if should buy or sell the option
def tradeDecision(modelPrice, marketPrice, thresh):
    edge = (modelPrice - marketPrice) / marketPrice
    
    if edge > thresh:
        return "Buy"
    elif edge < -thresh:
        return "Sell"
    return "Hold"

#calls paper_trader.py, calls the log and export function, update posns and adjust cash
def execTrade(signal, smbl, exp, strk, optn_typ, qty, mdl_prc, portf_state, slippage_bps, fees_p_contr) -> dict : #Creating dictionary t 
    ts = pd.Timestamp.now(tz="America/Toronto")
    side = signal.upper()

    if side == "HOLD":
        #DETERMINE RETURN VALUES
        return {"status": "Skipped", "Reason": "No Trade Signal", "side": side, "symbol": smbl, "expiry": exp, "Stirke": float(strk),
               "Option_type": optn_typ.lower(), "Quantity": int(qty), "Model Price": float(mdl_prc), "mark_price": np.NaN, "Fill price": np.Nan,
               "Slippage_bps": slippage_bps, }
    if qty <= 0:
        return{"Status": "REJECTED", "Reason": "qty must be > 0"}
    if "cash" not in portf_state or "positions" not in portf_state:
        return {"Status": "REJECTED", "Reason": "portfolio state missing 'cash'/'positions'"}

    key = (smbl, exp, float(strike), optn_typ.lower())
    pos_before = portf_state["Positions"].get(key, {"qty": 0, "avg_price": 0.0})
    qty_before = int(pos_before["qty"])
    avg_before = float(pos_before["avg_price"])
    cash_before = float(portf_state["cash"])

    row, mark = _get_option_mark(smbl, expy, strk, optn_typ)
    if row is None or not np.isfinite(mark) or mark<=0:
        return {"Status": "REJECTED", "Reason": "No valid market quote for contract"}

    edge = (float(model_price) - mark) / mark

    if side == "BUY":
        provis_fill = mark*((1.0 + slippage_bps) / 10000.0)
    elif side=="SELL":
        provis_fill = mark*((1.0 - slippage_bps) / 10000.0)
    else:
        return {"Status": "REJECTED", "Reason": f"Unknown side: {side}"}

    fill_price = _round_to_tick(provis_fill, tick=0.01)
    fees = float(fees_per_contract) * int(qty)
    gross = fill_price*int(qty)*100.0

    if side == "SELL" and qty > qty_before:
        return {"Status": "REJECTED", "Reason": "No shorting allowed; insufficient long qty"}
    if side == "BUY" and cash_before < (gross + fees):
        return {"Status": "REJECTED", "Reason": "Insufficient budge for buy+fees"}

    if side=="BUY":
        new_qty = qty_before+qty
        new_avg = (((avg_before+qty_before*100.0)+(fill_price*qty*100.0))/(new_qty*100.0))
        cash_after = cash_before - gross - fees
        portf_state["positions"][key] = {"qty": new_qty, "avg_price": float(new_avg)}
        portf_state["cash"] = float(cash_after)
    else:
        new_qty = 

#CONTINUE HERE

#Save all trade data, activity and results
def logAndExport():
    return 

#makes script executable and testable
def main():
    price = priceOptnLSMC()
    print(f"LSMC model price: {price:4f}")

    return

