# LSMC-American-Style-Option-Trading-Algorithm
LSMC American Style Option Trading Algorithm:
This project is a mock trading algorithm to automate trading of American options. It uses the Monte Carlo method to simulate potential prices of the underlying assets (the stock in this case), then uses the least squares method to go from the predicted price at maturity and regress backwards to find the optimal time to cash in the option. In this algorithm I'm only going to allow call options because making a put option is an extra extension, and I may add it in the future but while I'm adding this repository its not in there. 

There is also an added stock trading simulator in there, because I didn't want to pay for a python linkable simulator (I don't live in the US so I cant use alpaca). And its a simple link to an excel sheet that logs trades that the algorithm would've done. 

Features:
- Uses information from yahoo finance (15 minute delay from real stock market)
- Uses Monte Carlo method to predict prices of the underlying asset
- Uses least squares method to find best time to exercise option
- Includes order simulator linked with excel file to track all trades algorithm would have made

Project Structure:

Installation:
If you'd like to run my code on your on machine you may, below are the steps to do so
