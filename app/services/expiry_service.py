import random
import pandas as pd
from datetime import datetime, timedelta

# Define some random food names and types
food_names = ['Apple', 'Banana', 'Carrot', 'Tomato', 'Chicken Breast', 'Beef Steak', 'Milk', 'Cheese', 'Lettuce', 'Spinach']
food_types = ['Fruit', 'Fruit', 'Vegetable', 'Vegetable', 'Meat', 'Meat', 'Dairy', 'Dairy', 'Vegetable', 'Vegetable']

# Function to generate synthetic data
def generate_synthetic_data(num_samples=100):
    data = []

    for _ in range(num_samples):
        # Randomly choose food name and type
        food_name = random.choice(food_names)
        food_type = food_types[food_names.index(food_name)]
        
        # Random shelf life (in days) based on food type
        if food_type == 'Fruit':
            shelf_life = random.randint(5, 15)  # 5-15 days for fruit
        elif food_type == 'Vegetable':
            shelf_life = random.randint(3, 7)  # 3-7 days for vegetables
        elif food_type == 'Meat':
            shelf_life = random.randint(3, 10)  # 3-10 days for meat
        else:
            shelf_life = random.randint(7, 30)  # 7-30 days for dairy
        
        # Random environmental conditions (temperature and humidity)
        temperature = random.uniform(0, 40)  # Temperature in Celsius (0 to 40)
        humidity = random.uniform(30, 80)  # Humidity in percentage (30% to 80%)
        
        # Random purchase date (within the last 6 months)
        purchase_date = datetime.now() - timedelta(days=random.randint(1, 180))
        
        # Calculate expiry date by adding the shelf life to the purchase date
        expiry_date = purchase_date + timedelta(days=shelf_life)

        # Add to the data list
        data.append({
            'food_name': food_name,
            'food_type': food_type,
            'avg_shelf_life_days': shelf_life,
            'temperature': temperature,
            'humidity': humidity,
            'purchase_date': purchase_date.strftime('%Y-%m-%d'),
            'expiry_date': expiry_date.strftime('%Y-%m-%d')
        })
    
    # Create a DataFrame from the generated data
    df = pd.DataFrame(data)
    
    # Save the DataFrame to a CSV file
    df.to_csv('synthetic_food_data.csv', index=False)

    print(f"Dataset generated with {num_samples} samples. Saved as 'synthetic_food_data.csv'.")

# Run the function to generate the data
generate_synthetic_data()