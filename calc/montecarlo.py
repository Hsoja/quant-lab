"""Estadísticas históricas (μ, σ) para la simulación Monte Carlo.

Capa B de la página (SIMULADO): el código calcula los números a partir de
cierres diarios reales; la página solo los usa para simular. Si no hay
suficientes datos, devuelve None — nunca se inventa un μ o σ.

Modelo (GBM, tiempo discreto, dt = 1/252):
    S[t+1] = S[t] * exp((mu - sigma^2 / 2) * dt + sigma * sqrt(dt) * Z)
mu y sigma se estiman de los retornos logarítmicos diarios, anualizados.
Es un modelo simple: no captura colas gordas, saltos ni cambios de régimen.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

TRADING_DAYS = 252
MIN_OBSERVATIONS = 120  # ~6 meses de cierres; menos que eso no es confiable


@dataclass(frozen=True)
class ReturnStats:
    mu: float  # retorno logarítmico anualizado (media diaria * 252)
    sigma: float  # volatilidad anualizada
    n_obs: int  # cantidad de retornos diarios usados


def compute_return_stats(closes: list[float]) -> ReturnStats | None:
    """μ y σ anualizados de cierres diarios consecutivos. None si hay pocos
    datos o valores no positivos."""
    clean = [c for c in closes if c is not None]
    if len(clean) != len(closes) or any(c <= 0 or not math.isfinite(c) for c in clean):
        return None
    if len(clean) < MIN_OBSERVATIONS + 1:
        return None
    rets = [math.log(b / a) for a, b in zip(clean, clean[1:])]
    n = len(rets)
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    return ReturnStats(mu=mean * TRADING_DAYS, sigma=math.sqrt(var * TRADING_DAYS), n_obs=n)


def simulate_gbm(
    *, s0: float, mu: float, sigma: float, days: int, n_paths: int, seed: int = 0
) -> list[float]:
    """Precios finales de n_paths trayectorias GBM (referencia en Python de
    la misma fórmula que corre en el navegador; sirve para las pruebas)."""
    rng = random.Random(seed)  # nosec B311 - simulación estadística, no criptografía
    dt = 1 / TRADING_DAYS
    drift = (mu - sigma * sigma / 2) * dt
    vol = sigma * math.sqrt(dt)
    finals = []
    for _ in range(n_paths):
        log_s = math.log(s0)
        for _ in range(days):
            log_s += drift + vol * rng.gauss(0, 1)
        finals.append(math.exp(log_s))
    return finals
