from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


PROJECT_DIR = Path(__file__).resolve().parents[1]

DATA_FILE = (
    PROJECT_DIR
    / "data/activity_logs/rescuecloud_audit_logs.csv"
)

MODEL_DIR = PROJECT_DIR / "ml/models"
MODEL_FILE = MODEL_DIR / "isolation_forest.joblib"


NUMERIC_FEATURES = [
    "failed_logins",
    "requests_per_minute",
    "records_accessed",
    "records_modified",
    "records_deleted",
    "export_size_mb",
    "session_duration_min",
    "off_hours_access",
    "new_ip_address",
    "privilege_change",
]

CATEGORICAL_FEATURES = [
    "role",
    "action",
    "status",
]

FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


data = pd.read_csv(DATA_FILE)

X = data[FEATURES]
y = data["label"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y,
)

preprocessor = ColumnTransformer(
    transformers=[
        (
            "numeric",
            StandardScaler(),
            NUMERIC_FEATURES,
        ),
        (
            "categorical",
            OneHotEncoder(
                handle_unknown="ignore",
                sparse_output=False,
            ),
            CATEGORICAL_FEATURES,
        ),
    ]
)

model = IsolationForest(
    n_estimators=300,
    contamination=0.05,
    random_state=42,
    n_jobs=-1,
)

pipeline = Pipeline(
    steps=[
        ("preprocessor", preprocessor),
        ("model", model),
    ]
)

print("Training Isolation Forest...")
pipeline.fit(X_train)

raw_predictions = pipeline.predict(X_test)

# Isolation Forest returns:
#  1 = normal
# -1 = anomaly
predictions = [
    1 if prediction == -1 else 0
    for prediction in raw_predictions
]

print("\nConfusion Matrix:")
print(confusion_matrix(y_test, predictions))

print("\nClassification Report:")
print(
    classification_report(
        y_test,
        predictions,
        target_names=["Normal", "Anomaly"],
        digits=4,
    )
)

MODEL_DIR.mkdir(parents=True, exist_ok=True)
joblib.dump(pipeline, MODEL_FILE)

print(f"\nModel saved to: {MODEL_FILE}")
print(f"Training records: {len(X_train)}")
print(f"Testing records: {len(X_test)}")
