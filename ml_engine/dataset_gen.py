"""
Telemetry Dataset Generator and EDA for Member 2.
Generates synthetic-yet-realistic telemetry datasets matching canonical CSV schema
(Master Section 4.1) and outputs exploratory data analysis (EDA).
"""
import json
import os
import random
from typing import Dict, List, Optional
import numpy as np
import pandas as pd

from shared.config import RAW_DATA_DIR

FEATURE_COLUMNS = ["latency", "jitter", "packet_loss", "queue", "throughput", "utilization"]
CANONICAL_COLUMNS = ["timestamp", "link", "latency", "jitter", "packet_loss", "queue", "throughput", "utilization", "state"]


def generate_dataset(
    n_samples: int = 6000,
    seed: int = 42,
    save_csv: bool = True,
    csv_filename: str = "telemetry_dataset.csv",
) -> pd.DataFrame:
    """
    Generate synthetic telemetry dataset with healthy, congested, and failed network states.
    Header: timestamp,link,latency,jitter,packet_loss,queue,throughput,utilization,state
    """
    np.random.seed(seed)
    random.seed(seed)

    links = ["A-B", "B-C", "C-D", "D-E", "E-F", "F-G", "G-H", "H-I", "I-J", "A-E", "B-F", "C-G", "D-H"]

    # Target class distribution: 60% healthy, 25% congested, 15% failed
    n_healthy = int(n_samples * 0.60)
    n_congested = int(n_samples * 0.25)
    n_failed = n_samples - n_healthy - n_congested

    records: List[Dict] = []
    base_time = 1000.0

    # 1. Healthy state
    for i in range(n_healthy):
        ts = base_time + i * 0.5
        link = random.choice(links)
        records.append({
            "timestamp": round(ts, 2),
            "link": link,
            "latency": round(float(np.random.normal(8.0, 2.0)), 2),
            "jitter": round(max(0.1, float(np.random.normal(1.2, 0.4))), 2),
            "packet_loss": round(max(0.0, float(np.random.exponential(0.2))), 2),
            "queue": int(np.random.poisson(1.5)),
            "throughput": round(min(100.0, max(75.0, float(np.random.normal(92.0, 4.0)))), 2),
            "utilization": round(min(0.5, max(0.1, float(np.random.normal(0.28, 0.05)))), 3),
            "state": "healthy",
        })

    # 2. Congested state
    for i in range(n_congested):
        ts = base_time + (n_healthy + i) * 0.5
        link = random.choice(links)
        records.append({
            "timestamp": round(ts, 2),
            "link": link,
            "latency": round(float(np.random.normal(75.0, 15.0)), 2),
            "jitter": round(float(np.random.normal(22.0, 5.0)), 2),
            "packet_loss": round(min(25.0, max(2.0, float(np.random.normal(8.0, 3.0)))), 2),
            "queue": int(np.random.normal(55, 12)),
            "throughput": round(min(50.0, max(10.0, float(np.random.normal(32.0, 7.0)))), 2),
            "utilization": round(min(0.99, max(0.80, float(np.random.normal(0.91, 0.04)))), 3),
            "state": "congested",
        })

    # 3. Failed state
    for i in range(n_failed):
        ts = base_time + (n_healthy + n_congested + i) * 0.5
        link = random.choice(links)
        records.append({
            "timestamp": round(ts, 2),
            "link": link,
            "latency": round(min(9999.0, max(250.0, float(np.random.normal(450.0, 80.0)))), 2),
            "jitter": round(float(np.random.normal(50.0, 15.0)), 2),
            "packet_loss": round(min(100.0, max(90.0, float(np.random.normal(98.0, 1.5)))), 2),
            "queue": int(max(0, np.random.poisson(0.5))),
            "throughput": round(max(0.0, float(np.random.exponential(0.5))), 2),
            "utilization": round(max(0.0, min(0.05, float(np.random.exponential(0.01)))), 3),
            "state": "failed",
        })

    df = pd.DataFrame(records)
    # Shuffle dataframe
    df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)

    if save_csv:
        RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = RAW_DATA_DIR / csv_filename
        df.to_csv(csv_path, index=False)

        # Generate EDA outputs
        perform_eda(df, RAW_DATA_DIR)

    return df


def perform_eda(df: pd.DataFrame, output_dir) -> Dict:
    """
    Perform Exploratory Data Analysis (EDA) on dataset:
    - Class balance counts
    - Feature summary statistics per state
    - Correlation matrix across features
    """
    class_balance = df["state"].value_counts().to_dict()
    feature_stats = df.groupby("state")[FEATURE_COLUMNS].mean().to_dict()
    correlation_matrix = df[FEATURE_COLUMNS].corr().to_dict()

    eda_summary = {
        "total_samples": len(df),
        "class_balance": class_balance,
        "feature_means_by_state": feature_stats,
        "correlation_matrix": correlation_matrix,
    }

    eda_path = os.path.join(output_dir, "eda_summary.json")
    with open(eda_path, "w", encoding="utf-8") as f:
        json.dump(eda_summary, f, indent=2)

    return eda_summary
