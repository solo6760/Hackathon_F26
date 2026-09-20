"""ARES sensor-fusion training and INT4 quantization pipeline."""


import math
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

try:
    from .sensor_fusion import generate_ares_trajectory, embed_sensor_stream
except ImportError:
    from sensor_fusion import generate_ares_trajectory, embed_sensor_stream

ACT_SCALE_LOG2 = -5
GELU_SCALE_LOG2 = -5


class AresSensorDataset(Dataset):
    def __init__(self, num_trajectories=128, seq_len=64, d_model=64,
                 base_seed=100, embedding_seed=42):
        samples = []
        targets = []
        for i in range(num_trajectories):
            data = generate_ares_trajectory(seq_len=seq_len, seed=base_seed + i)
            # One fixed projection defines the model's input feature space.
            # Varying it per trajectory makes identical physical channels mean
            # something different in every sample and prevents generalization.
            tokens_int8, _ = embed_sensor_stream(
                data, d_model=d_model, seed=embedding_seed, as_numpy=True
            )
            # Normalize tokens to float [-1.0, 1.0]
            samples.append(torch.from_numpy(tokens_int8[0]).float().mul_(2.0 ** ACT_SCALE_LOG2))
            targets.append(torch.from_numpy(data["target_future"]).float())
        # Contiguous tensors make DataLoader collation a slice/copy instead of
        # recursively stacking hundreds of small Python objects every epoch.
        self.samples = torch.stack(samples)
        self.targets = torch.stack(targets)

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
    """Symmetric INT4 quantization with a shift-exact power-of-two scale."""
    max_val = torch.max(torch.abs(weight_tensor)).item()
    scale_log2 = math.ceil(math.log2(max_val / 7.0)) if max_val else 0
    scale = 2.0 ** scale_log2
    q_tensor = torch.clamp(torch.floor(weight_tensor / scale + 0.5), -8, 7).to(torch.int8)
    return q_tensor, scale


def _requant_shift(weight_scale, input_log2, output_log2):
    """Return shift for accum * 2**(input+w_scale-output)."""
    weight_log2 = int(round(math.log2(weight_scale)))
    return output_log2 - input_log2 - weight_log2


def train_kera_model(epochs=30, seq_len=64, d_model=64, n_heads=1, d_mlp=128,
                     checkpoint_path="testing_py/kera_sensor_fusion_trained.pt", seed=42):
    print(f"Initializing ARES Sensor Fusion Transformer Training:")
    print(f"  Sequence Length (Tokens) : {seq_len} (Proposal spec: 64-128)")
    print(f"  Attention Heads (H)      : {n_heads} (Single-head baseline)")
    print(f"  Head Dimension           : {d_model // n_heads}")
    print(f"  FFN Hidden Dimension     : {d_mlp}")

    # Dataset: 256 trajectories
    torch.manual_seed(seed)
    np.random.seed(seed)
    dataset = AresSensorDataset(
        num_trajectories=256, seq_len=seq_len, d_model=d_model,
        base_seed=42, embedding_seed=seed,
    )
    loader_rng = torch.Generator().manual_seed(seed)
    train_loader = DataLoader(dataset, batch_size=32, shuffle=True, generator=loader_rng)

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
    val_data = AresSensorDataset(
        num_trajectories=32, seq_len=seq_len, d_model=d_model,
        base_seed=999, embedding_seed=seed,
    )
    val_loader = DataLoader(val_data, batch_size=32, shuffle=False)
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

    # Every scale is a power of two, so these are pure arithmetic shifts in RTL.
    requant_shifts = {
        name: _requant_shift(scale, ACT_SCALE_LOG2, ACT_SCALE_LOG2)
        for name, scale in scales.items() if name in {"w_q", "w_k", "w_v", "w_out"}
    }
    requant_shifts["w_ffn1"] = _requant_shift(
        scales["w_ffn1"], ACT_SCALE_LOG2, GELU_SCALE_LOG2
    )
    requant_shifts["w_ffn2"] = _requant_shift(
        scales["w_ffn2"], GELU_SCALE_LOG2, ACT_SCALE_LOG2
    )

    # Save Checkpoint
    checkpoint_path = Path(checkpoint_path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "model_state_dict": model.state_dict(),
        "quantized_weights": quant_dict,
        "scales": scales,
        "requant_shifts": requant_shifts,
        "activation_scale": 2.0 ** ACT_SCALE_LOG2,
        "gelu_scale": 2.0 ** GELU_SCALE_LOG2,
        "embedding_seed": seed,
        "config": {
            "seq_len": seq_len,
            "d_model": d_model,
            "n_heads": n_heads,
            "d_mlp": d_mlp
        },
        "val_mse": val_mse,
    }
    torch.save(checkpoint, checkpoint_path)

    # End-to-end post-training quantization check. The prediction head remains
    # FP32 because it is outside the accelerated attention/FFN block.
    try:
        from .pytorch_model import SmallTransformerBlockRTL
    except ImportError:
        from pytorch_model import SmallTransformerBlockRTL
    rtl_model = SmallTransformerBlockRTL(d_model=d_model, n_heads=n_heads, d_mlp=d_mlp)
    rtl_model.load_trained_checkpoint(checkpoint_path)
    quant_val_loss = 0.0
    with torch.inference_mode():
        for samples, targets in val_loader:
            samples_int8 = torch.clamp(
                torch.floor(samples / checkpoint["activation_scale"] + 0.5), -128, 127
            ).to(torch.int8)
            fused = rtl_model.forward_rtl(samples_int8).float() * checkpoint["activation_scale"]
            prediction = model.pred_head(fused)
            quant_val_loss += criterion(prediction, targets).item() * len(samples)
    quant_val_mse = quant_val_loss / len(val_data)
    checkpoint["quant_val_mse"] = quant_val_mse
    torch.save(checkpoint, checkpoint_path)
    print(f"Validation MSE (INT8/INT4 block): {quant_val_mse:.6f}")
    # Lightweight deployment artifact: avoids importing PyTorch merely to
    # generate BRAM vectors. PyTorch [out, in] weights are transposed here to
    # the datapath's [K, N] convention.
    deployment_path = checkpoint_path.with_suffix(".npz")
    np.savez_compressed(
        deployment_path,
        w_q=quant_dict["w_q"].numpy().T,
        w_k=quant_dict["w_k"].numpy().T,
        w_v=quant_dict["w_v"].numpy().T,
        projection_shifts=np.array([
            requant_shifts["w_q"], requant_shifts["w_k"], requant_shifts["w_v"]
        ], dtype=np.int8),
        d_model=np.int32(d_model),
        n_heads=np.int32(n_heads),
        seq_len=np.int32(seq_len),
    )
    print(f"Saved trained checkpoint to: {checkpoint_path}")
    print(f"Saved deployment weights to: {deployment_path}")
    return model, quant_dict, scales


if __name__ == "__main__":
    train_kera_model(epochs=30, seq_len=64, d_model=64, n_heads=1, d_mlp=128)
