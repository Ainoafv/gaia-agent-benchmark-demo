"""Quasi-exact-match scorer, modeled on GAIA's own answer-matching convention:
case-insensitive, punctuation/whitespace-insensitive, numeric-tolerant."""
from __future__ import annotations

import re


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9.\-]", "", value.strip().lower())


def is_correct(predicted: str, expected: str, numeric_tol: float = 1e-2) -> bool:
    pred_norm, exp_norm = _normalize(predicted), _normalize(expected)
    if pred_norm == exp_norm:
        return True
    try:
        return abs(float(pred_norm) - float(exp_norm)) <= numeric_tol
    except ValueError:
        return False
