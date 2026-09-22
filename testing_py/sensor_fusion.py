import numpy as np


def generate_ares_trajectory(seq_len=64, dt=0.05, seed=42):
    rng = np.random.RandomState(seed)
    t = np.arange(seq_len + 1) * dt

    # 3D smooth path trajectory
    x = 2.0 * np.sin(1.5 * t)
    y = 2.0 * np.sin(3.0 * t)
    z = 1.0 + 0.5 * np.cos(1.0 * t)

    vx = 3.0 * np.cos(1.5 * t) + rng.normal(0, 0.02, seq_len + 1)
    vy = 6.0 * np.cos(3.0 * t) + rng.normal(0, 0.02, seq_len + 1)
    vz = -0.5 * np.sin(1.0 * t) + rng.normal(0, 0.01, seq_len + 1)

    ax = -4.5 * np.sin(1.5 * t) + rng.normal(0, 0.05, seq_len + 1)
    ay = -18.0 * np.sin(3.0 * t) + rng.normal(0, 0.05, seq_len + 1)
    az = -0.5 * np.cos(1.0 * t) + 9.81 + rng.normal(0, 0.05, seq_len + 1)

    wx = 0.5 * np.cos(2.0 * t) + rng.normal(0, 0.01, seq_len + 1)
    wy = 0.5 * np.sin(2.0 * t) + rng.normal(0, 0.01, seq_len + 1)
    wz = 1.0 * np.cos(1.5 * t) + rng.normal(0, 0.01, seq_len + 1)

    angles = np.arange(8, dtype=np.float64) * (2.0 * np.pi / 8.0)
    base_dist = 2.5 + 1.5 * np.cos(angles[None, :] - 2.0 * t[:seq_len, None])
    lidar = np.clip(base_dist + rng.normal(0, 0.05, (seq_len, 8)), 0.2, 5.0)

    dx = 0.1 * np.sin(4.0 * t[:seq_len])
    dy = 0.1 * np.cos(4.0 * t[:seq_len])
    dz = 0.05 * np.sin(2.0 * t[:seq_len])

    # Target future waypoint displacement (next step prediction target)
    target_disp = np.stack([x[1:] - x[:-1], y[1:] - y[:-1], z[1:] - z[:-1]], axis=-1)

    return {
        "pos": np.stack([x[:seq_len], y[:seq_len], z[:seq_len]], axis=-1),
        "vel": np.stack([vx[:seq_len], vy[:seq_len], vz[:seq_len]], axis=-1),
        "acc": np.stack([ax[:seq_len], ay[:seq_len], az[:seq_len]], axis=-1),
        "gyro": np.stack([wx[:seq_len], wy[:seq_len], wz[:seq_len]], axis=-1),
        "lidar": lidar,
        "target_err": np.stack([dx, dy, dz], axis=-1),
        "target_future": target_disp[:seq_len]  # (S, 3) next waypoint delta
    }


def embed_sensor_stream(sensor_data, d_model=64, seed=42, as_numpy=False):
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

    # Q3.5 covers layer-normalized values up to almost +/-4 without the heavy
    # clipping caused by Q1.7. The power-of-two scale is a five-bit RTL shift.
    scale = 2.0 ** -5
    int8_tokens = np.clip(np.floor(normed * (1 << 5) + 0.5), -128, 127).astype(np.int8)
    if as_numpy:
        return int8_tokens[None, ...], scale
    import torch

    return torch.from_numpy(int8_tokens).unsqueeze(0), scale


if __name__ == "__main__":
    data = generate_ares_trajectory(seq_len=64)
    tokens, scale = embed_sensor_stream(data, d_model=64)
    print("ARES Sensor Trajectory generated:")
    print("  Tokens shape:", tokens.shape, "range:", tokens.min().item(), "to", tokens.max().item())
