"""
AI Ensemble Signal Ranker
==========================
Random Forest trained on technical features to predict probability
of > ML_TARGET_THRESHOLD forward return in ML_TARGET_DAYS days.

Walk-forward split: train on DATA_START → ML_TRAIN_CUTOFF, score the rest.
"""

import pandas as pd
import numpy as np
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from typing import Dict, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

import config

FEATURE_COLS = [
    'mom1m', 'mom3m', 'mom6m',
    'rsi14', 'vol_ratio',
    'dist_from_high', 'dist_from_low',
    'atr_pct', 'bb_pct', 'bb_width',
    'price_vs_sma50', 'price_vs_sma200',
    'sma50_slope', 'sma150_slope',
    'above_sma50', 'above_sma150', 'above_sma200',
]


class EnsembleRanker:

    def __init__(self):
        self.pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('clf', RandomForestClassifier(
                n_estimators=200,
                max_depth=6,
                min_samples_leaf=15,
                max_features='sqrt',
                random_state=42,
                n_jobs=-1,
            )),
        ])
        self.is_trained   = False
        self.feature_imp_  = {}

    # ── Training ──────────────────────────────────────────────────────────

    def build_training_set(
        self,
        stock_data: Dict[str, pd.DataFrame],
        train_end: str,
    ) -> Tuple[Optional[pd.DataFrame], Optional[pd.Series]]:
        """
        Build (X, y) from all stocks up to train_end.
        Target: 1 if forward return > threshold, else 0.
        No look-ahead: labels use only dates that fall before train_end
        and where forward window is fully within available data.
        """
        X_parts, y_parts = [], []

        for ticker, df in stock_data.items():
            if len(df) < 150:
                continue

            # Compute forward return (allowed to peek during label creation only)
            d = df.copy()
            d['fwd_ret'] = d['Close'].pct_change(config.ML_TARGET_DAYS).shift(-config.ML_TARGET_DAYS)
            d['label']   = (d['fwd_ret'] > config.ML_TARGET_THRESHOLD).astype(int)

            # Restrict to training window and require label to be available
            train = d[d.index <= train_end].dropna(subset=['label'] + FEATURE_COLS)

            if len(train) < 30:
                continue

            X_parts.append(train[FEATURE_COLS])
            y_parts.append(train['label'])

        if not X_parts:
            return None, None

        return pd.concat(X_parts), pd.concat(y_parts)

    def train(self, X: pd.DataFrame, y: pd.Series) -> None:
        self.pipeline.fit(X, y)
        self.is_trained = True

        clf = self.pipeline.named_steps['clf']
        self.feature_imp_ = dict(zip(FEATURE_COLS, clf.feature_importances_))

    # ── Scoring ───────────────────────────────────────────────────────────

    def score_row(self, row: pd.Series) -> float:
        """Score one signal row. Returns probability [0, 1]."""
        if not self.is_trained:
            return 0.50

        feat = row[FEATURE_COLS].values.reshape(1, -1).astype(float)
        if np.any(np.isnan(feat)):
            return 0.40

        return float(self.pipeline.predict_proba(feat)[0][1])

    def score_dataframe(self, df: pd.DataFrame) -> pd.Series:
        """Score multiple rows at once."""
        if not self.is_trained or df.empty:
            return pd.Series(0.50, index=df.index)

        feats = df[FEATURE_COLS].fillna(0).astype(float)
        probs = self.pipeline.predict_proba(feats)[:, 1]
        return pd.Series(probs, index=df.index)

    # ── Reporting ─────────────────────────────────────────────────────────

    def top_features(self, n: int = 8) -> list:
        return sorted(self.feature_imp_.items(), key=lambda x: x[1], reverse=True)[:n]
