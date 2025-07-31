import numpy as np
import pandas as pd
from pandas import DataFrame
import math
import random
from scipy.stats import norm
from cds_portfolio_gbm_simulation import CDSPortfolioGBMSimulation
from arma_model import ModelARIMA


class CDSPortfolioMCSimulation():


    def __init__(self, sim_num):
        self.simulated_portfolio = CDSPortfolioGBMSimulation()
        self.model = ModelARIMA()
        self.portfolio = pd.DataFrame(columns=["asset", "expiration", "long_strike", "short_strike", "long_price", "short_price", "spread_cost", 
             "max_profit", "position_size", "contracts_bought"])
        self.account_size = 100000 # $100'000
        # This means we can open with max of 0.6%, i.e., we can open up to 3 positions and not loosing more than 1% if we close them all with 50% loss
        self.trade_size = self.account_size * 0.006
        self.number_of_simulations = sim_num
        self.YEARS_TO_EXP = 2
        self.PREMATURE_PERC_PROFIT = 0.35
        self.PREMATURE_PERC_LOSS = -0.5
        self.log = []
        self.all_portfolio_simulations = []


    def calculate_call_option_price(self, S, K, sigma, T, r):
        d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        d2 = d1 - sigma * np.sqrt(T)
        call_price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)      
        return call_price


    def calculate_historical_volatility(self, historical_volatility_data):
        sum_squared_returns = historical_volatility_data["log_returns_squared"].sum()
        n = historical_volatility_data["log_returns"].count()
        sigma_historical = np.sqrt((252 / n) * sum_squared_returns)
        return round(sigma_historical, 6)


    def get_proxy_implied_volatility(self, gbm_path, step, asset):
        # If 252 steps (trading days) is deducted from the current step, but there isn't enough steps/days in the GBM simulation,
        # the start of the interval is from non-existing index, so the series is empty
        series = self.simulated_portfolio.portfolio_gbm[asset][step - 252:step, gbm_path]
        if len(series) == 0:
            missing_steps = abs(step - 252)
            series = np.concatenate([
                self.simulated_portfolio.data[asset]["Close"][-missing_steps:].to_numpy(),
                self.simulated_portfolio.portfolio_gbm[asset][0:step, gbm_path]
            ])
        series = pd.Series(series)
        volatility_data = pd.DataFrame()
        volatility_data["log_returns"] = np.log(series / series.shift(1))
        volatility_data["log_returns_squared"] = volatility_data["log_returns"] ** 2
        step_sigma = self.calculate_historical_volatility(volatility_data)
        return step_sigma, series
    

    def get_spreads(self, series, step, step_sigma, asset, price) -> DataFrame:
        _, conf_int = self.model.model(series, [[1, 0, 1], [0, 0, 0, 0]])
        strike_list_lower_boundary = round(round(conf_int[0][0]))
        strike_list_upper_boundary = round(round(conf_int[0][1]))
        strike_prices_list = [strike for strike in range(strike_list_lower_boundary, strike_list_upper_boundary + 1)]
        strike_price_chain = {
            "strike": strike_prices_list,
            "price": np.full(len(strike_prices_list), None),
            "implied_volatility": np.full(len(strike_prices_list), step_sigma)
        }
        strike_price_chain = pd.DataFrame(strike_price_chain)
        strike_price_chain["price"] = strike_price_chain.apply(
            lambda row: pd.Series(
                self.calculate_call_option_price(
                    price,
                    row["strike"],
                    step_sigma,
                    self.YEARS_TO_EXP,
                    self.simulated_portfolio.data[asset]["Risk-free Rate"].iloc[-1]
                )
            ),
            axis=1
        )
        spreads = []
        for _, long_call in strike_price_chain.iterrows():
            for _, short_call in strike_price_chain.iterrows():
                spread_cost = long_call["price"] - short_call["price"]
                max_profit = short_call["strike"] - long_call["strike"] - spread_cost

                spreads.append({
                    "asset": asset,
                    "expiration": step + 365 * self.YEARS_TO_EXP, # Is there enough room for it?
                    "long_strike": long_call["strike"],
                    "short_strike": short_call["strike"],
                    "long_price": long_call["price"],
                    "short_price": short_call["price"],
                    "spread_cost": spread_cost,
                    "max_profit": max_profit
                })
        spreads = pd. DataFrame(spreads)
        spreads = spreads[
            (spreads["long_strike"] < spreads["short_strike"]) &
            (spreads["short_strike"] > price)
        ] # Only OTM spreads
        spreads = spreads[spreads["max_profit"] > spreads["spread_cost"]]
        return spreads
        

    def check_opened_positions(self, gbm_path, step, portfolio_pnl):
        for index, row in self.portfolio.iterrows():
            price = self.simulated_portfolio.portfolio_gbm[row["asset"]][step, gbm_path]
            step_sigma, _ = self.get_proxy_implied_volatility(gbm_path, step, row["asset"])
            # For consistency, datasets of underlying assets should be created on the same day, so the risk-free rates are same for the modelling
            r = self.simulated_portfolio.data[row["asset"]]["Risk-free Rate"].iloc[-1]
            time_to_expiration = (row["expiration"] - step) / 365
            long_call_price = self.calculate_call_option_price(price, row["long_strike"], step_sigma, time_to_expiration, r)
            short_call_price = self.calculate_call_option_price(price, row["short_strike"], step_sigma, time_to_expiration, r)
            spread_value = long_call_price - short_call_price
            spread_return = (spread_value - row["spread_cost"]) / row["spread_cost"]
            
            if (spread_return >= self.PREMATURE_PERC_PROFIT) and (row["expiration"] - step) <= 100:
                profit_in_usd = row["max_profit"] * self.PREMATURE_PERC_PROFIT * row["contracts_bought"]
                portfolio_pnl.append(portfolio_pnl[-1] + profit_in_usd)
                self.portfolio = self.portfolio.drop(index=index)

            if spread_return <= self.PREMATURE_PERC_LOSS and (row["expiration"] - step) <= 100:
                loss_in_usd = row["spread_cost"] * self.PREMATURE_PERC_LOSS * row["contracts_bought"]
                # Loss in USD is added as a sum because it was calculated from the negative share of premature percentage loss value
                portfolio_pnl.append(portfolio_pnl[-1] + loss_in_usd)
                self.portfolio = self.portfolio.drop(index=index)

            if row["expiration"] == step:
                if price > row["short_strike"]:
                    profit_in_usd = row["max_profit"] * row["contracts_bought"]
                    portfolio_pnl.append(portfolio_pnl[-1] + profit_in_usd)
                    self.portfolio = self.portfolio.drop(index=index)
                elif price < row["long_strike"]:
                    loss_in_usd = row["spread_cost"] * row["contracts_bought"]
                    # Minus sign is here because we don't multiply by negative share of return
                    portfolio_pnl.append(portfolio_pnl[-1] - loss_in_usd)
                    self.portfolio = self.portfolio.drop(index=index)
                else:
                    # Whether the profit or loss is added to the portfolio here, it is added up because spread's max profit is divided
                    # by spread return share that is either positive or negative for profit or loss, respectively
                    portfolio_pnl.append(portfolio_pnl[-1] + spread_return * row["max_profit"] * row["contracts_bought"])
                    self.portfolio = self.portfolio.drop(index=index)

        return portfolio_pnl


    def check_observed_underlying_assets(self, gbm_path, step):
        for asset in self.simulated_portfolio.files:
            price = self.simulated_portfolio.portfolio_gbm[asset][step, gbm_path]
            ma50_level = self.simulated_portfolio.portfolio_50ma[asset][step, gbm_path]
            ma100_level = self.simulated_portfolio.portfolio_100ma[asset][step, gbm_path]

            condition = (
                (ma50_level > ma100_level) and
                (price < ma50_level) and
                ((self.simulated_portfolio.sim_years_steps - step) > (365 * 2)) #and # There must be at least two years available in the future steps of the simulation
                # This needs to be uncomented once I start simulating
                #(asset not in portfolio["asset"].values) # Returning single True/False based on whether the asset is already in the portfolio or not
            )

            if condition == True:
                step_sigma, series = self.get_proxy_implied_volatility(gbm_path, step, asset)
                spreads = self.get_spreads(series, step, step_sigma, asset, price)
                # There were no spreads because early 50-days and 100-days Moving Averages had Nan values
                try:
                    random_spread = spreads.sample(n=1)
                    spread_cost = random_spread["spread_cost"].item()
                    number_of_contracts = round(self.trade_size / (spread_cost * 100))
                    position_cost = spread_cost * 100 * number_of_contracts
                    current_allocation = self.portfolio.loc[self.portfolio["asset"] == asset, "position_size"].sum()
                    max_allocation = self.account_size * 0.01

                    # Some spreads are too expensive they cannot be bought with the current account size
                    # or its portion dedicated to Call Debit Spreads + 
                    if (number_of_contracts > 0) and ((current_allocation + position_cost) < max_allocation):
                        random_spread["position_size"] = position_cost
                        random_spread["contracts_bought"] = number_of_contracts
                        self.portfolio = pd.concat([self.portfolio, random_spread], ignore_index=True)
                except Exception as e:
                    #self.log.append(e)
                    continue


    def run_monte_carlo_simulation(self):
        for _ in range(self.number_of_simulations):
            portfolio_pnl = [0]
            gbm_path = random.randint(0, self.simulated_portfolio.M - 1) # Number of GBM simulations passed from CDSPortfolioGBMSimulation class
            for step in range(self.simulated_portfolio.sim_years_steps): # Number of steps in GBM paths passed from CDSPortfolioGBMSimulation class
                # Checking the currently opened Call Debit Spread positions whether they are to be closed or exercised
                # Randomly selected GBM path for each simulation and time step on it are passed to the method
                portfolio_pnl = self.check_opened_positions(gbm_path, step, portfolio_pnl)
                # Checking the all observed underlying asset at each step whether the condition for opening Call Debit Spread position occured
                # Randomly selected GBM path for each simulation and time step on it are passed to the method
                self.check_observed_underlying_assets(gbm_path, step)

            portfolio_pnl = [x * 100 for x in portfolio_pnl]
            self.all_portfolio_simulations.append(portfolio_pnl)
            # Portfolio should be empty at the end of each simulation
            if len(self.portfolio) != 0:
                self.log.append(f"Error on {gbm_path}")

        return self.all_portfolio_simulations
    
