from __future__ import annotations

import csv
import io
import json
import math
import random
from datetime import timedelta
from statistics import mean

from app.models.enums import FaultLabel
from app.schemas.simulator import (
    FAULT_PROFILE_TO_LABEL,
    ActuatorSimulationConfig,
    SimulationFaultProfile,
    SimulationFaultProfileInfo,
    SimulationGenerateResponse,
    SimulationMetadata,
)
from app.schemas.telemetry import TelemetrySampleCreate


FAULT_PROFILE_INFO: list[SimulationFaultProfileInfo] = [
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.HEALTHY,
        label="Healthy actuator",
        description="Nominal response with small sensor noise and stable current draw.",
        expected_pattern="Low position error, stable current, normal temperature, low latency.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.FRICTION_INCREASE,
        label="Friction increase",
        description="Mechanical resistance increases, causing lag, current rise, and heating.",
        expected_pattern="Growing position error, elevated current, mild thermal rise.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.BACKLASH,
        label="Backlash",
        description="Mechanical looseness creates deadband and delayed sign reversals.",
        expected_pattern="Flat spots around reversals, abrupt catch-up motion, encoder mismatch.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.ENCODER_NOISE,
        label="Encoder noise",
        description="Sensor reading becomes inconsistent while the physical actuator remains mostly normal.",
        expected_pattern="Encoder position jitter, actual-position mismatch, noisy calculated errors.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.MOTOR_WEAKENING,
        label="Motor weakening",
        description="Actuator cannot track demanded motion under load as strongly as before.",
        expected_pattern="Reduced actual velocity, lag during peaks, higher current for less motion.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.OVERHEATING,
        label="Overheating",
        description="Temperature rises progressively across the run.",
        expected_pattern="Strong upward temperature trend with increasing current draw.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.DELAYED_RESPONSE,
        label="Delayed response",
        description="Control response is shifted in time relative to the command.",
        expected_pattern="Command/actual phase shift, elevated control latency, persistent lag.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.LOAD_IMBALANCE,
        label="Load imbalance",
        description="Uneven load changes tracking error and current cyclically.",
        expected_pattern="Periodic current/load swings and asymmetric position error.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY,
        label="Oscillation / control instability",
        description="Control loop overshoots and oscillates around the command.",
        expected_pattern="Ringing, overshoot, alternating error signs, noisy velocity response.",
    ),
    SimulationFaultProfileInfo(
        key=SimulationFaultProfile.CURRENT_SPIKE_ANOMALY,
        label="Current spike anomaly",
        description="Short current spikes appear without proportional command demand.",
        expected_pattern="Sparse high-current spikes with mild heat bumps.",
    ),
]

CSV_COLUMNS = [
    "timestamp",
    "commanded_position",
    "actual_position",
    "commanded_velocity",
    "actual_velocity",
    "commanded_torque",
    "estimated_torque",
    "motor_current",
    "temperature",
    "load_estimate",
    "control_latency_ms",
    "encoder_position",
    "error_position",
    "error_velocity",
    "fault_label",
]


class ActuatorTelemetrySimulator:
    def generate(self, config: ActuatorSimulationConfig) -> SimulationGenerateResponse:
        rng = random.Random(config.seed)
        dt = 1.0 / config.sample_rate_hz
        samples: list[TelemetrySampleCreate] = []

        actual_position = 0.0
        previous_actual = 0.0
        previous_direction = 0
        reversal_deadband_remaining = 0.0
        command_history: list[float] = []
        spike_indexes = self._choose_spike_indexes(config, rng)

        for index in range(config.sample_count):
            t = index * dt
            phase = 2.0 * math.pi * config.command_frequency_hz * t
            commanded_position = config.commanded_amplitude * math.sin(phase)
            commanded_velocity = (
                2.0 * math.pi * config.command_frequency_hz * config.commanded_amplitude * math.cos(phase)
            )
            command_history.append(commanded_position)

            target_position = commanded_position
            latency_ms = config.base_latency_ms
            load_estimate = config.nominal_load
            current_multiplier = 1.0
            temp_extra = 0.0
            fault = config.fault_profile
            intensity = config.fault_intensity

            if fault == SimulationFaultProfile.DELAYED_RESPONSE:
                delay_samples = max(1, int(round((0.08 + intensity * 0.42) / dt)))
                if len(command_history) > delay_samples:
                    target_position = command_history[-delay_samples]
                latency_ms += 40.0 + intensity * 220.0
                current_multiplier += 0.08 * intensity

            elif fault == SimulationFaultProfile.FRICTION_INCREASE:
                friction = intensity * (0.35 + 0.25 * (index / max(config.sample_count - 1, 1)))
                target_position *= 1.0 - friction * 0.22
                latency_ms += 12.0 + friction * 80.0
                current_multiplier += 0.35 + friction * 1.1
                temp_extra += 7.0 * friction * (index / max(config.sample_count - 1, 1))

            elif fault == SimulationFaultProfile.MOTOR_WEAKENING:
                weakening = 0.16 + intensity * 0.35
                target_position *= 1.0 - weakening * min(1.0, abs(commanded_velocity) / 70.0)
                latency_ms += 35.0 * intensity
                current_multiplier += 0.45 * intensity
                load_estimate += 0.25 * intensity

            elif fault == SimulationFaultProfile.LOAD_IMBALANCE:
                load_wave = math.sin(2.0 * math.pi * config.command_frequency_hz * 0.5 * t + 0.6)
                load_estimate += intensity * 0.45 * (1.0 + load_wave)
                target_position -= load_wave * intensity * config.commanded_amplitude * 0.10
                current_multiplier += 0.22 + abs(load_wave) * intensity * 0.9
                latency_ms += abs(load_wave) * 55.0 * intensity

            response_constant = config.response_time_constant_s
            if fault in {
                SimulationFaultProfile.FRICTION_INCREASE,
                SimulationFaultProfile.DELAYED_RESPONSE,
                SimulationFaultProfile.MOTOR_WEAKENING,
            }:
                response_constant *= 1.0 + 2.0 * intensity

            alpha = min(1.0, dt / max(response_constant, 1e-6))
            actual_position = actual_position + alpha * (target_position - actual_position)

            if fault == SimulationFaultProfile.BACKLASH:
                direction = 1 if commanded_velocity >= 0 else -1
                if direction != previous_direction and previous_direction != 0:
                    reversal_deadband_remaining = 0.8 + intensity * 4.8

                delta = actual_position - previous_actual
                if reversal_deadband_remaining > 0:
                    consumed = min(abs(delta), reversal_deadband_remaining)
                    reversal_deadband_remaining -= consumed
                    actual_position = previous_actual + math.copysign(max(abs(delta) - consumed, 0.0), delta)
                    latency_ms += 20.0 + intensity * 90.0

                previous_direction = direction
                current_multiplier += 0.14 * intensity

            if fault == SimulationFaultProfile.OSCILLATION_CONTROL_INSTABILITY:
                oscillation = (
                    math.sin(2.0 * math.pi * (config.command_frequency_hz * 5.0 + 1.5) * t)
                    * config.commanded_amplitude
                    * (0.025 + intensity * 0.12)
                )
                actual_position += oscillation
                current_multiplier += 0.18 + abs(oscillation) * 0.025
                latency_ms += 10.0 * intensity

            actual_position += rng.gauss(0.0, config.sensor_noise_std)
            actual_velocity = 0.0 if index == 0 else (actual_position - previous_actual) / dt

            commanded_torque = 0.04 * abs(commanded_velocity) + load_estimate * 0.8
            estimated_torque = commanded_torque * (0.95 + rng.gauss(0.0, 0.015))
            motor_current = (
                config.nominal_current_a * current_multiplier
                + 0.015 * abs(commanded_velocity)
                + rng.gauss(0.0, config.current_noise_std)
            )
            motor_current = max(0.0, motor_current)

            if fault == SimulationFaultProfile.CURRENT_SPIKE_ANOMALY and index in spike_indexes:
                motor_current += config.nominal_current_a * (2.5 + 5.0 * intensity)
                temp_extra += 0.4 + 1.5 * intensity

            run_progress = index / max(config.sample_count - 1, 1)
            temperature = (
                config.nominal_temperature_c
                + temp_extra
                + 0.018 * abs(actual_velocity)
                + 0.25 * motor_current
                + rng.gauss(0.0, config.temperature_noise_std)
            )

            if fault == SimulationFaultProfile.OVERHEATING:
                temperature += (18.0 + 42.0 * intensity) * run_progress
                motor_current += 0.25 * intensity * run_progress
                latency_ms += 18.0 * intensity * run_progress

            encoder_noise = config.sensor_noise_std * 0.6
            if fault == SimulationFaultProfile.ENCODER_NOISE:
                encoder_noise += 0.4 + intensity * 3.0
                latency_ms += 3.0 * intensity
            encoder_position = actual_position + rng.gauss(0.0, encoder_noise)

            if fault == SimulationFaultProfile.CURRENT_SPIKE_ANOMALY:
                fault_label = FaultLabel.CURRENT_SPIKE if index in spike_indexes else FaultLabel.NONE
            else:
                fault_label = FAULT_PROFILE_TO_LABEL[fault]

            sample = TelemetrySampleCreate(
                timestamp=config.start_time + timedelta(seconds=t),
                commanded_position=round(commanded_position, 6),
                actual_position=round(actual_position, 6),
                commanded_velocity=round(commanded_velocity, 6),
                actual_velocity=round(actual_velocity, 6),
                commanded_torque=round(commanded_torque, 6),
                estimated_torque=round(estimated_torque, 6),
                motor_current=round(motor_current, 6),
                temperature=round(temperature, 6),
                load_estimate=round(load_estimate, 6),
                control_latency_ms=round(max(0.0, latency_ms + rng.gauss(0.0, 1.5)), 6),
                encoder_position=round(encoder_position, 6),
                error_position=round(commanded_position - actual_position, 6),
                error_velocity=round(commanded_velocity - actual_velocity, 6),
                fault_label=fault_label,
            )
            samples.append(sample)
            previous_actual = actual_position

        metadata = SimulationMetadata(
            fault_profile=config.fault_profile,
            fault_label=FAULT_PROFILE_TO_LABEL[config.fault_profile],
            seed=config.seed,
            sample_rate_hz=config.sample_rate_hz,
            duration_s=config.duration_s,
            sample_count=len(samples),
        )
        return SimulationGenerateResponse(metadata=metadata, samples=samples)

    def export_csv(self, response: SimulationGenerateResponse) -> bytes:
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for sample in response.samples:
            row = sample.model_dump(mode="json")
            writer.writerow({key: row.get(key) for key in CSV_COLUMNS})
        return output.getvalue().encode("utf-8")

    def export_json(self, response: SimulationGenerateResponse) -> bytes:
        return json.dumps(response.model_dump(mode="json"), indent=2).encode("utf-8")

    def summarize(self, samples: list[TelemetrySampleCreate]) -> dict:
        if not samples:
            return {}
        errors = [abs(sample.error_position or 0.0) for sample in samples]
        currents = [sample.motor_current or 0.0 for sample in samples]
        temps = [sample.temperature or 0.0 for sample in samples]
        latencies = [sample.control_latency_ms or 0.0 for sample in samples]
        return {
            "mean_abs_position_error": round(mean(errors), 6),
            "max_abs_position_error": round(max(errors), 6),
            "mean_current_a": round(mean(currents), 6),
            "max_current_a": round(max(currents), 6),
            "start_temperature_c": round(temps[0], 6),
            "end_temperature_c": round(temps[-1], 6),
            "mean_latency_ms": round(mean(latencies), 6),
            "max_latency_ms": round(max(latencies), 6),
        }

    def _choose_spike_indexes(self, config: ActuatorSimulationConfig, rng: random.Random) -> set[int]:
        if config.fault_profile != SimulationFaultProfile.CURRENT_SPIKE_ANOMALY:
            return set()
        sample_count = config.sample_count
        spike_count = max(1, int(sample_count * (0.005 + config.fault_intensity * 0.015)))
        start = max(1, int(sample_count * 0.05))
        population = list(range(start, sample_count))
        return set(rng.sample(population, min(spike_count, len(population))))


simulator = ActuatorTelemetrySimulator()
