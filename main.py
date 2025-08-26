import dotenv as load_dotenv
import os
import yfinance as yf
import numpy as np
import pandas as pd
import lsmc_engine
import paper_trader
import time
import datetime from datetime

trader = paper_trader.PaperTrader()

#Find a way to make loopable through the day
def timeCheck():
    while True:
        now = datetime.now()
        if now.weekday() < 5 and now.hour >= 9 and now.hour < 16:
            #Run the main function
            main()
            #Check every minute
            time.sleep(60)
        else:
            time.sleep(60)

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

#Fetches from yahoo finance
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
    from config import tickers, start_date, end_date, T, strike_pct, M, I, r

    for ticker in tickers:
        config = loadconfig(ticker, start_date, end_date)
        spotPrice = config['spotPrice']
        prices = config['historicalPrices']
        
        #compute historical volatility
        log_returns = np.log(prices['Adj Close'] / prices['Adj Close'].shift(1)).dropna() #Gets rid of NaN used
        hist_sigma = log_returns.std() * np.sqrt(252) #num of trad days in a year for annualized amnt

        #add strike price
        strike = spotPrice*(1+float(strike_pct))
        
        #call for price paths and calculating the option
        paths = lsmc_engine.genPricePaths(hist_sigma, spotPrice, r, M, I)

        if ticker == 'AAPL':
            aaplPrice = lsmc_engine.calcOptnPrice(paths, strike, r, T)
        elif ticker == 'MSFT':
            msftPrice = lsmc_engine.calcOptnPrice(paths, strike, r, T)
        elif ticker == 'GOOGL':
            googlPrice = lsmc_engine.calcOptnPrice(paths, strike, r, T)
        else:
            tslaPrice = lsmc_engine.calcOptnPrice(paths, strike, r, T)
    return {
        'AAPl': aaplPrice, 
        'MSFT': msftPrice,
        'GOOGL': googlPrice,
        'TSLA': tslaPrice
    }

#check if should buy or sell the option
def tradeDecision(modelPrice, marketPrice, thresh, spotPrice, strk, today_index, optimal_exercise_index):
    edge = (modelPrice - marketPrice) / marketPrice

    #add something about exercising the option
    #Creating a sort of stop loss with the negative thresh
    if today_index >= optimal_exercise_index and spotPrice > strk:
        return "EXERCISE"
    elif edge > thresh:
        return "BUY"
    elif edge < -thresh:
        return "SELL"
    return "HOLD"

#calls paper_trader.py, calls the log and export function, update posns and adjust cash
def execTrade(ticker, modelPrice, marketPrice, strike, spotPrice, expiry, optimal_day_index, purchase_day_index, thresh):
    #Determine decision and get time stamp
    decision = tradeDecision(modelPrice, marketPrice, thresh, spotPrice, strike, purchase_day_index, optimal_day_index)
    timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    #add option ID
    optnID = f"{ticker}_{expiry}_{strike}"

    if decision == "EXERCISE":
        trader.exerciseOptn(optnID, spotPrice, timestamp)
    elif decision == "BUY":
        trader.buyOptn(optnID, strike, 1, marketPrice, "call", expiry, spotPrice, timestamp)
    elif decision == "SELL":
        trader.sellOptn(optnID, marketPrice, 1, timestamp, spotPrice)
    return

#makes script executable and testable
#Still figuring out what to put
def main():
    execTrade(ticker, modelPrice, spotPrice, strike, spotPrice, expirations[0], optimal_day_index, today_index, thresh)
