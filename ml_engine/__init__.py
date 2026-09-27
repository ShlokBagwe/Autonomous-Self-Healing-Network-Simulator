"""
Machine Learning Engine for Member 2.
Includes synthetic dataset generation, unsupervised Isolation Forest anomaly detection,
supervised Random Forest classification, explainable feature importance, and real-time inference.
"""
from ml_engine.dataset_gen import generate_dataset
from ml_engine.isolation_forest import train_iforest, AnomalyDetector
from ml_engine.random_forest import train_rf, NetworkStateClassifier
from ml_engine.feature_importance import get_feature_importance, render_feature_importance_html
from ml_engine.inference import MLInferenceService

__all__ = [
    "generate_dataset",
    "train_iforest",
    "AnomalyDetector",
    "train_rf",
    "NetworkStateClassifier",
    "get_feature_importance",
    "render_feature_importance_html",
    "MLInferenceService",
]
