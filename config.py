from dotenv import load_dotenv
from pathlib import Path
import os

#load stor_configs.env from the same folder as this file (robust to CWD)
env_path = Path(__file__).with_name("stor_configs.env")
load_dotenv(dotenv_path=env_path, override=False)

#SAFE DEFAULTS so we never crash if a key is missing
tickers_raw = os.getenv("TICKERS") or "AAPL,MSFT,GOOGL,TSLA"
tickers = [t.strip() for t in tickers_raw.split(",") if t.strip()]

start_date = os.getenv("START_DATE", "2024-01-01")
end_date   = os.getenv("END_DATE", "2025-01-01")

T = float(os.getenv("MATURITY_YEARS", "1"))
strike_type = (os.getenv("STRIKE_TYPE", "ATM") or "ATM").upper()
strike_pct = float(os.getenv("STRIKE_PERCENT", "0.05"))
thresh = float(os.getenv("THRESHOLD", "0.05"))

M = int(os.getenv("TIME_STEPS", "50"))
I = int(os.getenv("SIMULATIONS", "10000"))
r = float(os.getenv("RISK_FREE_RATE", "0.05"))

excel_output = os.getenv("EXCEL_OUTPUT", "TransactionRecords.xlsx")
