"""Machine learning risk model prediction tool.

Uses trained GradientBoostingClassifier to predict probability of AML high-risk.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from onboardiq.eval.train_risk_model import predict_high_risk_prob


class RiskModelInput(BaseModel):
    country_risk: float = Field(default=0.1, ge=0.0, le=1.0)
    occupation_risk: float = Field(default=0.1, ge=0.0, le=1.0)
    monthly_volume_inr: float = Field(default=50000.0, ge=0.0)
    num_red_flags: int = Field(default=0, ge=0)
    max_screening_score: float = Field(default=0.0, ge=0.0, le=1.0)
    tamper_score: float = Field(default=0.0, ge=0.0, le=1.0)
    is_company: bool = False


class RiskModelOutput(BaseModel):
    probability_high: float = Field(ge=0.0, le=1.0)
    model_version: str = "gradient_boosting_v1"


def predict_case_risk(
    country_risk: float = 0.1,
    occupation_risk: float = 0.1,
    monthly_volume_inr: float = 50000.0,
    num_red_flags: int = 0,
    max_screening_score: float = 0.0,
    tamper_score: float = 0.0,
    is_company: bool = False,
) -> RiskModelOutput:
    """Predict applicant high risk probability using trained ML estimator."""
    prob = predict_high_risk_prob(
        country_risk=country_risk,
        occupation_risk=occupation_risk,
        monthly_volume_inr=monthly_volume_inr,
        num_red_flags=num_red_flags,
        max_screening_score=max_screening_score,
        tamper_score=tamper_score,
        is_company=is_company,
    )
    return RiskModelOutput(
        probability_high=round(prob, 4),
        model_version="gradient_boosting_v1",
    )
