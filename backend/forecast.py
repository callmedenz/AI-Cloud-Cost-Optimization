# Forecasting helpers (Prophet-based), used for AI-assisted cost forecasting.
import pandas as pd
from prophet import Prophet

# Forecasting state
cost_history_df = None
model = None


# add new cost to dataframe
def add_cost_data(timestamp, cost):
    global cost_history_df
    
    if cost_history_df is None:
        cost_history_df = pd.DataFrame({
            'ds': [timestamp],
            'y': [cost]
        })
    else:
        new_row = pd.DataFrame({
            'ds': [timestamp],
            'y': [cost]
        })
        cost_history_df = pd.concat([cost_history_df, new_row], ignore_index=True)
    
    # I only need last 60 points so memory doesn't crash
    if len(cost_history_df) > 60:
        cost_history_df = cost_history_df.tail(60).reset_index(drop=True)


# function to predict future cost using ML
def predict_future_cost(days=30):
    global cost_history_df
    
    if cost_history_df is None or len(cost_history_df) < 10:
        return None, None
    
    try:
        model = Prophet()
        model.fit(cost_history_df)
        
        future = model.make_future_dataframe(periods=days)
        forecast = model.predict(future)
        
        future_predictions = forecast.tail(days)
        predicted_daily_costs = future_predictions['yhat'].values
        predicted_monthly_cost = sum(predicted_daily_costs)
        
        return float(predicted_monthly_cost), predicted_daily_costs.tolist()
    except Exception as e:
        print("Prophet Error:", e)
        # my fallback math here just in case ML fails
        recent_avg = cost_history_df['y'].tail(10).mean()
        # Keep fallback in the same unit as input cost samples.
        predicted_daily_costs = [float(recent_avg)] * days
        predicted_monthly_cost = sum(predicted_daily_costs)
        return float(predicted_monthly_cost), predicted_daily_costs


# get trend direction (increasing or decreasing)
def get_trend():
    global cost_history_df
    
    if cost_history_df is None or len(cost_history_df) < 5:
        return "unknown"
    
    recent_costs = cost_history_df['y'].tail(5).values
    if recent_costs[-1] > recent_costs[0]:
        return "increasing"
    elif recent_costs[-1] < recent_costs[0]:
        return "decreasing"
    return "stable"
