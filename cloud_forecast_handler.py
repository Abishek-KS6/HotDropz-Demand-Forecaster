import json
import os
import pandas as pd
from prophet import Prophet
from flask import Flask, request, jsonify

# Note: This mock data is typically uploaded separately to the cloud environment.
# For simplicity, we define it here, but in production, it would be fetched from a database or storage bucket.
MOCK_CSV_DATA = """
ds,y,product_id
2022-01-01,150,W01
2022-02-01,120,W01
2022-03-01,100,W01
2022-04-01,140,W01
2022-05-01,180,W01
2022-06-01,250,W01
2022-07-01,350,W01
2022-08-01,400,W01
2022-09-01,380,W01
2022-10-01,550,W01
2022-11-01,600,W01
2022-12-01,450,W01
2023-01-01,180,W01
2023-02-01,150,W01
2023-03-01,130,W01
2023-04-01,160,W01
2023-05-01,200,W01
2023-06-01,280,W01
2023-07-01,380,W01
2023-08-01,420,W01
2023-09-01,400,W01
2023-10-01,580,W01
2023-11-01,630,W01
2023-12-01,480,W01
2024-01-01,200,W01
2024-02-01,170,W01
2024-03-01,150,W01
2024-04-01,180,W01
2024-05-01,220,W01
2024-06-01,300,W01
2024-07-01,400,W01
2024-08-01,450,W01
2024-09-01,420,W01
2024-10-01,610,W01
2024-11-01,660,W01
2024-12-01,500,W01
2022-01-01,300,F01
2022-02-01,320,F01
2022-03-01,350,F01
2022-04-01,400,F01
2022-05-01,420,F01
2022-06-01,450,F01
2022-07-01,500,F01
2022-08-01,550,F01
2022-09-01,600,F01
2022-10-01,850,F01
2022-11-01,750,F01
2022-12-01,400,F01
2023-01-01,320,F01
2023-02-01,340,F01
2023-03-01,370,F01
2023-04-01,420,F01
2023-05-01,440,F01
2023-06-01,470,F01
2023-07-01,520,F01
2023-08-01,580,F01
2023-09-01,630,F01
2023-10-01,880,F01
2023-11-01,780,F01
2023-12-01,430,F01
2024-01-01,340,F01
2024-02-01,360,F01
2024-03-01,390,F01
2024-04-01,440,F01
2024-05-01,460,F01
2024-06-01,490,F01
2024-07-01,540,F01
2024-08-01,600,F01
2024-09-01,650,F01
2024-10-01,900,F01
2024-11-01,800,F01
2024-12-01,450,F01
"""

def run_prophet_forecast(df):
    """Trains Prophet model and generates a 12-month sales forecast."""
    
    # Check if DataFrame is valid
    if df.empty or 'ds' not in df.columns or 'y' not in df.columns:
        return []

    # Initialize Prophet model
    # Adjust seasonality based on general retail cycles (yearly, monthly)
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode='multiplicative'
    )
    
    # Add Indian holidays as custom regressors for production
    # model.add_country_holidays(country_name='IN')

    # Train the model
    model.fit(df)
    
    # Create future DataFrame for 12 months (starting from the month after the last data point)
    future = model.make_future_dataframe(periods=12, freq='MS')
    
    # Generate the forecast
    forecast = model.predict(future)
    
    # Extract only the dates and the forecasted sales (yhat)
    # Convert dates to string for JSON serialization
    forecast_data = forecast[['ds', 'yhat']].tail(12).rename(columns={'yhat': 'demand_score'}).copy()
    
    # Normalize demand score to a 0-100 scale for the frontend (simulating sales volume as a score)
    min_val = forecast_data['demand_score'].min()
    max_val = forecast_data['demand_score'].max()
    
    if max_val > min_val:
        forecast_data['demand_score'] = (
            (forecast_data['demand_score'] - min_val) / (max_val - min_val) * 100
        ).round(2)
    else:
        forecast_data['demand_score'] = 50.0  # Default if no variance

    # Prepare final output structure
    output = []
    for index, row in forecast_data.iterrows():
        output.append({
            'date': row['ds'].strftime('%Y-%m-%d'),
            'demand_score': row['demand_score'],
        })
        
    return output

def run_multi_product_forecast():
    """Reads mock data, runs separate forecasts for each product, and aggregates the result."""
    
    # Convert the mock CSV string into a DataFrame
    from io import StringIO
    df_raw = pd.read_csv(StringIO(MOCK_CSV_DATA))
    
    all_forecasts = {}
    
    # Get unique product IDs
    product_ids = df_raw['product_id'].unique()
    
    for product_id in product_ids:
        # Filter data for the current product
        df_product = df_raw[df_raw['product_id'] == product_id].copy()
        
        # Prepare DataFrame for Prophet (must have 'ds' and 'y' columns)
        df_product = df_product.rename(columns={'y': 'y', 'ds': 'ds'})
        df_product['ds'] = pd.to_datetime(df_product['ds'])
        
        # Run forecast
        forecast_result = run_prophet_forecast(df_product)
        
        # Store the result by product ID
        all_forecasts[product_id] = forecast_result
        
    return all_forecasts

def forecast_handler(request):
    """
    Main entry point for the Google Cloud Function/Serverless API.
    Handles HTTP requests to run the demand forecast.
    """
    # Set CORS headers for preflight requests
    if request.method == 'OPTIONS':
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Max-Age': '3600'
        }
        return ('', 204, headers)

    # Set CORS headers for main requests
    headers = {
        'Access-Control-Allow-Origin': '*'
    }

    try:
        # Run the full multi-product forecast
        forecast_data = run_multi_product_forecast()
        
        # Return the structured JSON response
        return (json.dumps(forecast_data), 200, headers)
        
    except Exception as e:
        error_message = f"Error during forecast calculation: {str(e)}"
        print(error_message)
        return (jsonify({'error': error_message}), 500, headers)

# This block is used for local testing (optional)
if __name__ == '__main__':
    # To run locally:
    # 1. Ensure you have the required Python libraries installed (pip install -r requirements.txt)
    # 2. Run this script directly: python cloud_forecast_handler.py
    # 3. Access via Flask (simulated)
    app = Flask(__name__)
    
    @app.route('/', methods=['GET', 'POST'])
    def handle_request():
        # Simulate a request object
        class MockRequest:
            def __init__(self, method):
                self.method = method
            
        return forecast_handler(MockRequest(request.method))

    app.run(host='0.0.0.0', port=8080)