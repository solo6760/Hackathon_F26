import math
import numpy as np
import torch


def generate_ares_trajectory(seq_len=16, dt=0.05, seed=42):
    rng = np.random.RandomState(seed)
    t = np.arange(seq_len) * dt

    x = 2.0 * np.sin(1.5 * t)
    y = 2.0 * np.sin(3.0 * t)
    z = 1.0 + 0.5 * np.cos(1.0 * t)

    vx = 3.0 * np.cos(1.5 * t) + rng.normal(0, 0.02, seq_len)
    vy = 6.0 * np.cos(3.0 * t) + rng.normal(0, 0.02, seq_len)
    vz = -0.5 * np.sin(1.0 * t) + rng.normal(0, 0.01, seq_len)

    ax = -4.5 * np.sin(1.5 * t) + rng.normal(0, 0.05, seq_len)
    ay = -18.0 * np.sin(3.0 * t) + rng.normal(0, 0.05, seq_len)
    az = -0.5 * np.cos(1.0 * t) + 9.81 + rng.normal(0, 0.05, seq_len)

    wx = 0.5 * np.cos(2.0 * t) + rng.normal(0, 0.01, seq_len)
    wy = 0.5 * np.sin(2.0 * t) + rng.normal(0, 0.01, seq_len)
    wz = 1.0 * np.cos(1.5 * t) + rng.normal(0, 0.01, seq_len)

    lidar = np.zeros((seq_len, 8))
    for b in range(8):
        angle = b * (2 * math.pi / 8)
        base_dist = 2.5 + 1.5 * np.cos(angle - t * 2)
        lidar[:, b] = np.clip(base_dist + rng.normal(0, 0.05, seq_len), 0.2, 5.0)

    dx = 0.1 * np.sin(4.0 * t)
    dy = 0.1 * np.cos(4.0 * t)
    dz = 0.05 * np.sin(2.0 * t)

    return {
        "pos": np.stack([x, y, z], axis=-1),
        "vel": np.stack([vx, vy, vz], axis=-1),
        "acc": np.stack([ax, ay, az], axis=-1),
        "gyro": np.stack([wx, wy, wz], axis=-1),
        "lidar": lidar,
        "target_err": np.stack([dx, dy, dz], axis=-1)
    }


def embed_sensor_stream(sensor_data, d_model=64, seed=42):
    raw_channels = np.concatenate([
        sensor_data["pos"],
        sensor_data["vel"],
        sensor_data["acc"],
        sensor_data["gyro"],
        sensor_data["lidar"],
        sensor_data["target_err"]
    ], axis=-1)

    seq_len, in_channels = raw_channels.shape
    rng = np.random.RandomState(seed)
    proj_weight = rng.normal(0, 1.0 / np.sqrt(in_channels), (in_channels, d_model))

    embedded = np.matmul(raw_channels, proj_weight)
    mean = np.mean(embedded, axis=-1, keepdims=True)
    std = np.std(embedded, axis=-1, keepdims=True) + 1e-5
    normed = (embedded - mean) / std

    scale = 1.0 / 128.0
    int8_tokens = np.clip(np.round(normed / scale), -128, 127).astype(np.int8)
    return torch.tensor(int8_tokens, dtype=torch.int8).unsqueeze(0), scale


if __name__ == "__main__":
    data = generate_ares_trajectory(seq_len=16)
    tokens, scale = embed_sensor_stream(data, d_model=64)
    print("ARES Sensor Trajectory generated:")
    print("  Tokens shape:", tokens.shape, "range:", tokens.min().item(), "to", tokens.max().item())
