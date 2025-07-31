

def trading_condition(latest_close, latest_50_day_MA, latest_100_day_MA):
    condition = (latest_50_day_MA > latest_100_day_MA) and (latest_close > latest_100_day_MA) and (latest_close < latest_50_day_MA)
    return condition

def closing_loosing_position_condition(current_spread_price, spread_max_loss, spread_max_profit):
    return ((current_spread_price - spread_max_loss) / (spread_max_profit - spread_max_loss)) >= 0.4

#def closing_profitable_position_condition():
