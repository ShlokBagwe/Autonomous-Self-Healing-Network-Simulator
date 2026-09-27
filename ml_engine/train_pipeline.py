"""
End-to-End Training and Explainability Pipeline for Member 2.
Generates synthetic dataset with EDA, trains Isolation Forest and Random Forest models,
saves trained artifacts, and outputs feature importance chart.
Defined in Plan_docs/00_PROJECT_MASTER.md Section 6.4 and Plan_docs/member-2-ml-engine.md.
"""
import json
import logging
from ml_engine.dataset_gen import generate_dataset
from ml_engine.isolation_forest import train_iforest
from ml_engine.random_forest import train_rf
from ml_engine.feature_importance import get_feature_importance, render_feature_importance_html

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ml_train_pipeline")


def run_pipeline():
    logger.info("1. Generating synthetic telemetry dataset with EDA...")
    df = generate_dataset(n_samples=6000, seed=42, save_csv=True)
    logger.info(f"   Dataset shape: {df.shape}")

    logger.info("2. Training unsupervised Isolation Forest...")
    iforest = train_iforest(df)
    logger.info("   Isolation Forest trained successfully.")

    logger.info("3. Training supervised Random Forest state classifier...")
    rf_model, report = train_rf(df, save_model=True)
    logger.info(f"   Accuracy: {report['overall_accuracy']:.4f}, Macro F1: {report['macro_f1']:.4f}")

    logger.info("4. Extracting feature importance scores...")
    importance_series = get_feature_importance(rf_model)
    logger.info("\nFeature Importance Rankings:")
    for feat, score in importance_series.items():
        logger.info(f"   - {feat}: {score * 100:.2f}%")

    logger.info("5. Rendering interactive feature importance HTML visualization...")
    html_path = render_feature_importance_html(importance_series)
    logger.info(f"   Visualization saved to: {html_path}")

    return {
        "dataset_rows": len(df),
        "accuracy": report["overall_accuracy"],
        "macro_f1": report["macro_f1"],
        "feature_importances": importance_series.to_dict(),
        "html_path": html_path,
    }


if __name__ == "__main__":
    res = run_pipeline()
    print("\nPipeline Result Summary:")
    print(json.dumps(res, indent=2))
