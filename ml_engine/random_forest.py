"""
Random Forest Classifier for Member 2.
Supervised classification of network state (healthy, congested, failed), model serialization,
and evaluation metrics report generation.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.4 and Plan_docs/member-2-ml-engine.md.
"""
import os
import pickle
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from shared.config import MODELS_DIR
from shared.schemas import State
from ml_engine.dataset_gen import FEATURE_COLUMNS


def train_rf(
    df: pd.DataFrame,
    save_model: bool = True,
    model_filename: str = "rf.pkl",
    random_state: int = 42,
) -> Tuple[RandomForestClassifier, Dict]:
    """
    Train a Random Forest classifier to predict network state ('healthy', 'congested', 'failed').
    Returns (model, classification_report_dict).
    """
    X = df[FEATURE_COLUMNS]
    y = df["state"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=random_state, stratify=y
    )

    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=12,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    y_pred = model.predict(X_test)
    report = classification_report(y_test, y_pred, output_dict=True)
    report["overall_accuracy"] = accuracy_score(y_test, y_pred)
    report["macro_f1"] = f1_score(y_test, y_pred, average="macro")

    if save_model:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        model_path = MODELS_DIR / model_filename
        with open(model_path, "wb") as f:
            pickle.dump(model, f)

    return model, report


class NetworkStateClassifier:
    """Wrapper around trained Random Forest model for live inference."""

    def __init__(self, model: Optional[RandomForestClassifier] = None):
        self.model = model

    def load(self, model_path: Optional[str] = None) -> None:
        if model_path is None:
            model_path = str(MODELS_DIR / "rf.pkl")
        with open(model_path, "rb") as f:
            self.model = pickle.load(f)

    def predict(self, reading_features: Union[Dict, List, np.ndarray]) -> Tuple[State, float]:
        """
        Classify state and return (predicted_state, confidence).
        Confidence is the predicted class probability.
        """
        if self.model is None:
            self.load()

        if isinstance(reading_features, dict):
            # Use DataFrame to preserve feature names (suppresses sklearn UserWarning)
            vec = pd.DataFrame([[float(reading_features[c]) for c in FEATURE_COLUMNS]], columns=FEATURE_COLUMNS)
        elif isinstance(reading_features, list):
            vec = pd.DataFrame([reading_features], columns=FEATURE_COLUMNS)
        else:
            vec = reading_features.reshape(1, -1) if reading_features.ndim == 1 else reading_features

        proba = self.model.predict_proba(vec)[0]
        max_idx = np.argmax(proba)
        predicted_state = str(self.model.classes_[max_idx])
        confidence = float(proba[max_idx])

        return predicted_state, round(confidence, 4)
