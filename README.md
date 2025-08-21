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
  feel free to download my code and run it on your own system :)

Example Output:
  My output are all logged in the excel file linked tot he project

Future extensions:
  Add put option support
  MUlti-asset option pricing (basket or spreads)

references:
  [1] QuantPy, Monte Carlo Simulation for Option Pricing with Python (Basic Ideas Explained). YouTube, Apr. 19,   2020. [Online]. Available: https://www.youtube.com/watch?v=pR32aii3shk
Accessed: Aug. 6, 2025.  

  [2] QuantPy, Valuing American Options Using Monte Carlo Simulation (intro to LSMC). YouTube, May 24, 2020. [Online]. Available: https://www.youtube.com/watch?v=rW9FdbirZzQ
Accessed: Aug. 7, 2025.

  [3] Technische Universität Berlin, Lecture Computational Finance / Numerical Methods 24 (American Monte-Carlo, Bermudan options). YouTube, Jul. 1, 2014. [Online]. Available: https://www.youtube.com/watch?v=Q4vfoDUkTsM
Accessed: Aug. 10, 2025.

  [4] Algorithmic Differentiation in Finance, Applying AAD to American Monte Carlo Option Pricing. YouTube, Dec. 17, 2019. [Online]. Available: https://www.youtube.com/watch?v=8mUlhkZ6FG0
Accessed: Aug. 20, 2025.
