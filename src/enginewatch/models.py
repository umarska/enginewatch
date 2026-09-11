"""Simple serializable reference estimators used by the benchmark."""

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, RegressorMixin


class AgeBaselineRegressor(RegressorMixin, BaseEstimator):
    """Predict mean training-engine lifetime minus observed age, clipped at zero."""

    def fit(self, X: pd.DataFrame, y: np.ndarray, sample_weight: np.ndarray | None = None):
        self.mean_lifetime_ = float(np.average(X["cycle"].to_numpy() + np.asarray(y), weights=sample_weight))
        self.n_features_in_ = X.shape[1]
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        return np.maximum(0.0, self.mean_lifetime_ - X["cycle"].to_numpy())
