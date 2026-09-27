"""
Isolation Forest module for Member 2.
Unsupervised anomaly detection for early warning and unknown network degradation patterns.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.4 and Plan_docs/member-2-ml-engine.md.
"""
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml_engine.dataset_gen import FEATURE_COLUMNS


def train_iforest(
    df: pd.DataFrame,
    contamination: float = 0.35,
    random_state: int = 42,
) -> IsolationForest:
    """
    Train an unsupervised Isolation Forest model on numerical telemetry features.
    Flags anomalous rows (unsupervised signal) independent of class labels.
    """
    X = df[FEATURE_COLUMNS].values
    model = IsolationForest(
        n_estimators=100,
        contamination=contamination,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(X)
    return model


class AnomalyDetector:
    """Wrapper around trained IsolationForest model."""

    def __init__(self, model: Optional[IsolationForest] = None):
        self.model = model

    def fit(self, df: pd.DataFrame) -> None:
        self.model = train_iforest(df)

    def is_anomalous(self, features: Union[Dict, List, np.ndarray]) -> bool:
        """Returns True if telemetry point is flagged as an anomaly (-1)."""
        if self.model is None:
            return False

        if isinstance(features, dict):
            vec = np.array([[features[col] for col in FEATURE_COLUMNS]])
        elif isinstance(features, list):
            vec = np.array([features])
        else:
            vec = features.reshape(1, -1) if features.ndim == 1 else features

        pred = self.model.predict(vec)
        return bool(pred[0] == -1)
