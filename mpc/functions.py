from typing import Tuple, Sequence, List, Optional, Any, Callable
import random
import time
import math

# Types
ProgressCallback = Callable[[int, List[float], float, List[float], float], None]
# args: (iter_idx, angles, value, best_angles, best_value)

class PaddleOptimizer:
    def __init__(self):
        # a set of 4 values tuples, paddle 1, 2, 3 and the detector value
        self.known_pos = set()
        # past previous best positions, should be read in from a file
        self.prev_bests = set()

    def read_prev_best(self):
        # TODO read from file || it is for later not now
        pass

    def reset(self):
        # empty known known positions
        pass

    def _get_next_paddle_state(self) -> List[float]:
        # use know positions to caluclate the next step to scout
        next_pos: List[float] = [0 for _ in range(3)]
        return next_pos

    def _get_optimum_paddle_state(self) -> List[float]:
        # after we dont have this scour more, this should be called to get the opt one
        optimum: List[list] = [0 for _ in range(3)]
        # print optimum
        return optimum

    def _get_next_optimized_paddle_states_dummy(self) -> List[float]:
        """Get next optimized paddle states.
        Returns:
        - optimum: three random angles in degrees
        """
        rng = random.Random(12345)
        optimum: List[float] = [rng.uniform(0.0, 170.0) for _ in range(3)]
        return  optimum


def _clip_angles(angles: List[float], lo: float, hi: float) -> List[float]:
    return [min(max(a, lo), hi) for a in angles]


def _measure_counts(tc: Any, channel: int, samples: int = 2, inter_sample_sleep: float = 0.02) -> float:
    acc = 0.0
    for s in range(max(1, samples)):
        try:
            v = tc.query_counter(channel)
        except Exception:
            v = 0
        acc += float(v)
        if s + 1 < samples and inter_sample_sleep > 0:
            time.sleep(inter_sample_sleep)
    return acc / max(1, samples)


def optimize_paddles(
    controller: Any,
    tc: Any,
    channel: int,
    *,
    angle_min: float = 0.0,
    angle_max: float = 160.0,
    seeds: int = 5,
    init_angles: Optional[List[float]] = None,
    measure_samples: int = 2,
    dwell_after_move_s: float = 0.05,
    fd_delta_deg: float = 2.0,
    lr_deg: float = 5.0,
    momentum_beta: float = 0.8,
    max_iters: int = 100,
    patience: int = 6,
    progress: Optional[ProgressCallback] = None,
    stop_event: Optional[Any] = None,
) -> Tuple[List[float], float]:
    """Gradient-ascent with momentum to maximize TC counts by tuning three paddles.

    Returns (best_angles, best_value). Uses central differences per axis.
    """
    # Local helpers
    def move_to_three(ang: List[float]):
        controller.move_to_three(tuple(ang))
        if dwell_after_move_s > 0:
            time.sleep(dwell_after_move_s)

    def eval_at(ang: List[float]) -> float:
        ang = _clip_angles(ang, angle_min, angle_max)
        move_to_three(ang)
        return _measure_counts(tc, channel, samples=measure_samples)

    # Seed selection
    candidate_starts: List[List[float]] = []
    if init_angles:
        candidate_starts.append(_clip_angles(list(init_angles), angle_min, angle_max))
    # Spread seeds roughly across space
    rng = random.Random(42)
    centers = [80.0, 80.0, 80.0]
    span = (angle_max - angle_min)
    for _ in range(max(0, seeds - len(candidate_starts))):
        candidate_starts.append([
            max(angle_min, min(angle_max, centers[i] + rng.uniform(-0.35, 0.35) * span))
            for i in range(3)
        ])

    # Evaluate seeds quickly, pick best
    best_seed_val = -1.0
    start_angles = candidate_starts[0] if candidate_starts else [80.0, 80.0, 80.0]
    for ang in candidate_starts:
        if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
            break
        v = eval_at(ang)
        if v > best_seed_val:
            best_seed_val = v
            start_angles = ang

    # Initialize state
    x = list(start_angles)
    fx = eval_at(x)
    best_x = list(x)
    best_fx = fx
    v_m = [0.0, 0.0, 0.0]
    no_improve = 0

    # Report initial state so GUI can display starting angles/value
    if progress is not None:
        try:
            progress(0, list(x), float(fx), list(best_x), float(best_fx))
        except Exception:
            pass

    # Iterations
    for it in range(1, max_iters + 1):
        if stop_event is not None and getattr(stop_event, 'is_set', lambda: False)():
            break
        # Central differences per axis; move one paddle at a time to reduce travel
        grad = [0.0, 0.0, 0.0]
        for i in range(3):
            x_minus = list(x)
            x_plus = list(x)
            x_minus[i] = max(angle_min, x[i] - fd_delta_deg)
            x_plus[i] = min(angle_max, x[i] + fd_delta_deg)
            # Move only paddle i
            try:
                paddles = controller.get_paddles()
                controller.move_to(x_plus[i], paddles[i])
                if dwell_after_move_s > 0:
                    time.sleep(dwell_after_move_s)
                f_plus = _measure_counts(tc, channel, samples=measure_samples)
                controller.move_to(x_minus[i], paddles[i])
                if dwell_after_move_s > 0:
                    time.sleep(dwell_after_move_s)
                f_minus = _measure_counts(tc, channel, samples=measure_samples)
                # Return to center
                controller.move_to(x[i], paddles[i])
                if dwell_after_move_s > 0:
                    time.sleep(dwell_after_move_s)
            except Exception:
                # Fallback: evaluate with full moves (slower)
                f_plus = eval_at(x_plus)
                f_minus = eval_at(x_minus)
                move_to_three(x)
            grad[i] = (f_plus - f_minus) / max(1e-6, (x_plus[i] - x_minus[i]))

        # Momentum update
        for i in range(3):
            v_m[i] = momentum_beta * v_m[i] + (1.0 - momentum_beta) * grad[i]

        # Normalize step to avoid huge jumps when gradient is large
        norm = math.sqrt(sum(g * g for g in v_m)) or 1.0
        step = [lr_deg * (g / norm) for g in v_m]
        x_new = _clip_angles([x[i] + step[i] for i in range(3)], angle_min, angle_max)
        fx_new = eval_at(x_new)

        improved = fx_new > fx
        if improved:
            x, fx = x_new, fx_new
            if fx_new > best_fx:
                best_x, best_fx = list(x_new), fx_new
            no_improve = 0
        else:
            # Backoff learning rate slightly on non-improvement
            lr_deg = max(0.5, lr_deg * 0.7)
            no_improve += 1

        if progress is not None:
            try:
                progress(it, list(x), float(fx), list(best_x), float(best_fx))
            except Exception:
                pass

        if no_improve >= patience:
            break

    # Move to the best found angles at the end
    try:
        move_to_three(best_x)
    except Exception:
        print("An exception has occurred in functions while optimizing paddles.")
    return best_x, best_fx

