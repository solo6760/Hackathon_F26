"""Sensor-Fusion Token Generator (ARES Robotics Trajectory).

Generates realistic multi-modal sensor streams for robotics path-planning:
  - 3D Position (x, y, z)
  - Linear Velocity (vx, vy, vz)
  - IMU Orientation & Angular Velocities (roll, pitch, yaw, wx, wy, wz)
  - IMU Linear Accelerations (ax, ay, az)
  - Multi-directional Proximity / Range Sensors (8 lidar beams)
  - Target Path Waypoint Offsets (dx, dy, dz)

Projects physical sensor readings into D=64 embedding tokens across S=16 timesteps,
quantized to Signed INT8 [-128, 127] for consumption by the KERA accelerator.
"""

import math
import numpy as np
import torch


def generate_ares_trajectory(seq_len=16, dt=0.05, seed=42):
    """Simulates a smooth quadrotor / mobile robot trajectory following a curved path.
    
    Returns:
        sensor_data: dict of physical sensor measurements (S timesteps)
    """
    rng = np.random.RandomState(seed)
    t = np.arange(seq_len) * dt

    # 3D smooth path (figure-8 / spline trajectory)
    x = 2.0 * np.sin(1.5 * t)
    y = 2.0 * np.sin(3.0 * t)
    z = 1.0 + 0.5 * np.cos(1.0 * t)

    # Velocities (derivatives with minor sensor noise)
    vx = 3.0 * np.cos(1.5 * t) + rng.normal(0, 0.02, seq_len)
    vy = 6.0 * np.cos(3.0 * t) + rng.normal(0, 0.02, seq_len)
    vz = -0.5 * np.sin(1.0 * t) + rng.normal(0, 0.01, seq_len)

    # Accelerations (IMU accelerometer)
    ax = -4.5 * np.sin(1.5 * t) + rng.normal(0, 0.05, seq_len)
    ay = -18.0 * np.sin(3.0 * t) + rng.normal(0, 0.05, seq_len)
    az = -0.5 * np.cos(1.0 * t) + 9.81 + rng.normal(0, 0.05, seq_len)  # gravity + motion

    # Angular velocities (IMU gyroscope)
    wx = 0.5 * np.cos(2.0 * t) + rng.normal(0, 0.01, seq_len)
    wy = 0.5 * np.sin(2.0 * t) + rng.normal(0, 0.01, seq_len)
    wz = 1.0 * np.cos(1.5 * t) + rng.normal(0, 0.01, seq_len)

    # 8-beam range sensors (distance to virtual obstacle boundary, 0.2m to 5.0m)
    lidar = np.zeros((seq_len, 8))
    for b in range(8):
        angle = b * (2 * math.pi / 8)
        base_dist = 2.5 + 1.5 * np.cos(angle - t * 2)
        lidar[:, b] = np.clip(base_dist + rng.normal(0, 0.05, seq_len), 0.2, 5.0)

    # Target path deviation (delta to planned path)
    dx = 0.1 * np.sin(4.0 * t)
    dy = 0.1 * np.cos(4.0 * t)
    dz = 0.05 * np.sin(2.0 * t)

    return {
        "pos": np.stack([x, y, z], axis=-1),          # (S, 3)
        "vel": np.stack([vx, vy, vz], axis=-1),       # (S, 3)
        "acc": np.stack([ax, ay, az], axis=-1),       # (S, 3)
        "gyro": np.stack([wx, wy, wz], axis=-1),      # (S, 3)
        "lidar": lidar,                               # (S, 8)
        "target_err": np.stack([dx, dy, dz], axis=-1) # (S, 3)
    }


def embed_sensor_stream(sensor_data, d_model=64, seed=42):
    """Projects multi-modal sensor signals into D=64 embedding tokens.
    
    Concatenates 23 raw sensor channels:
      [pos(3), vel(3), acc(3), gyro(3), lidar(8), target_err(3)] = 23 channels
    and projects via a linear projection to d_model (64), then normalizes.
    
    Returns:
        int8_tokens: (1, S, D) torch.int8 tensor in [-128, 127]
        scale: float input quantization scale (1/128)
    """
    raw_channels = np.concatenate([
        sensor_data["pos"],
        sensor_data["vel"],
        sensor_data["acc"],
        sensor_data["gyro"],
        sensor_data["lidar"],
        sensor_data["target_err"]
    ], axis=-1)  # (S, 23)

    seq_len, in_channels = raw_channels.shape

    # Deterministic projection weights
    rng = np.random.RandomState(seed)
    proj_weight = rng.normal(0, 1.0 / np.sqrt(in_channels), (in_channels, d_model))

    # Linear projection
    embedded = np.matmul(raw_channels, proj_weight)  # (S, 64)

    # Normalize across feature dim (simulating LayerNorm / feature standardization)
    mean = np.mean(embedded, axis=-1, keepdims=True)
    std = np.std(embedded, axis=-1, keepdims=True) + 1e-5
    normed = (embedded - mean) / std  # std ~= 1.0, range roughly [-3, +3]

    # Quantize to INT8 with scale Sx = 1/128 (matches Brevitas QuantIdentity scale)
    scale = 1.0 / 128.0
    int8_tokens = np.clip(np.round(normed / scale), -128, 127).astype(np.int8)

    return torch.tensor(int8_tokens, dtype=torch.int8).unsqueeze(0), scale


if __name__ == "__main__":
    data = generate_ares_trajectory(seq_len=16)
    tokens, scale = embed_sensor_stream(data, d_model=64)
    print("ARES Sensor Trajectory generated:")
    print("  Sequence Length (S):", tokens.shape[1])
    print("  Embedding Dim   (D):", tokens.shape[2])
    print("  Token Range        :", tokens.min().item(), "to", tokens.max().item())
    print("  Sample Token[0,:8] :", tokens[0, 0, :8].tolist())

