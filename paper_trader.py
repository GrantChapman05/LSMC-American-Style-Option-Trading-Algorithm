from datetime import datetime
import pandas as pd
import os, json
from typing import Dict, Any
from pathlib import Path
from config import excel_output

#create paper trading class to find state of positions
class PaperTrader:
    #initialize
    def __init__(self, starting_cash: float = 200.0, allow_multiple_lots_same_option: bool = False):
        self.startCash = float(starting_cash)
        self.allow_multiple = bool(allow_multiple_lots_same_option)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_log = []
        self.realized_PNL = 0.0
        self.unrealized_PNL = 0.0
        self.currCash = self.startCash

    #current state to dict
    def to_state(self) -> Dict[str, Any]:
        return {
            "startCash": self.startCash,
            "currCash": self.currCash,
            "positions": self.positions,
            "realized_PNL": self.realized_PNL,
            "unrealized_PNL": self.unrealized_PNL,
            "allow_multiple": self.allow_multiple,
        }

    def save_state(self, path: str = "portfolio_state.json") -> None:
        Path(path).write_text(json.dumps(self.to_state(), indent=2))

    
    @classmethod #called on loading the state (duh)
    def load_state(cls, path: str = "portfolio_state.json", starting_cash: float = 200.0,
                   allow_multiple_lots_same_option: bool = False):
        p = Path(path)
        if p.exists():
            data = json.loads(p.read_text() or "{}")
            trader = cls(
                starting_cash=float(data.get("startCash", starting_cash)),
                allow_multiple_lots_same_option=bool(data.get("allow_multiple", allow_multiple_lots_same_option)),
            )
            trader.currCash = float(data.get("currCash", trader.startCash))
            trader.positions = data.get("positions", {})
            trader.realized_PNL = float(data.get("realized_PNL", 0.0))
            trader.unrealized_PNL = float(data.get("unrealized_PNL", 0.0))
            return trader
        return cls(starting_cash=starting_cash, allow_multiple_lots_same_option=allow_multiple_lots_same_option)

    #if purchasing an option has been called
    def buyOptn(self, optnID, strk_price, qty, prem_paid, optn_typ, exp_date, underlying_price, timestamp) -> bool:
        total_cost = float(prem_paid) * int(qty)

        #skip if not enough cash
        if total_cost > self.currCash + 1e-9:
            #not executed -> do NOT log
            return False

        #skip duplicate lots unless allowed
        if (not self.allow_multiple) and (optnID in self.positions) and self.positions[optnID]['qty'] > 0:
            return False

        #execute
        self.currCash -= total_cost

        if optnID in self.positions:
            existing = self.positions[optnID]
            new_qty = existing['qty'] + int(qty)
            new_avg_prem = ((existing['prem_paid'] * existing['qty']) + total_cost) / new_qty
            existing['qty'] = new_qty
            existing['prem_paid'] = new_avg_prem
            existing['underlying_price'] = float(underlying_price)
        else:
            self.positions[optnID] = {
                'strk_price': float(strk_price),
                'prem_paid': float(prem_paid),
                'qty': int(qty),
                'exp_date': exp_date,
                'optn_typ': optn_typ,
                'underlying_price': float(underlying_price),
            }

        #only successful executions should be logged
        self._logTrade(
            trad_typ="BUY",
            optnID=optnID,
            strk_price=strk_price,
            prem_paid=prem_paid,
            qty=qty,
            exp_date=exp_date,
            optn_typ=optn_typ,
            underlying_price=underlying_price,
            total_cost=total_cost,
            timestamp=timestamp,
        )
        return True

    #if sell is determined
    def sellOptn(self, optnID, price, qty, timestamp, underlying_price=None) -> bool:
        if optnID not in self.positions or self.positions[optnID]['qty'] < int(qty):
            return False

        pos = self.positions[optnID].copy()
        avg_buy_price = float(pos['prem_paid'])
        strike = float(pos['strk_price'])
        exp_date = pos['exp_date']
        optn_typ = pos['optn_typ']

        total_proceeds = float(price) * int(qty)
        self.currCash += total_proceeds
        realized_pnl = (float(price) - avg_buy_price) * int(qty)
        self.realized_PNL += realized_pnl

        self.positions[optnID]['qty'] -= int(qty)
        if self.positions[optnID]['qty'] == 0:
            del self.positions[optnID]

        #log the trade
        self._logTrade(
            trad_typ="SELL",
            optnID=optnID,
            strk_price=strike,
            prem_paid=price,
            qty=qty,
            exp_date=exp_date,
            optn_typ=optn_typ,
            underlying_price=underlying_price,
            total_cost=-total_proceeds,
            timestamp=timestamp,
        )
        return True

    #if exercise is called
    def exerciseOptn(self, optnID, underlying_price, timestamp) -> bool:
        if optnID not in self.positions:
            return False

        position = self.positions[optnID]
        qty = int(position['qty'])
        strike = float(position['strk_price'])
        optn_type = position['optn_typ']

        if optn_type.lower() != 'call':
            return False

        payoff_per_contract = max(0.0, float(underlying_price) - strike)
        total_payoff = payoff_per_contract * qty

        self.currCash += total_payoff
        self.realized_PNL += total_payoff - (position['prem_paid'] * qty)

        del self.positions[optnID]

        self._logTrade(
            trad_typ='EXERCISE',
            optnID=optnID,
            strk_price=strike,
            prem_paid=position['prem_paid'],
            qty=qty,
            exp_date=position['exp_date'],
            optn_typ=optn_type,
            underlying_price=underlying_price,
            total_cost=total_payoff,
            timestamp=timestamp
        )
        return True

    def calcPNL(self, current_prices):
        unrealized_pnl = 0.0
        for optnID, position in self.positions.items():
            if optnID in current_prices:
                mrkt_price = float(current_prices[optnID])
                avg_buy_price = float(position['prem_paid'])
                qty = int(position['qty'])
                unrealized_pnl += (mrkt_price - avg_buy_price) * qty

        total_pnl = self.realized_PNL + unrealized_pnl
        self.unrealized_PNL = unrealized_pnl
        return {'realized': self.realized_PNL, 'unrealized': unrealized_pnl, 'total': total_pnl}

    #log in excel, patched to also open when the excel file is opened
    from pathlib import Path

    def _logTrade(self, trad_typ, optnID, strk_price, prem_paid, qty, exp_date, optn_typ, underlying_price, total_cost, timestamp):
        today_str = datetime.today().strftime('%Y-%m-%d')
        trade_entry = {
            'timestamp': timestamp,
            'trad_typ': trad_typ,
            'optnID': optnID,
            'optn_typ': optn_typ,
            'strk_price': float(strk_price),
            'prem_paid': float(prem_paid),
            'qty': int(qty),
            'exp_date': exp_date,
            'underlying_price': float(underlying_price) if underlying_price is not None else None,
            'total_cost': float(total_cost),
            'remaining_cash': float(self.currCash)
        }

        self.trade_log.append(trade_entry)

        sheet_name = f"Registered Trades ({today_str})"
        file_name = excel_output if excel_output else "TransactionRecords.xlsx"

        try:
            if os.path.exists(file_name):
                with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
                    try:
                        existing_df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')
                        updated_df = pd.concat([existing_df, pd.DataFrame([trade_entry])], ignore_index=True)
                    except Exception:
                        updated_df = pd.DataFrame([trade_entry])
                    updated_df.to_excel(writer, sheet_name=sheet_name, index=False)
            else:
                with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
                    pd.DataFrame([trade_entry]).to_excel(writer, sheet_name=sheet_name, index=False)

        except PermissionError:
            #workbook is open/locked, write to a day CSV buffer instead
            buf_dir = Path("reports") / "fallback"
            buf_dir.mkdir(parents=True, exist_ok=True)
            csv_path = buf_dir / f"{today_str}_buffer.csv"
            df = pd.DataFrame([trade_entry])
            #append (write header only if file doesn't exist)
            df.to_csv(csv_path, mode="a", index=False, header=not csv_path.exists())
            print(f"[WARN] {file_name} locked. Logged to {csv_path} instead.")

    def getPortfolio(self):
        return {'cash': float(self.currCash), 'positions': self.positions, 'PnL': self.calcPNL(current_prices={})}

    #reset position
    def reset(self, current_prices, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        for optnID in list(self.positions.keys()):
            if optnID in current_prices:
                market_price = float(current_prices[optnID])
                qty = int(self.positions[optnID]['qty'])
                self.sellOptn(optnID, market_price, qty, timestamp, underlying_price=self.positions[optnID]['underlying_price'])
        self.unrealized_PNL = 0.0
