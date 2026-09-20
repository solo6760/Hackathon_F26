"""ARES sensor-fusion training and INT4 quantization pipeline."""


import os
import math
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

from sensor_fusion import generate_ares_trajectory, embed_sensor_stream


class AresSensorDataset(Dataset):
    def __init__(self, num_trajectories=128, seq_len=64, d_model=64, base_seed=100):
        self.samples = []
        self.targets = []
        for i in range(num_trajectories):
            data = generate_ares_trajectory(seq_len=seq_len, seed=base_seed + i)
            tokens_int8, _ = embed_sensor_stream(data, d_model=d_model, seed=base_seed + i)
            # Normalize tokens to float [-1.0, 1.0]
            tokens_fp = tokens_int8.squeeze(0).float() / 128.0
            target = torch.tensor(data["target_future"], dtype=torch.float32)  # (S, 3)
            self.samples.append(tokens_fp)
            self.targets.append(target)

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        return self.samples[idx], self.targets[idx]


class TrainableAresTransformer(nn.Module):
    def __init__(self, d_model=64, n_heads=1, d_mlp=128):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads

        # Projections (Linear without bias to match RTL MAC pipeline)
        self.q_proj = nn.Linear(d_model, d_model, bias=False)
        self.k_proj = nn.Linear(d_model, d_model, bias=False)
        self.v_proj = nn.Linear(d_model, d_model, bias=False)
        self.out_proj = nn.Linear(d_model, d_model, bias=False)

        # FFN
        self.ffn1 = nn.Linear(d_model, d_mlp, bias=False)
        self.gelu = nn.GELU()
        self.ffn2 = nn.Linear(d_mlp, d_model, bias=False)

        # Waypoint trajectory prediction head: D=64 -> 3D delta (dx, dy, dz)
        self.pred_head = nn.Linear(d_model, 3, bias=True)

    def forward(self, x):
        B, S, D = x.shape
        q = self.q_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        k = self.k_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)
        v = self.v_proj(x).view(B, S, self.n_heads, self.head_dim).transpose(1, 2)

        scores = torch.matmul(q, k.transpose(-2, -1)) / math.sqrt(self.head_dim)
        probs = torch.softmax(scores, dim=-1)
        context = torch.matmul(probs, v).transpose(1, 2).contiguous().view(B, S, D)

        attn_out = self.out_proj(context)
        x_post_attn = x + attn_out

        ffn_out = self.ffn2(self.gelu(self.ffn1(x_post_attn)))
        fused = x_post_attn + ffn_out

        # Future waypoint prediction
        pred = self.pred_head(fused)
        return pred, fused


def quantize_to_int4(weight_tensor):
    """Symmetric per-tensor INT4 quantization: returns INT8 tensor in [-8, 7] and scale."""
    max_val = torch.max(torch.abs(weight_tensor)).item()
    scale = max_val / 7.0 if max_val != 0 else 1.0
    q_tensor = torch.clamp(torch.round(weight_tensor / scale), -8, 7).to(torch.int8)
    return q_tensor, scale


def train_kera_model(epochs=35, seq_len=64, d_model=64, n_heads=1, d_mlp=128, checkpoint_path="testing_py/kera_sensor_fusion_trained.pt"):
    print(f"Initializing ARES Sensor Fusion Transformer Training:")
    print(f"  Sequence Length (Tokens) : {seq_len} (Proposal spec: 64-128)")
    print(f"  Attention Heads (H)      : {n_heads} (Single-head baseline)")
    print(f"  Head Dimension           : {d_model // n_heads}")
    print(f"  FFN Hidden Dimension     : {d_mlp}")

    # Dataset: 256 trajectories
    dataset = AresSensorDataset(num_trajectories=256, seq_len=seq_len, d_model=d_model, base_seed=42)
    train_loader = DataLoader(dataset, batch_size=16, shuffle=True)

    model = TrainableAresTransformer(d_model=d_model, n_heads=n_heads, d_mlp=d_mlp)
    optimizer = torch.optim.AdamW(model.parameters(), lr=8e-3, weight_decay=1e-4)
    criterion = nn.MSELoss()

    model.train()
    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        for samples, targets in train_loader:
            optimizer.zero_grad()
            pred, _ = model(samples)
            loss = criterion(pred, targets)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(samples)

        epoch_loss = total_loss / len(dataset)
        if epoch % 10 == 0 or epoch == epochs:
            print(f"  Epoch [{epoch:02d}/{epochs:02d}] - Trajectory MSE Loss: {epoch_loss:.6f}")

    # Validation evaluation on unseen trajectories
    model.eval()
    val_data = AresSensorDataset(num_trajectories=32, seq_len=seq_len, d_model=d_model, base_seed=999)
    val_loader = DataLoader(val_data, batch_size=16, shuffle=False)
    val_loss = 0.0
    with torch.no_grad():
        for samples, targets in val_loader:
            pred, _ = model(samples)
            val_loss += criterion(pred, targets).item() * len(samples)
    val_mse = val_loss / len(val_data)
    print(f"Validation MSE (FP32 baseline): {val_mse:.6f}")

    # Quantization of All Projection and FFN Weights to INT4
    quant_dict = {}
    scales = {}
    for name, weight in [
        ("w_q", model.q_proj.weight.data),
        ("w_k", model.k_proj.weight.data),
        ("w_v", model.v_proj.weight.data),
        ("w_out", model.out_proj.weight.data),
        ("w_ffn1", model.ffn1.weight.data),
        ("w_ffn2", model.ffn2.weight.data),
    ]:
        q_w, s_w = quantize_to_int4(weight)
        quant_dict[name] = q_w
        scales[name] = s_w
        # Evaluate quantization reconstruction error
        recon_err = torch.mean(torch.abs(weight - q_w.float() * s_w)).item()
        print(f"  Quantized {name:<6}: shape {list(q_w.shape)}, range [{q_w.min().item()}, {q_w.max().item()}], scale {s_w:.6f}, recon MAE {recon_err:.6f}")

    # Save Checkpoint
    os.makedirs(os.path.dirname(checkpoint_path), exist_ok=True)
    torch.save({
        "model_state_dict": model.state_dict(),
        "quantized_weights": quant_dict,
        "scales": scales,
        "config": {
            "seq_len": seq_len,
            "d_model": d_model,
            "n_heads": n_heads,
            "d_mlp": d_mlp
        },
        "val_mse": val_mse
    }, checkpoint_path)
    print(f"Saved trained checkpoint to: {checkpoint_path}")
    return model, quant_dict, scales


if __name__ == "__main__":
    train_kera_model(epochs=30, seq_len=64, d_model=64, n_heads=1, d_mlp=128)
