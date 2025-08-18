# config.py
from dotenv import load_dotenv
import os

load_dotenv()

tickers = os.getenv("TICKERS").split(',')
start_date = os.getenv("START_DATE")
end_date = os.getenv("END_DATE")

T = float(os.getenv("MATURITY_YEARS"))
strike_type = os.getenv("STRIKE_TYPE")
strike_pct = float(os.getenv("STRIKE_PERCENT"))

M = int(os.getenv("TIME_STEPS"))
I = int(os.getenv("SIMULATIONS"))
r = float(os.getenv("RISK_FREE_RATE"))

excel_output = os.getenv("EXCEL_OUTPUT")