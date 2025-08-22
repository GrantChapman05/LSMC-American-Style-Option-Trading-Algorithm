from datetime import datetime
import pandas as pd
import os
#Constructor
#initialize paper trader w/ cash
def __init__(self):
    self.startCash = 200 #I want this algorithm to start with 200$

    #Creating null logs of trades and current positions
    self.positions = {}
    self.trade_log = []

    #starting profit and loss is nothing
    self.realized_PNL = 0
    self.unrealized_PNL = 0

    self.currCash = self.startCash + self.realized_PNL

#Simulate the buying of an option
def buyOptn(self, optnID, strk_price, qty, prem_paid, optn_typ, exp_date, underlying_price, timestamp):
    total_cost = prem_paid * qty

    #current cash amount to be less the price paid
    self.currCash = self.currCash - total_cost

    #Check for existing option
    if optnID in self.positions:
        existing = self.positions[optnID]
        #add to qty
        new_qty = existing['qty'] + qty
        #calc avg premium paid
        new_avg_prem = ((existing['prem_paid'] * existing['qty']) + total_cost) / new_qty
        self.positions[optnID]['qty'] = new_qty
        self.positions[optnID]['prem_paid'] = new_avg_prem
    else:
        #make new and add givens
        self.positions[optnID] = {
            'strk_price' = strk_price,
            'prem_paid' = prem_paid,
            'qty' = qty,
            'exp_date' = exp_date,
            'optn_typ' = optn_typ,
            'underlying_price' = underlying_price
        }

    #log trade
    self.logTrade(
        trad_typ = "BUY",
        total_cost = total_cost,
        strk_price = strk_price,
        prem_paid = prem_paid,
        qty = qty,
        exp_date = exp_date,
        optn_typ = optn_typ,
        underlying_price = underlying_price,
        timestamp = timestamp
    )

#Simulate a preowned option being sold, must be owned
def sellOptn(self, optnID, price, qty, timestamp, underlying_price=None):
    #Check if the option is owned
    if optnID not in self.positions or self.positions[optnID]['qty'] < qty:
        return f"Error: Not enough contracts of {optnID} to sell."

    #Get the original purchase price
    avg_buy_price = self.positions[optnID]['prem_paid']

    #Calculate proceeds and PnL
    total_proceeds = price * qty

    #Update cash and realized PnL
    self.currCash += total_proceeds
    
    realized_pnl = (price - avg_buy_price) * qty
    self.realized_PNL += realized_pnl


    #Update or remove posn
    self.positions[optnID]['qty'] -= qty
    if self.positions[optnID]['qty'] == 0:
        del self.positions[optnID]

    #log the trade
    self.logTrade(
        trad_typ='SELL',
        optnID=optnID,
        strk_price=self.positions.get(optnID, {}).get('strk_price', 'N/A'),
        prem_paid=price,
        qty=qty,
        exp_date=self.positions.get(optnID, {}).get('exp_date', 'N/A'),
        optn_typ=self.positions.get(optnID, {}).get('optn_typ', 'N/A'),
        underlying_price=underlying_price,
        total_cost=-total_proceeds,  #negative because it's a sale
        timestamp=timestamp
    )
    
def exerciseOptn(self, optnID, underlying_price, timestamp):
    #Check if the option is owned
    if optnID not in self.positions:
        return f"Error: Option {optnID} not found in portfolio."

    position = self.positions[optnID]
    qty = position['qty']
    strike = position['strk_price']
    optn_type = position['optn_typ']

    #Calc curr payoff
    if optn_type.lower() == 'call':
        payoff_per_contract = max(0, underlying_price - strike)
    else:
        return f"Error: Unknown option type '{optn_type}' for {optnID}."

    total_payoff = payoff_per_contract * qty

    #Update cash posn and realized PnL
    self.currCash += total_payoff
    self.realized_PNL += total_payoff - (position['prem_paid'] * qty)

    #Remove the posn
    del self.positions[optnID]

    #Log the exercise
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

#calc realized and unrealized profits/losses from trades
def calcPNL(self, current_prices):
    unrealized_pnl = 0

    for optnID, position in self.positions.items():
        if optnID in current_prices:
            mrkt_price = current_prices[optnID]
            avg_buy_price = position['prem_paid']
            qty = position['qty']

            #Unrealized PnL = (market - buy) * qty
            unrealized_pnl += (mrkt_price - avg_buy_price) * qty

    total_pnl = self.realized_PNL + unrealized_pnl
    self.unrealized_PNL = unrealized_pnl

    return {
        'realized': self.realized_PNL,
        'unrealized': unrealized_pnl,
        'total': total_pnl
    }


#export to excel any tade decision
def logTrade(self, trad_typ, optnID, strk_price, prem_paid, qty, exp_date, optn_typ, underlying_price, total_cost, timestamp):
    from datetime import datetime

    #time and date for excel sheet
    today_str = datetime.today().strftime('%Y-%m-%d')
    trade_entry = {
        'timestamp': timestamp,
        'trad_typ': trad_typ,
        'optmID': optnID,
        'optn_typ': optn_typ,
        'strk_price': strk_price,
        'prem_paid': prem_paid,
        'qty': qty,
        'exp_date': exp_date,
        'underlying_price': underlying_price,
        'total_cost': total_cost,
        'remaining_cash': self.currCash
    }

    #add to trade log array
    self.trade_log.append(trade_entry)

    sheet_name = f"Registered Trades ({today_str})"
    file_name = "Transactionrecords.xlsx"

    #check if the path exists to the excel sheet w todays date
    if os.path.exists(file_name):
        excel_file = pd.ExcelFile(file_name, engine='openpyxl')
        if sheet_name in excel_file.sheetnames:
            existing_df = pd.read_excel(file_name, sheet_name=sheet_name, engine='openpyxl')
            updated_df = pd.concat([existing_df, pd.DataFrame([trade_entry])], ignore_index=True)
        else: 
            updated_df = pd.DataFrame([trade_entry])
        with pd.ExcelWriter(file_name, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            updated_df.to_excel(writer, sheet_name=sheet_name, index=False)

    else:
        with pd.ExcelWriter(file_name, engine='openpyxl') as writer:
            pd.DataFrame([trade_entry]).to_excel(writer, sheet_name=sheet_name, index=False)

#Just to get portfolio information, might delete later
def getPortfolio(self):
    return {
        'cash': self.currCash,
        'positions': self.positions,
        'PnL': self.calcPNL(current_prices={})  #I'll need to pass real prices
    }

def reset(self, current_prices, timestamp=None):
    """
    sells all held options at current market prices and resets the portfolio.
    The idea behind this function is to let the algo buy as it wants for a week,
    wait until the unsold/unexercised options expire, then get rid of everything and repeat, keeping any money it made 
    """
    if timestamp is None:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    for optnID in list(self.positions.keys()):
        if optnID in current_prices:
            market_price = current_prices[optnID]
            qty = self.positions[optnID]['qty']
            self.sellOptn(optnID, market_price, qty, timestamp, underlying_price=self.positions[optnID]['underlying_price'])

    #Clear unrealized PnL since all positions are sold
    self.unrealized_PNL = 0
