import numpy as np


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

    # Broadcast every beam at once; rows are timesteps and columns are beams.
    angles = np.arange(8, dtype=np.float64) * (2.0 * np.pi / 8.0)
    base_dist = 2.5 + 1.5 * np.cos(angles[None, :] - 2.0 * t[:, None])
    lidar = np.clip(base_dist + rng.normal(0, 0.05, (seq_len, 8)), 0.2, 5.0)

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


def embed_sensor_stream(sensor_data, d_model=64, seed=42, as_numpy=False):
    """Embed and quantize the sensor stream.

    ``as_numpy=True`` avoids importing PyTorch in high-throughput vector tools;
    the default preserves the original tensor-returning public API.
    """
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

    # Q1.7 activation format: multiplication by 2**7 is the software form of
    # the RTL binary-point shift. floor(x + 0.5) matches round-half-up logic.
    scale = 2.0 ** -7
    int8_tokens = np.clip(np.floor(normed * (1 << 7) + 0.5), -128, 127).astype(np.int8)
    if as_numpy:
        return int8_tokens[None, ...], scale
    import torch

    return torch.from_numpy(int8_tokens).unsqueeze(0), scale


if __name__ == "__main__":
    data = generate_ares_trajectory(seq_len=16)
    tokens, scale = embed_sensor_stream(data, d_model=64)
    print("ARES Sensor Trajectory generated:")
    print("  Tokens shape:", tokens.shape, "range:", tokens.min().item(), "to", tokens.max().item())
