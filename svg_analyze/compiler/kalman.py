"""Kalman filtering for landmark / part centroid smoothing."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class KalmanState:
    x: np.ndarray
    p: np.ndarray
    history: list[tuple[float, float]] = field(default_factory=list)


class KalmanFilter2D:
    """Constant-velocity Kalman filter for 2D points."""

    def __init__(self, process_noise: float = 1e-2, measurement_noise: float = 2.0) -> None:
        self.q = process_noise
        self.r = measurement_noise
        self.state: KalmanState | None = None

    def init(self, x: float, y: float) -> None:
        self.state = KalmanState(
            x=np.array([x, y, 0.0, 0.0], dtype=float),
            p=np.eye(4, dtype=float) * 10.0,
            history=[(x, y)],
        )

    def predict(self) -> tuple[float, float]:
        if self.state is None:
            return 0.0, 0.0
        f = np.array([[1, 0, 1, 0], [0, 1, 0, 1], [0, 0, 1, 0], [0, 0, 0, 1]], dtype=float)
        q = np.eye(4, dtype=float) * self.q
        self.state.x = f @ self.state.x
        self.state.p = f @ self.state.p @ f.T + q
        return float(self.state.x[0]), float(self.state.x[1])

    def update(self, mx: float, my: float) -> tuple[float, float]:
        if self.state is None:
            self.init(mx, my)
            return mx, my
        self.predict()
        h = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], dtype=float)
        r = np.eye(2, dtype=float) * self.r
        z = np.array([mx, my], dtype=float)
        y = z - h @ self.state.x
        s = h @ self.state.p @ h.T + r
        k = self.state.p @ h.T @ np.linalg.inv(s)
        self.state.x = self.state.x + k @ y
        self.state.p = (np.eye(4) - k @ h) @ self.state.p
        sx, sy = float(self.state.x[0]), float(self.state.x[1])
        self.state.history.append((sx, sy))
        return sx, sy

    def smooth_sequence(self, points: list[tuple[float, float]]) -> list[tuple[float, float]]:
        if not points:
            return []
        self.state = None
        filtered: list[tuple[float, float]] = []
        for x, y in points:
            filtered.append(self.update(x, y))
        # Rauch-Tung-Striebel-lite: backward pass averaging with next filtered
        if len(filtered) < 2:
            return filtered
        rts = list(filtered)
        for i in range(len(filtered) - 2, -1, -1):
            rts[i] = ((filtered[i][0] + rts[i + 1][0]) / 2, (filtered[i][1] + rts[i + 1][1]) / 2)
        return rts


def smooth_tracks_kalman(
    observations: list[dict],
) -> list[dict[str, float]]:
    """Apply Kalman smoothing to a list of {centroid:{x,y}} observations."""
    kf = KalmanFilter2D()
    pts = [(float(o["centroid"]["x"]), float(o["centroid"]["y"])) for o in observations]
    smoothed = kf.smooth_sequence(pts)
    return [{"x": round(x, 4), "y": round(y, 4)} for x, y in smoothed]
