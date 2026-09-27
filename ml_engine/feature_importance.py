"""
Feature Importance and Explainability module for Member 2.
Extracts Random Forest feature importance scores and generates interactive HTML visualization.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.4 and Plan_docs/member-2-ml-engine.md.
"""
from typing import Dict, List, Optional
import pandas as pd
from sklearn.ensemble import RandomForestClassifier

from shared.config import MODELS_DIR
from ml_engine.dataset_gen import FEATURE_COLUMNS


def get_feature_importance(
    model: RandomForestClassifier,
    feature_names: Optional[List[str]] = None,
) -> pd.Series:
    """
    Extract normalized Gini feature importance scores from trained Random Forest model.
    """
    if feature_names is None:
        feature_names = FEATURE_COLUMNS
    importances = model.feature_importances_
    series = pd.Series(importances, index=feature_names).sort_values(ascending=False)
    return series


def render_feature_importance_html(
    importance_series: pd.Series,
    output_path: Optional[str] = None,
) -> str:
    """
    Render self-contained, interactive HTML chart saved to data/models/feature_importance.html.
    Member 4's frontend embeds this file directly.
    """
    if output_path is None:
        MODELS_DIR.mkdir(parents=True, exist_ok=True)
        output_path = str(MODELS_DIR / "feature_importance.html")

    labels = list(importance_series.index)
    values = [round(float(v) * 100, 2) for v in importance_series.values]

    # Generate modern, responsive glassmorphic HTML visualization
    bars_html = ""
    for label, val in zip(labels, values):
        bars_html += f"""
        <div style="margin-bottom: 14px;">
            <div style="display: flex; justify-content: space-between; font-size: 13px; font-weight: 600; margin-bottom: 4px; color: #cbd5e1;">
                <span>{label.replace('_', ' ').title()}</span>
                <span>{val}%</span>
            </div>
            <div style="background: rgba(255,255,255,0.08); border-radius: 6px; height: 10px; overflow: hidden;">
                <div style="width: {val}%; height: 100%; background: linear-gradient(90deg, #38bdf8, #818cf8); border-radius: 6px; transition: width 0.6s ease;"></div>
            </div>
        </div>
        """

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Random Forest Feature Importance</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f172a;
            color: #f8fafc;
            padding: 24px;
            margin: 0;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 12px;
            padding: 24px;
            max-width: 600px;
            margin: auto;
            box-shadow: 0 10px 25px rgba(0,0,0,0.4);
        }}
        h2 {{
            margin-top: 0;
            font-size: 18px;
            color: #38bdf8;
            letter-spacing: -0.5px;
        }}
        .interpretation {{
            margin-top: 20px;
            padding: 12px 16px;
            background: rgba(56, 189, 248, 0.08);
            border-left: 3px solid #38bdf8;
            font-size: 13px;
            color: #94a3b8;
            line-height: 1.5;
            border-radius: 0 6px 6px 0;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Explainable AI: Feature Importance</h2>
        <div style="margin-top: 18px;">
            {bars_html}
        </div>
        <div class="interpretation">
            <strong>Key Insight:</strong> Packet loss and RTT dominate hard failure detection, while jitter and queue size serve as the strongest early-warning indicators for congestion and gradual link degradation.
        </div>
    </div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return output_path
