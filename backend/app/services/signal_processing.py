from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from statistics import mean, median, pvariance
from typing import Any, Iterable, Sequence

from app.schemas.features import FeatureVector

ALGORITHM_VERSION = "sp-1.0.0"


@dataclass(frozen=True)
class NumericSeries:
    times_s: list[float]
    commanded_position: list[float | None]
    actual_position: list[float | None]
    commanded_velocity: list[float | None]
    actual_velocity: list[float | None]
    motor_current: list[float | None]
    temperature: list[float | None]
    latency_ms: list[float | None]
    error_position: list[float | None]
    error_velocity: list[float | None]


class SignalProcessingError(ValueError):
    pass


class SignalProcessor:
    """Converts raw actuator telemetry into deterministic robotics diagnostic features."""

    def extract_features(self, samples: Sequence[Any], smoothing_window: int = 5) -> FeatureVector:
        if smoothing_window < 1:
            raise SignalProcessingError("smoothing_window must be at least 1")
        if smoothing_window > 301:
            raise SignalProcessingError("smoothing_window cannot exceed 301")

        series = self._to_series(samples)
        if not series.times_s:
            raise SignalProcessingError("Feature extraction requires at least one telemetry sample")

        position_error = self._position_error(series)
        velocity_error = self._velocity_error(series)

        abs_position_error = [abs(value) for value in position_error]
        abs_velocity_error = [abs(value) for value in velocity_error]

        current_values = self._compact(series.motor_current)
        temperature_values = self._compact(series.temperature)
        latency_values = self._compact(series.latency_ms)
        commanded_values = self._compact(series.commanded_position)
        actual_values = self._compact(series.actual_position)

        smoothed_actual = self.moving_average(actual_values, smoothing_window)
        noise_level = self._noise_level(actual_values, smoothed_actual)

        duration_ms = self._duration_ms(series.times_s)
        feature = FeatureVector(
            sample_count=len(series.times_s),
            duration_ms=duration_ms,
            mean_position_error=self._safe_mean(abs_position_error),
            max_position_error=max(abs_position_error, default=0.0),
            mean_velocity_error=self._safe_mean(abs_velocity_error),
            max_velocity_error=max(abs_velocity_error, default=0.0),
            response_delay_ms=self._response_delay_ms(series),
            overshoot_percent=self._overshoot_percent(series),
            settling_time_ms=self._settling_time_ms(series, position_error),
            steady_state_error=self._steady_state_error(position_error),
            current_drift_percent=self._drift_percent(current_values),
            temperature_rise_rate=self._linear_slope(series.times_s, series.temperature),
            error_variance=pvariance(position_error) if len(position_error) > 1 else 0.0,
            noise_level=noise_level,
            oscillation_score=self._oscillation_score(series.times_s, position_error, commanded_values),
            health_deviation_score=0.0,
            commanded_position_range=self._range(commanded_values),
            actual_position_range=self._range(actual_values),
            mean_motor_current=self._safe_mean(current_values),
            max_motor_current=max(current_values, default=0.0),
            mean_temperature=self._safe_mean(temperature_values),
            max_temperature=max(temperature_values, default=0.0),
            mean_latency_ms=self._safe_mean(latency_values),
            max_latency_ms=max(latency_values, default=0.0),
        )
        feature.health_deviation_score = self._heuristic_health_deviation(feature)
        return self._sanitize_feature_vector(feature)

    def moving_average(self, values: Sequence[float], window: int) -> list[float]:
        if not values:
            return []
        if window <= 1:
            return [float(value) for value in values]
        window = min(window, len(values))
        half = window // 2
        result: list[float] = []
        for index in range(len(values)):
            left = max(0, index - half)
            right = min(len(values), index + half + 1)
            result.append(self._safe_mean(values[left:right]))
        return result

    def _to_series(self, samples: Sequence[Any]) -> NumericSeries:
        sorted_samples = sorted(samples, key=lambda sample: self._timestamp(sample) or datetime.min)
        timestamps = [self._timestamp(sample) for sample in sorted_samples]
        times_s = self._relative_times_s(timestamps, len(sorted_samples))

        return NumericSeries(
            times_s=times_s,
            commanded_position=[self._number(self._attr(sample, "commanded_position")) for sample in sorted_samples],
            actual_position=[self._number(self._attr(sample, "actual_position")) for sample in sorted_samples],
            commanded_velocity=[self._number(self._attr(sample, "commanded_velocity")) for sample in sorted_samples],
            actual_velocity=[self._number(self._attr(sample, "actual_velocity")) for sample in sorted_samples],
            motor_current=[self._number(self._attr(sample, "motor_current")) for sample in sorted_samples],
            temperature=[self._number(self._attr(sample, "temperature")) for sample in sorted_samples],
            latency_ms=[self._number(self._attr(sample, "control_latency_ms")) for sample in sorted_samples],
            error_position=[self._number(self._attr(sample, "error_position")) for sample in sorted_samples],
            error_velocity=[self._number(self._attr(sample, "error_velocity")) for sample in sorted_samples],
        )

    def _position_error(self, series: NumericSeries) -> list[float]:
        values: list[float] = []
        for explicit, commanded, actual in zip(
            series.error_position,
            series.commanded_position,
            series.actual_position,
        ):
            if explicit is not None:
                values.append(explicit)
            elif commanded is not None and actual is not None:
                values.append(commanded - actual)
            else:
                values.append(0.0)
        return values

    def _velocity_error(self, series: NumericSeries) -> list[float]:
        values: list[float] = []
        for explicit, commanded, actual in zip(
            series.error_velocity,
            series.commanded_velocity,
            series.actual_velocity,
        ):
            if explicit is not None:
                values.append(explicit)
            elif commanded is not None and actual is not None:
                values.append(commanded - actual)
            else:
                values.append(0.0)
        return values

    def _response_delay_ms(self, series: NumericSeries) -> float:
        commanded_pairs = self._valid_xy(series.times_s, series.commanded_position)
        actual_pairs = self._valid_xy(series.times_s, series.actual_position)
        if len(commanded_pairs) < 8 or len(actual_pairs) < 8:
            return self._safe_mean(self._compact(series.latency_ms))

        commanded = [value for _, value in commanded_pairs]
        actual = [value for _, value in actual_pairs]
        sample_dt = self._median_dt(series.times_s)
        if sample_dt <= 0:
            return self._safe_mean(self._compact(series.latency_ms))

        max_lag = min(max(1, int(round(2.0 / sample_dt))), len(commanded) // 3, 250)
        if max_lag <= 0:
            return 0.0

        best_lag = 0
        best_score = -math.inf
        for lag in range(max_lag + 1):
            left = commanded[: len(commanded) - lag] if lag else commanded
            right = actual[lag:] if lag else actual
            score = self._correlation(left, right)
            if score > best_score:
                best_score = score
                best_lag = lag

        estimated = best_lag * sample_dt * 1000.0
        explicit_latency = self._safe_mean(self._compact(series.latency_ms))
        if explicit_latency > 0 and estimated <= 0:
            return explicit_latency
        return estimated

    def _overshoot_percent(self, series: NumericSeries) -> float:
        commanded = self._compact(series.commanded_position)
        actual = self._compact(series.actual_position)
        if not commanded or not actual:
            return 0.0

        command_peak = max(abs(value) for value in commanded)
        actual_peak = max(abs(value) for value in actual)
        if command_peak <= 1e-9:
            return 0.0
        return max(0.0, ((actual_peak - command_peak) / command_peak) * 100.0)

    def _settling_time_ms(self, series: NumericSeries, position_error: Sequence[float]) -> float:
        if len(position_error) < 3:
            return 0.0

        commanded = self._compact(series.commanded_position)
        command_range = max(self._range(commanded), 1.0)
        tolerance = max(command_range * 0.02, 0.05)
        required_tail = max(3, min(20, len(position_error) // 10))

        for index in range(len(position_error)):
            tail = position_error[index : index + required_tail]
            if len(tail) < required_tail:
                break
            if all(abs(value) <= tolerance for value in tail):
                return max(0.0, series.times_s[index] - series.times_s[0]) * 1000.0

        return self._duration_ms(series.times_s)

    def _steady_state_error(self, position_error: Sequence[float]) -> float:
        if not position_error:
            return 0.0
        start = max(0, int(len(position_error) * 0.9))
        tail = position_error[start:] or position_error
        return self._safe_mean(abs(value) for value in tail)

    def _drift_percent(self, values: Sequence[float]) -> float:
        if len(values) < 4:
            return 0.0
        window = max(2, len(values) // 5)
        first = self._safe_mean(values[:window])
        last = self._safe_mean(values[-window:])
        denominator = max(abs(first), 1e-9)
        return ((last - first) / denominator) * 100.0

    def _linear_slope(self, times_s: Sequence[float], maybe_values: Sequence[float | None]) -> float:
        pairs = self._valid_xy(times_s, maybe_values)
        if len(pairs) < 2:
            return 0.0
        xs = [x for x, _ in pairs]
        ys = [y for _, y in pairs]
        x_mean = mean(xs)
        y_mean = mean(ys)
        denominator = sum((x - x_mean) ** 2 for x in xs)
        if denominator <= 1e-12:
            return 0.0
        return sum((x - x_mean) * (y - y_mean) for x, y in pairs) / denominator

    def _noise_level(self, values: Sequence[float], smoothed: Sequence[float]) -> float:
        if not values or not smoothed or len(values) != len(smoothed):
            return 0.0
        residuals = [value - avg for value, avg in zip(values, smoothed)]
        if len(residuals) <= 1:
            return 0.0
        return math.sqrt(pvariance(residuals))

    def _oscillation_score(
        self,
        times_s: Sequence[float],
        position_error: Sequence[float],
        commanded_values: Sequence[float],
    ) -> float:
        if len(position_error) < 3:
            return 0.0

        signs = [1 if value > 0 else -1 if value < 0 else 0 for value in position_error]
        changes = 0
        previous = 0
        for sign in signs:
            if sign == 0:
                continue
            if previous and sign != previous:
                changes += 1
            previous = sign

        duration_s = max((times_s[-1] - times_s[0]) if len(times_s) > 1 else 0.0, 1e-9)
        crossings_per_s = changes / duration_s
        error_std = math.sqrt(pvariance(position_error)) if len(position_error) > 1 else 0.0
        scale = max(self._range(commanded_values), 1.0)
        return min(100.0, crossings_per_s * (error_std / scale) * 100.0)

    def _heuristic_health_deviation(self, feature: FeatureVector) -> float:
        command_scale = max(feature.commanded_position_range, 1.0)
        position_component = min(40.0, (feature.mean_position_error / command_scale) * 250.0)
        velocity_component = min(15.0, (feature.mean_velocity_error / max(command_scale, 1.0)) * 40.0)
        latency_component = min(15.0, feature.response_delay_ms / 20.0)
        current_component = min(12.0, abs(feature.current_drift_percent) / 4.0)
        thermal_component = min(10.0, max(0.0, feature.temperature_rise_rate) * 8.0)
        oscillation_component = min(8.0, feature.oscillation_score / 10.0)
        return min(100.0, position_component + velocity_component + latency_component + current_component + thermal_component + oscillation_component)

    def _sanitize_feature_vector(self, feature: FeatureVector) -> FeatureVector:
        data = feature.model_dump()
        for key, value in data.items():
            if isinstance(value, float) and not math.isfinite(value):
                data[key] = 0.0
        return FeatureVector(**data)

    def _relative_times_s(self, timestamps: Sequence[datetime | None], count: int) -> list[float]:
        if count == 0:
            return []
        if all(timestamp is not None for timestamp in timestamps):
            first = timestamps[0]
            assert first is not None
            return [max(0.0, (timestamp - first).total_seconds()) for timestamp in timestamps if timestamp is not None]
        return [float(index) for index in range(count)]

    def _timestamp(self, sample: Any) -> datetime | None:
        value = self._attr(sample, "timestamp")
        return value if isinstance(value, datetime) else None

    def _attr(self, sample: Any, name: str) -> Any:
        if isinstance(sample, dict):
            return sample.get(name)
        return getattr(sample, name, None)

    def _number(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return number

    def _compact(self, values: Iterable[float | None]) -> list[float]:
        return [float(value) for value in values if value is not None and math.isfinite(float(value))]

    def _valid_xy(self, xs: Sequence[float], ys: Sequence[float | None]) -> list[tuple[float, float]]:
        return [
            (float(x), float(y))
            for x, y in zip(xs, ys)
            if y is not None and math.isfinite(float(y)) and math.isfinite(float(x))
        ]

    def _safe_mean(self, values: Iterable[float]) -> float:
        compact = [float(value) for value in values if math.isfinite(float(value))]
        return mean(compact) if compact else 0.0

    def _range(self, values: Sequence[float]) -> float:
        if not values:
            return 0.0
        return max(values) - min(values)

    def _duration_ms(self, times_s: Sequence[float]) -> float:
        if len(times_s) < 2:
            return 0.0
        return max(0.0, times_s[-1] - times_s[0]) * 1000.0

    def _median_dt(self, times_s: Sequence[float]) -> float:
        if len(times_s) < 2:
            return 0.0
        deltas = [right - left for left, right in zip(times_s, times_s[1:]) if right > left]
        return median(deltas) if deltas else 0.0

    def _correlation(self, left: Sequence[float], right: Sequence[float]) -> float:
        size = min(len(left), len(right))
        if size < 3:
            return -math.inf
        x = list(left[:size])
        y = list(right[:size])
        mean_x = mean(x)
        mean_y = mean(y)
        numerator = sum((a - mean_x) * (b - mean_y) for a, b in zip(x, y))
        denom_x = math.sqrt(sum((a - mean_x) ** 2 for a in x))
        denom_y = math.sqrt(sum((b - mean_y) ** 2 for b in y))
        denominator = denom_x * denom_y
        if denominator <= 1e-12:
            return -math.inf
        return numerator / denominator
