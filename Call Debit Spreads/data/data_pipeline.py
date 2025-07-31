import pandas as pd
import numpy as np
import os
from alpha_vantage.timeseries import TimeSeries
import requests

class LoadAssetsData():

    def __init__(self):
        self.ALPHA_VANTAGE_API_KEY = "6JKWIK2RFT5121M1"
        self.ts = TimeSeries(key=self.ALPHA_VANTAGE_API_KEY, output_format="pandas")
        self.tickers, self.files = self.get_assets_tickers()
        self.ten_years_ago = pd.Timestamp.today() - pd.DateOffset(years=10)
        self.risk_free_rates = self.get_risk_free_rates()


    def get_assets_tickers(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_folder_path = os.path.join(script_dir, "..", "data")
        if not os.path.exists(data_folder_path):
            raise FileNotFoundError(f"Data folder not found at {data_folder_path}")
        files = [
            f for f in os.listdir(data_folder_path)
            if f.endswith(".csv") and f != "observed_assets.csv"
        ]
        assets_tickers = [f.replace("_data.csv", "").upper() for f in files]
        return assets_tickers, files
    

    def get_risk_free_rates(self):
        url = f"https://www.alphavantage.co/query?function=TREASURY_YIELD&interval=daily&maturity=10year&apikey={self.ALPHA_VANTAGE_API_KEY}"
        response = requests.get(url)
        risk_free_rate_data = response.json()
        # At this point, the unit is percent and interval is daily
        risk_free_rate_data = pd.DataFrame(risk_free_rate_data["data"])
        risk_free_rate_data = risk_free_rate_data.rename(columns={
            "date": "Date",
            "value": "Value"
        })
        risk_free_rate_data = risk_free_rate_data.sort_values(by="Date")
        risk_free_rate_data = risk_free_rate_data.reset_index()
        risk_free_rate_data = risk_free_rate_data.drop(columns="index")
        # This changes string values of Value column to numbers only if possible and divide by 100 to get the
        # percentage values as a fraction of 1
        risk_free_rate_data["Value"] = pd.to_numeric(risk_free_rate_data["Value"], errors="coerce") / 100
        risk_free_rate_data["Date"] = pd.to_datetime(risk_free_rate_data["Date"], errors="coerce")
        # The U.S. Department of Treasury posts rates daily on business days, however, for weekends and holidays
        # the rates stay unchanged, therefore ->
        # This will replace each missing value (NaN) with the most recent previous non-missing value
        risk_free_rate_data["Value"] = risk_free_rate_data["Value"].ffill()
        ten_years_risk_free_rate_data = risk_free_rate_data[risk_free_rate_data["Date"] >= self.ten_years_ago]
        return ten_years_risk_free_rate_data
    

    def get_asset_data(self, asset):
        data, _ = self.ts.get_daily(
            symbol=asset,
            outputsize="full" # returns full history (compact = last 100 days)
        )
        data = data.reset_index()
        data = data.rename(columns={
            "date": "Date",
            "1. open": "Open",
            "2. high": "High",
            "3. low": "Low",
            "4. close": "Close",
            "5. volume": "Volume"
        })
        data = data.sort_values(by="Date")
        data = data.reset_index()
        data = data.drop(columns=["index"])
        data["50_day_MA"] = data["Close"].rolling(window=50).mean() # 50-days Moving average
        data["100_day_MA"] = data["Close"].rolling(window=100).mean() # 100-days Moving average
        data["Log_return"] = np.log(data["Close"] / data["Close"].shift(1)) # Daily log returns
        # Annualized daily volatility computed from rolling standard deviation of 20 days 
        data["Volatility"] = data["Log_return"].rolling(window=20).std() * np.sqrt(252) 
        data = data[data["Date"] >= self.ten_years_ago]
        return data
    

    def drop_and_load_data(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_folder_path = os.path.join(script_dir, "..", "data")
        for file in self.files:
            file_path = os.path.join(data_folder_path, file)
            if os.path.exists(file_path):
                os.remove(file_path)




    

    

load_assets_data = LoadAssetsData()
#print(load_assets_data.get_risk_free_rates())
print(load_assets_data.get_asset_data("SPY"))


    

