# train_model.py

import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib

# Sample data (you can replace this with actual data)
data = pd.DataFrame({
    'food_type': [1, 2, 3, 1],  # 1: Dairy, 2: Meat, 3: Fruit
    'temperature': [4, 6, 22, 5],
    'humidity': [85, 80, 60, 80],
    'shelf_life': [7, 5, 4, 10]
})

# Features (independent variables)
X = data[['food_type', 'temperature', 'humidity']]

# Target (dependent variable)
y = data['shelf_life']

# Initialize model
model = RandomForestRegressor(n_estimators=100, random_state=42)

# Train the model
model.fit(X, y)

# Save the model to a file
joblib.dump(model, 'expiry_predictor.pkl')

print("Model trained and saved successfully!")