"""Synthetic risk training dataset generation and model training.

Trains a scikit-learn GradientBoostingClassifier on synthetic AML risk features
and serializes the trained estimator to data/models/.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from joblib import dump, load
from sklearn.ensemble import GradientBoostingClassifier

ROOT_DIR = Path(__file__).resolve().parents[3]
MODELS_DIR = ROOT_DIR / "data" / "models"
MODEL_PATH = MODELS_DIR / "risk_gradient_boosting.joblib"


def generate_training_data(n_samples: int = 500, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Generate synthetic AML risk training data with deterministic rule-based labels plus noise."""
    rng = np.random.RandomState(seed)

    country_risk = rng.beta(2, 5, size=n_samples)  # most countries are low/med risk
    occupation_risk = rng.beta(2, 4, size=n_samples)
    volume_log = rng.uniform(4.0, 8.0, size=n_samples)  # log10(INR 10k to 100M)
    num_red_flags = rng.poisson(0.4, size=n_samples)
    max_screening_score = rng.beta(1, 6, size=n_samples)
    tamper_score = rng.beta(1, 8, size=n_samples)
    is_company = rng.binomial(1, 0.4, size=n_samples)

    # Underlying latent risk probability
    latent_score = (
        0.30 * (num_red_flags > 0).astype(float)
        + 0.35 * (max_screening_score > 0.75).astype(float)
        + 0.20 * (tamper_score > 0.4).astype(float)
        + 0.15 * country_risk
        + 0.10 * occupation_risk
        + 0.10 * (volume_log > 6.5).astype(float)
        + rng.normal(0, 0.05, size=n_samples)
    )

    y = (latent_score > 0.45).astype(int)

    X = np.column_stack([
        country_risk,
        occupation_risk,
        volume_log,
        num_red_flags,
        max_screening_score,
        tamper_score,
        is_company,
    ])

    return X, y


def train_and_save_model() -> GradientBoostingClassifier:
    """Train Gradient Boosting model and save artifact."""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    X, y = generate_training_data(n_samples=600, seed=42)

    clf = GradientBoostingClassifier(
        n_estimators=50,
        max_depth=3,
        learning_rate=0.1,
        random_state=42,
    )
    clf.fit(X, y)
    dump(clf, MODEL_PATH)
    return clf


def predict_high_risk_prob(
    country_risk: float,
    occupation_risk: float,
    monthly_volume_inr: float,
    num_red_flags: int,
    max_screening_score: float,
    tamper_score: float,
    is_company: bool,
) -> float:
    """Load model and predict probability of high risk for an applicant."""
    if not MODEL_PATH.exists():
        train_and_save_model()

    clf = load(MODEL_PATH)
    volume_log = np.log10(max(monthly_volume_inr, 1000.0))
    feature_row = np.array([[
        country_risk,
        occupation_risk,
        volume_log,
        num_red_flags,
        max_screening_score,
        tamper_score,
        1.0 if is_company else 0.0,
    ]])
    probs = clf.predict_proba(feature_row)
    return float(probs[0, 1])


if __name__ == "__main__":
    model = train_and_save_model()
    print(f"Risk model trained and saved to {MODEL_PATH}")
