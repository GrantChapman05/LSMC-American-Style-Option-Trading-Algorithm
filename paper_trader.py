from datetime import datetime
import pandas as pd
import os
from typing import Dict, Any
from config import excel_output

class PaperTrader:
    def __init__(self, starting_cash: float = 200.0):
        self.startCash = float(starting_cash)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trade_log = []
        self.realized_PNL = 0.0
        self.unrealized_PNL = 0.0
        self.currCash = self.startCash

    #simulate the buying of an option
    def buyOptn(self, optnID, strk_price, qty, prem_paid, optn_typ, exp_date, underlying_price, timestamp):
        total_cost = float(prem_paid) * int(qty)

        #update cash
        self.currCash -= total_cost

        #update/add position
        if optnID in self.positions:
            existing = self.positions[optnID]
            new_qty = existing['qty'] + qty
            new_avg_prem = ((existing['prem_paid'] * existing['qty']) + total_cost) / new_qty
            existing['qty'] = new_qty
            existing['prem_paid'] = new_avg_prem
            existing['underlying_price'] = underlying_price
        else:
            self.positions[optnID] = {
                'strk_price': float(strk_price),
                'prem_paid': float(prem_paid),
                'qty': int(qty),
                'exp_date': exp_date,
                'optn_typ': optn_typ,
                'underlying_price': float(underlying_price),
            }

        #log trade
        self.logTrade(
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

    #simulate selling an owned option
    def sellOptn(self, optnID, price, qty, timestamp, underlying_price=None):
        if optnID not in self.positions or self.positions[optnID]['qty'] < qty:
            return f"Error: Not enough contracts of {optnID} to sell."

        #unapshot details before mutation
        pos = self.positions[optnID].copy()
        avg_buy_price = pos['prem_paid']
        strike = pos['strk_price']
        exp_date = pos['exp_date']
        optn_typ = pos['optn_typ']

        total_proceeds = float(price) * int(qty)

        #update cash and realized PnL
        self.currCash += total_proceeds
        realized_pnl = (float(price) - avg_buy_price) * int(qty)
        self.realized_PNL += realized_pnl

        #update/clear position
        self.positions[optnID]['qty'] -= int(qty)
        if self.positions[optnID]['qty'] == 0:
            del self.positions[optnID]

        #log trade
        self.logTrade(
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

    def exerciseOptn(self, optnID, underlying_price, timestamp):
        if optnID not in self.positions:
            return f"Error: Option {optnID} not found in portfolio."

        position = self.positions[optnID]
        qty = position['qty']
        strike = position['strk_price']
        optn_type = position['optn_typ']

        if optn_type.lower() != 'call':
            return f"Error: Unknown option type '{optn_type}' for {optnID}."

        payoff_per_contract = max(0.0, float(underlying_price) - float(strike))
        total_payoff = payoff_per_contract * int(qty)

        self.currCash += total_payoff
        self.realized_PNL += total_payoff - (position['prem_paid'] * int(qty))

        #remove position and log
        del self.positions[optnID]
        self.logTrade(
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

        return {
            'realized': self.realized_PNL,
            'unrealized': unrealized_pnl,
            'total': total_pnl
        }

    def logTrade(self, trad_typ, optnID, strk_price, prem_paid, qty, exp_date, optn_typ, underlying_price, total_cost, timestamp):
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

        if os.path.exists(file_name):
            #append or create/replace today's sheet
            with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='overlay') as writer:
                try:
                    existing_df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')
                    updated_df = pd.concat([existing_df, pd.DataFrame([trade_entry])], ignore_index=True)
                except Exception:
                    updated_df = pd.DataFrame([trade_entry])
                updated_df.to_excel(writer, sheet_name=sheet_name, index=False)
        else:
            with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
                pd.DataFrame([trade_entry]).to_excel(writer, sheet_name=sheet_name, index=False)

    def getPortfolio(self):
        return {
            'cash': float(self.currCash),
            'positions': self.positions,
            'PnL': self.calcPNL(current_prices={})
        }

    def reset(self, current_prices, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for optnID in list(self.positions.keys()):
            if optnID in current_prices:
                market_price = float(current_prices[optnID])
                qty = int(self.positions[optnID]['qty'])
                self.sellOptn(optnID, market_price, qty, timestamp, underlying_price=self.positions[optnID]['underlying_price'])

        self.unrealized_PNL = 0.0

