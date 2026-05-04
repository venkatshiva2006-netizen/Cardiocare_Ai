import pandas as pd
import joblib  # <-- NEW: The tool used to save the model to your hard drive
from sklearn.linear_model import SGDClassifier
from sklearn.preprocessing import StandardScaler

# 1. Load the historical medical dataset
print("Loading patient records...")
df = pd.read_csv("heart.csv")

# 2. Separate the patient vitals (X) from the final diagnosis (y)
X = df.drop("target", axis=1)
y = df["target"]

# 3. Scale the numbers
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# 4. Initialize the AI Model
model = SGDClassifier(loss="log_loss", random_state=42)

# 5. Train the base model 
model.partial_fit(X_scaled, y, classes=[0, 1])

# --- NEW CODE BELOW ---
print("Saving the AI Brain...")

# Save the model and the scaler to files
joblib.dump(model, "heart_disease_brain.joblib")
joblib.dump(scaler, "medical_scaler.joblib")

print("Success! The AI Brain and Scaler are permanently saved to your folder!")