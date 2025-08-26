import numpy as np
import yfinance as yf
import pandas as pd

#Use GBM here for multiple future paths
def genPricePaths(hist_sigma, spotPrice, rfr, matInYrs, steps, numOfPaths):
    dt = matInYrs / steps
    paths = np.zeros((numOfPaths, steps+1))
    paths[:, 0] = spotPrice
    
    Z = np.random.normal(0, 1, size=(numOfPaths, steps))
    
    drift = (rfr - 0.5*hist_sigma**2) * dt
    diffusion = hist_sigma * np.sqrt(dt) * Z
    log_returns = drift+diffusion
    
    for t in range(1, steps + 1):
        paths[:, t] = paths[:, t-1] * np.exp(log_returns[:, t-1])
    return paths

#Calc payoff for each sim done
def payoffCalc(St, Strike, option_type):
    if option_type == "Call":
        return np.maximum(St - Strike, 0)
    else:
        return np.maximum(Strike - St, 0)

#Using risk free rate, apply time discounting to future cashflows
def discountCashFlow(values, r, dt, fromTimeIndex, ToTimeIndex):
    return values * np.exp(-r * dt * (fromTimeIndex - ToTimeIndex))

#Checks value of option if not exercised at each step
def fitRegression(SItem, futureVals):
    A = np.vstack([np.ones_like(SItem), SItem, SItem**2]).T
    beta = np.linalg.lstsq(A, futureVals, rcond=None)[0]
    continuation = beta[0] + beta[1] * SItem + beta[2] * SItem**2
    return continuation, beta

#compare exercise val to cont val to decide when to exercise
def detExercise(immediateItem, continuationItem):
    return immediateItem > continuationItem

#determine fair value of option using discounted cashflows and optimal exercise policy
def calcOptnPrice(paths, K, r, T, optionType="Call"):
    I, M_plus_1 = paths.shape
    M = M_plus_1 - 1
    dt = T / M

    #default is to exercise at maturity
    cashflows = np.zeros(I)
    exerciseTimes = np.full(I, M, dtype=int)

    #payoff at maturity
    final_payoff = payoffCalc(paths[:, -1], K, optionType)
    cashflows[:] = final_payoff

    #backward induction
    for t in range(M - 1, 0, -1):
        S_t = paths[:, t]
        immediate = payoffCalc(S_t, K, optionType)

        # Consider only ITM paths
        itemIndex = np.where(immediate > 0)[0]
        if itemIndex.size == 0:
            continue

        #discount each path's current "plan" (cashflow at its exercise time) to time t
        fv_at_t = discountCashFlow(cashflows[itemIndex], r, dt, exerciseTimes[itemIndex], t)

        #regress continuation on ITM set
        cont_vals, _ = fitRegression(S_t[itemIndex], fv_at_t)

        #decide where to exercise now
        ex_now_mask = detExercise(immediate[itemIndex], cont_vals)
        ex_now_idx = itemIndex[ex_now_mask]

        #update those paths: lock in immediate payoff and stamp time
        cashflows[ex_now_idx] = immediate[ex_now_idx]
        exerciseTimes[ex_now_idx] = t

    #discount all realized cashflows to time 0 and average
    pv = discountCashFlow(cashflows, r, dt, from_time_idx=exerciseTimes, to_time_idx=0)
    return float(np.mean(pv))
