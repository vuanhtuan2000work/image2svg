"""Part label inference via ILP (PuLP) with ICM graph-cut fallback."""

from __future__ import annotations

import platform
import shutil
import sys
from typing import Any, Literal

try:
    import pulp

    _HAS_PULP = True
except ImportError:
    pulp = None  # type: ignore
    _HAS_PULP = False

SolverMethod = Literal["ilp", "icm"]

INCOMPATIBLE_PAIRS: set[tuple[str, str]] = {
    ("eyeSet", "tailSet"),
    ("eyeSet", "backLegSet"),
    ("eyeSet", "frontLegSet"),
    ("earSet", "tailSet"),
}

COMPATIBLE_PAIRS: dict[tuple[str, str], float] = {
    ("eyeSet", "headBase"): 0.35,
    ("eyeSet", "faceSet"): 0.25,
    ("earSet", "headBase"): 0.30,
    ("faceSet", "headBase"): 0.28,
    ("tailSet", "bodySet"): 0.22,
    ("frontLegSet", "bodySet"): 0.20,
    ("backLegSet", "bodySet"): 0.20,
}

_CBC_USABLE: bool | None = None


def _pairwise_penalty(label_a: str, label_b: str, overlap: float, distance_norm: float) -> float:
    if (label_a, label_b) in INCOMPATIBLE_PAIRS or (label_b, label_a) in INCOMPATIBLE_PAIRS:
        if overlap > 0.05 or distance_norm < 0.25:
            return 1.2
    compat = COMPATIBLE_PAIRS.get((label_a, label_b)) or COMPATIBLE_PAIRS.get((label_b, label_a))
    if compat and distance_norm < 0.35:
        return -compat
    return 0.0


def _system_cbc_path() -> str | None:
    return shutil.which("cbc")


def _cbc_solver_usable() -> bool:
    """PuLP ships x86_64 CBC on macOS; Apple Silicon needs Homebrew cbc or ICM fallback."""
    global _CBC_USABLE
    if _CBC_USABLE is not None:
        return _CBC_USABLE

    if not _HAS_PULP or pulp is None:
        _CBC_USABLE = False
        return False

    if _system_cbc_path():
        _CBC_USABLE = True
        return True

    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        _CBC_USABLE = False
        return False

    _CBC_USABLE = True
    return True


def _build_pulp_solver() -> Any:
    assert pulp is not None
    cbc_path = _system_cbc_path()
    if cbc_path:
        return pulp.COIN_CMD(path=cbc_path, msg=False)
    return pulp.PULP_CBC_CMD(msg=False)


def _solve_ilp(
    component_ids: list[str],
    labels: list[str],
    unary_costs: dict[str, dict[str, float]],
    pairwise: list[tuple[str, str, float, float]],
    min_confidence: float,
) -> dict[str, str] | None:
    assert pulp is not None

    prob = pulp.LpProblem("part_labels", pulp.LpMinimize)
    x = pulp.LpVariable.dicts("x", (component_ids, labels), cat=pulp.LpBinary)

    for cid in component_ids:
        prob += pulp.lpSum(x[cid][label] for label in labels) == 1

    objective: list[Any] = []
    for cid in component_ids:
        for label in labels:
            cost = 1.0 - unary_costs.get(cid, {}).get(label, 0.0)
            objective.append(cost * x[cid][label])

    var_idx = 0
    for cid_a, cid_b, overlap, dist_norm in pairwise:
        for la in labels:
            for lb in labels:
                pen = _pairwise_penalty(la, lb, overlap, dist_norm)
                if abs(pen) < 1e-6:
                    continue
                z = pulp.LpVariable(f"pair_{var_idx}", cat=pulp.LpBinary)
                var_idx += 1
                prob += z <= x[cid_a][la]
                prob += z <= x[cid_b][lb]
                prob += z >= x[cid_a][la] + x[cid_b][lb] - 1
                objective.append(pen * z)

    prob += pulp.lpSum(objective)
    solver = _build_pulp_solver()
    status = prob.solve(solver)

    if pulp.LpStatus.get(status, "") not in {"Optimal", "Not Solved", "Undefined"}:
        if status != 1:
            return None

    assignment: dict[str, str] = {}
    for cid in component_ids:
        best_label = "unknown"
        best_score = -1.0
        for label in labels:
            if (pulp.value(x[cid][label]) or 0) > 0.5:
                best_label = label
                break
            score = unary_costs.get(cid, {}).get(label, 0.0)
            if score > best_score:
                best_score = score
                best_label = label
        if unary_costs.get(cid, {}).get(best_label, 0.0) < min_confidence:
            best_label = "unknown"
        assignment[cid] = best_label
    return assignment


def _solve_icm_fallback(
    component_ids: list[str],
    labels: list[str],
    unary_costs: dict[str, dict[str, float]],
    pairwise: list[tuple[str, str, float, float]],
    min_confidence: float,
) -> dict[str, str]:
    assignment: dict[str, str] = {}
    for cid in component_ids:
        scored = sorted(
            ((label, unary_costs.get(cid, {}).get(label, 0.0)) for label in labels),
            key=lambda t: t[1],
            reverse=True,
        )
        assignment[cid] = scored[0][0] if scored and scored[0][1] >= min_confidence else "unknown"

    for _ in range(8):
        changed = False
        for cid in component_ids:
            best_label = assignment[cid]
            best_cost = float("inf")
            for label in labels:
                unary = 1.0 - unary_costs.get(cid, {}).get(label, 0.0)
                pair_cost = 0.0
                for cid_a, cid_b, overlap, dist_norm in pairwise:
                    other = cid_b if cid_a == cid else cid_a if cid_b == cid else None
                    if other is None:
                        continue
                    pair_cost += _pairwise_penalty(label, assignment[other], overlap, dist_norm)
                total = unary + pair_cost
                if total < best_cost:
                    best_cost = total
                    best_label = label
            if best_label != assignment[cid]:
                assignment[cid] = best_label
                changed = True
        if not changed:
            break

    for cid in component_ids:
        if unary_costs.get(cid, {}).get(assignment[cid], 0.0) < min_confidence:
            assignment[cid] = "unknown"
    return assignment


def _disable_cbc() -> None:
    global _CBC_USABLE
    _CBC_USABLE = False


def solve_part_labels_ilp(
    component_ids: list[str],
    labels: list[str],
    unary_costs: dict[str, dict[str, float]],
    pairwise: list[tuple[str, str, float, float]],
    *,
    min_confidence: float = 0.25,
) -> tuple[dict[str, str], SolverMethod]:
    if not component_ids:
        return {}, "icm"

    if _HAS_PULP and pulp is not None and _cbc_solver_usable() and len(component_ids) <= 40:
        try:
            result = _solve_ilp(component_ids, labels, unary_costs, pairwise, min_confidence)
            if result is not None:
                return result, "ilp"
        except OSError as exc:
            if exc.errno not in {86, 8}:  # Bad CPU type / Exec format error
                raise
            _disable_cbc()
        except Exception:
            _disable_cbc()

    return _solve_icm_fallback(component_ids, labels, unary_costs, pairwise, min_confidence), "icm"
