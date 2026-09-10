"""NEC equations (1)--(3), (9)--(13), implemented without author toy rules.

The ODE and cumulative intensity are integrated together with fixed-step RK4.
Timestamps use the predictor's explicitly configured time unit, not wall seconds.
"""

from __future__ import annotations

import math
from itertools import groupby

import torch
from torch import Tensor, nn


class ODERNNPointProcess(nn.Module):
    def __init__(self, n_types: int, hidden_size: int = 32,
                 embedding_size: int = 16, ode_step: float = 0.25,
                 max_ode_steps: int = 4096):
        super().__init__()
        if n_types < 1 or hidden_size < 1 or embedding_size < 1:
            raise ValueError("Model dimensions must be positive")
        if not math.isfinite(ode_step) or ode_step <= 0 or max_ode_steps < 1:
            raise ValueError("Invalid ODE integration budget")
        self.n_types = n_types
        self.hidden_size = hidden_size
        self.ode_step = ode_step
        self.max_ode_steps = max_ode_steps
        self.embedding = nn.Embedding(n_types, embedding_size, padding_idx=0)
        nn.init.normal_(self.embedding.weight, std=0.1)
        with torch.no_grad():
            self.embedding.weight[0].zero_()
        self.dynamics = nn.Sequential(nn.Linear(hidden_size, hidden_size),
                                      nn.Tanh(), nn.Linear(hidden_size, hidden_size))
        self.jump = nn.GRUCell(embedding_size, hidden_size)
        self.query = nn.Sequential(nn.Linear(hidden_size, embedding_size), nn.Tanh(),
                                   nn.Linear(embedding_size, embedding_size))
        self.type_features = nn.Linear(embedding_size, embedding_size)

    def initial_state(self) -> Tensor:
        return self.embedding.weight.new_zeros(self.hidden_size)

    def log_rates(self, state: Tensor) -> Tensor:
        # Eq. (2): log lambda_k(t) = NN3(h(t^-)) dot phi(v_k).
        return self.type_features(self.embedding.weight) @ self.query(state)

    def evolve(self, state: Tensor, duration: float, integrate: bool = True):
        if not math.isfinite(duration) or duration < 0:
            raise ValueError("Non-finite or reversed time interval")
        total = state.new_zeros(())
        if duration == 0:
            return state, total
        steps = math.ceil(duration / self.ode_step)
        if steps > self.max_ode_steps:
            raise ValueError(f"ODE interval needs {steps} steps; budget is {self.max_ode_steps}")
        dt = duration / steps
        for _ in range(steps):
            k1 = self.dynamics(state)
            s2 = state + dt * k1 / 2
            k2 = self.dynamics(s2)
            s3 = state + dt * k2 / 2
            k3 = self.dynamics(s3)
            s4 = state + dt * k3
            k4 = self.dynamics(s4)
            if integrate:
                rates = [self.log_rates(s).exp().sum() for s in (state, s2, s3, s4)]
                total = total + dt * (rates[0] + 2 * rates[1] + 2 * rates[2] + rates[3]) / 6
            state = state + dt * (k1 + 2 * k2 + 2 * k3 + k4) / 6
        return state, total

    def trajectory(self, times: list[float], embeddings: Tensor, end: float,
                   integrate: bool = True):
        if len(times) != len(embeddings):
            raise ValueError("Time/embedding lengths differ")
        if not math.isfinite(end) or end <= 0:
            raise ValueError("Observation duration must be positive")
        if any(not math.isfinite(t) or t < 0 or t > end for t in times):
            raise ValueError("Events must be inside the observation window")
        if times != sorted(times):
            raise ValueError("Events must be sorted")
        state = self.initial_state()
        integral = state.new_zeros(())
        previous = 0.0
        log_intensities = []
        for timestamp, indices_iter in groupby(range(len(times)), key=lambda j: times[j]):
            indices = list(indices_iter)
            state, mass = self.evolve(state, timestamp - previous, integrate)
            integral = integral + mass
            pre_event_rates = self.log_rates(state)
            # A tied event may not use another event at the same timestamp.
            log_intensities.extend([pre_event_rates] * len(indices))
            for index in indices:
                state = self.jump(embeddings[index], state)
            previous = timestamp
        state, tail_mass = self.evolve(state, end - previous, integrate)
        integral = integral + tail_mass
        logs = (torch.stack(log_intensities) if log_intensities else
                self.embedding.weight.new_empty((0, self.n_types)))
        return logs, integral, state

    def loss(self, times: list[float], types: Tensor, end: float,
             prior: Tensor, regularization_weight: float = 1.0):
        embeddings = self.embedding(types)
        logs, integral, _ = self.trajectory(times, embeddings, end)
        event_log_likelihood = (logs.gather(1, types[:, None]).sum() if len(types)
                                else integral.new_zeros(()))
        nll = integral - event_log_likelihood
        # Keep all event timestamps and recurrent jumps, zero only input embeddings.
        null_logs, _, _ = self.trajectory(times, torch.zeros_like(embeddings), end, False)
        regularizer = (null_logs.exp() - prior[None, :]).square().sum()
        objective = nll + regularization_weight * regularizer
        if not torch.isfinite(objective):
            raise FloatingPointError("Non-finite likelihood/regularizer; no intensity clipping performed")
        return objective, {"nll": nll, "integral": integral,
                           "event_log_likelihood": event_log_likelihood,
                           "empty_history_regularizer": regularizer}

    def target_log_intensity(self, history_times: list[float], history_embeddings: Tensor,
                             target_time: float, target_type: int) -> Tensor:
        if any(t >= target_time for t in history_times):
            raise ValueError("IG history must precede the target strictly")
        if target_time == 0 and not history_times:
            return self.log_rates(self.initial_state())[target_type]
        _, _, state = self.trajectory(history_times, history_embeddings, target_time, False)
        return self.log_rates(state)[target_type]

    def integrated_gradients(self, history_times: list[float], history_types: Tensor,
                             target_time: float, target_type: int, steps: int = 32):
        """IG of log intensity; sums signed feature contributions per source event."""
        if steps < 1:
            raise ValueError("IG steps must be positive")
        embeddings = self.embedding(history_types).detach()
        if not len(history_times):
            return [], {"completeness_residual": 0.0, "log_intensity_delta": 0.0}
        gradient_sum = torch.zeros_like(embeddings)
        with torch.enable_grad():
            for step in range(steps + 1):
                point = (embeddings * (step / steps)).requires_grad_(True)
                output = self.target_log_intensity(history_times, point, target_time, target_type)
                gradient = torch.autograd.grad(output, point)[0]
                gradient_sum += gradient.detach() * (0.5 if step in (0, steps) else 1.0)
        scores = (embeddings * gradient_sum / steps).sum(-1)
        with torch.no_grad():
            actual = self.target_log_intensity(history_times, embeddings, target_time, target_type)
            baseline = self.target_log_intensity(history_times, torch.zeros_like(embeddings),
                                                 target_time, target_type)
        residual = scores.sum() - (actual - baseline)
        if not torch.isfinite(scores).all() or not torch.isfinite(residual):
            raise FloatingPointError("Non-finite integrated gradients")
        return scores.cpu().tolist(), {"completeness_residual": float(residual),
                                      "log_intensity_delta": float(actual - baseline),
                                      "baseline_log_intensity": float(baseline),
                                      "actual_log_intensity": float(actual)}
