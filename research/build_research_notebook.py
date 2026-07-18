"""Build Skarly's executable research notebook from original project analysis code."""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "research" / "Skarly_Audio_Intelligence_Research.ipynb"


def md(text: str):
    return nbf.v4.new_markdown_cell(text.strip())


def code(text: str):
    return nbf.v4.new_code_cell(text.strip())


def main() -> None:
    notebook = nbf.v4.new_notebook()
    notebook["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.11+"},
        "title": "Skarly Audio Intelligence Research",
    }
    notebook["cells"] = [
        md(
            """
# Skarly Audio Intelligence: Research Notebook

**Research-internship artifact | Reproducible signal analysis + model documentation**

This notebook explains the working Skarly pipeline from the audio waveform upward. It analyzes a user-supplied recording, derives interpretable audio features, documents the neural-network and CNN paths implemented in this repository, and plots the real training history stored in the reviewed checkpoint.

The analysis code in this notebook is authored for this project. It uses NumPy/SciPy operations directly for framing, STFT, mel filters, MFCCs, onset autocorrelation, chroma, and key scoring. It does not copy or modify the working vocal-to-music or music-to-music services.

**Reproducibility boundary:** audio is read from `SKARLY_AUDIO_PATH`; the source audio itself is not committed. Set the variable to any WAV/MP3/M4A/FLAC file you are permitted to analyze.
"""
        ),
        md(
            """
## 1. Experiment configuration

The notebook converts the source to a temporary mono 22.05 kHz WAV through FFmpeg, then performs read-only analysis. Generated charts are written to `research/artifacts/` for the illustrated report.
"""
        ),
        code(
            r"""
from pathlib import Path
import json, math, os, shutil, subprocess, sys, tempfile

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib import patches
from scipy import signal
from scipy.fft import dct
from scipy.io import wavfile
from scipy.ndimage import uniform_filter1d

plt.style.use("dark_background")
plt.rcParams.update({
    "figure.figsize": (12, 5.5),
    "figure.dpi": 120,
    "axes.facecolor": "#0c0d10",
    "figure.facecolor": "#08090b",
    "axes.edgecolor": "#777777",
    "axes.labelcolor": "#e8e8e8",
    "text.color": "#f5f5f5",
    "xtick.color": "#bcbcbc",
    "ytick.color": "#bcbcbc",
    "font.size": 10,
})

PROJECT_ROOT = Path.cwd().resolve()
if PROJECT_ROOT.name.lower() == "research":
    PROJECT_ROOT = PROJECT_ROOT.parent
ARTIFACT_DIR = PROJECT_ROOT / "research" / "artifacts"
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

audio_env = os.environ.get("SKARLY_AUDIO_PATH", "").strip()
AUDIO_PATH = Path(audio_env).expanduser() if audio_env else PROJECT_ROOT / "research" / "sample-audio.wav"
if not AUDIO_PATH.is_file():
    raise FileNotFoundError(
        f"Audio not found: {AUDIO_PATH}. Set SKARLY_AUDIO_PATH to a permitted audio file before running."
    )

ffmpeg_env = os.environ.get("SKARLY_FFMPEG_PATH", "").strip()
FFMPEG = ffmpeg_env or shutil.which("ffmpeg")
if not FFMPEG:
    raise FileNotFoundError("FFmpeg was not found. Install FFmpeg or set SKARLY_FFMPEG_PATH.")

ANALYSIS_WAV = Path(tempfile.gettempdir()) / "skarly_research_analysis_input.wav"
subprocess.run([
    str(FFMPEG), "-y", "-v", "error", "-i", str(AUDIO_PATH),
    "-ac", "1", "-ar", "22050", "-c:a", "pcm_s16le", str(ANALYSIS_WAV)
], check=True)

sample_rate, pcm = wavfile.read(ANALYSIS_WAV)
if pcm.ndim > 1:
    pcm = pcm.mean(axis=1)
if np.issubdtype(pcm.dtype, np.integer):
    scale = max(abs(np.iinfo(pcm.dtype).min), np.iinfo(pcm.dtype).max)
    audio = pcm.astype(np.float32) / float(scale)
else:
    audio = pcm.astype(np.float32)
audio = np.nan_to_num(audio)
duration_seconds = len(audio) / sample_rate

print(json.dumps({
    "source": AUDIO_PATH.name,
    "sample_rate_hz": sample_rate,
    "samples": len(audio),
    "duration_seconds": round(duration_seconds, 3),
    "analysis_only": True,
}, indent=2))
"""
        ),
        md(
            """
## 2. Waveform, level, and silence structure

RMS energy approximates perceived level over short windows. Zero-crossing rate (ZCR) is a compact indicator of noisiness and high-frequency activity. These are descriptive features, not identity or quality judgements.
"""
        ),
        code(
            r"""
frame_length = 2048
hop_length = 512
times = np.arange(len(audio)) / sample_rate

rms_dense = np.sqrt(uniform_filter1d(audio * audio, size=frame_length, mode="nearest") + 1e-12)
crossings_dense = np.abs(np.diff(np.signbit(audio).astype(np.int8), prepend=0))
zcr_dense = uniform_filter1d(crossings_dense.astype(np.float32), size=frame_length, mode="nearest")

peak = float(np.max(np.abs(audio)))
rms_global = float(np.sqrt(np.mean(audio * audio) + 1e-12))
crest_factor = peak / max(rms_global, 1e-9)
silence_ratio = float(np.mean(rms_dense < max(0.003, np.percentile(rms_dense, 15))))

overview = pd.DataFrame({
    "Metric": ["Duration", "Sample rate", "Peak amplitude", "Global RMS", "Crest factor", "Low-energy share"],
    "Value": [f"{duration_seconds:.2f} s", f"{sample_rate:,} Hz", f"{peak:.4f}", f"{rms_global:.4f}", f"{crest_factor:.2f}", f"{100*silence_ratio:.1f}%"],
})
display(overview)

stride = max(1, len(audio) // 7000)
fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
axes[0].plot(times[::stride], audio[::stride], color="#e1c47a", linewidth=0.55)
axes[0].set(title="Waveform", ylabel="Amplitude")
axes[1].plot(times[::stride], 20*np.log10(rms_dense[::stride] + 1e-6), color="#6ec5ff", linewidth=0.8)
axes[1].set(title="Short-time RMS envelope", ylabel="dBFS")
axes[2].plot(times[::stride], zcr_dense[::stride], color="#8ee0b7", linewidth=0.8)
axes[2].set(title="Zero-crossing activity", ylabel="Rate", xlabel="Time (seconds)")
for ax in axes: ax.grid(alpha=0.12)
fig.suptitle("Skarly input signal overview", fontsize=16, fontweight="bold")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "audio_overview.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 3. Time-frequency representation (STFT)

Skarly ultimately reasons about changing spectral patterns rather than only raw amplitude. The short-time Fourier transform (STFT) converts overlapping audio frames into a time-frequency surface. This is the basis for spectrograms, chroma, onset strength, and the legacy mel-CNN input.
"""
        ),
        code(
            r"""
frequencies, frame_times, stft = signal.stft(
    audio, fs=sample_rate, window="hann", nperseg=2048, noverlap=1536,
    boundary=None, padded=False
)
magnitude = np.abs(stft).astype(np.float32)
power = magnitude * magnitude
db = 20*np.log10(magnitude + 1e-6)

fig, ax = plt.subplots(figsize=(13, 6))
mesh = ax.pcolormesh(frame_times, frequencies, db, shading="auto", cmap="magma", vmin=np.percentile(db, 8), vmax=np.percentile(db, 99.5))
ax.set_ylim(40, min(10000, sample_rate/2))
ax.set_yscale("log")
ax.set(title="Log-frequency spectrogram", xlabel="Time (seconds)", ylabel="Frequency (Hz)")
fig.colorbar(mesh, ax=ax, label="Magnitude (dB)")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "spectrogram.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 4. Mel spectrogram and MFCCs for CNN-style learning

The mel scale compresses frequency resolution toward a perceptual spacing. A CNN can learn local shapes in the resulting image: harmonic stacks, consonant bursts, rhythm, formants, and timbral texture. MFCCs are a compact cosine transform of log-mel energy and remain useful for inspection even when the production model uses a learned pretrained encoder.
"""
        ),
        code(
            r"""
def hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)

def mel_to_hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)

def mel_filterbank(sample_rate, n_fft, n_mels=64, fmin=30.0, fmax=None):
    fmax = fmax or sample_rate / 2
    mel_points = np.linspace(hz_to_mel(fmin), hz_to_mel(fmax), n_mels + 2)
    hz_points = mel_to_hz(mel_points)
    bins = np.floor((n_fft + 1) * hz_points / sample_rate).astype(int)
    bins = np.clip(bins, 0, n_fft // 2)
    filters = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for index in range(1, n_mels + 1):
        left, center, right = bins[index-1:index+2]
        if center > left:
            filters[index-1, left:center] = (np.arange(left, center) - left) / (center - left)
        if right > center:
            filters[index-1, center:right] = (right - np.arange(center, right)) / (right - center)
    return filters

mel_filters = mel_filterbank(sample_rate, 2048, n_mels=64)
mel_power = mel_filters @ power
log_mel = 10*np.log10(mel_power + 1e-10)
mfcc = dct(log_mel, type=2, axis=0, norm="ortho")[:20]

fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
im0 = axes[0].imshow(log_mel, origin="lower", aspect="auto", extent=[frame_times[0], frame_times[-1], 0, 64], cmap="viridis")
axes[0].set(title="64-band log-mel spectrogram", ylabel="Mel band")
fig.colorbar(im0, ax=axes[0], label="dB")
im1 = axes[1].imshow(mfcc, origin="lower", aspect="auto", extent=[frame_times[0], frame_times[-1], 1, 20], cmap="coolwarm")
axes[1].set(title="First 20 MFCCs", xlabel="Time (seconds)", ylabel="Coefficient")
fig.colorbar(im1, ax=axes[1], label="Coefficient value")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "mel_mfcc.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 5. Rhythm, chroma, and an interpretable key estimate

Spectral flux highlights sudden increases in spectral energy and acts as a simple onset envelope. Autocorrelation over plausible beat periods gives a tempo hypothesis. Chroma folds spectral bins into 12 pitch classes; a deliberately transparent triad score then compares major and minor candidates. Production Skarly applies additional full-song logic and confidence gates, so this notebook estimate is explanatory rather than authoritative.
"""
        ),
        code(
            r"""
spectral_flux = np.maximum(0, np.diff(magnitude, axis=1, prepend=magnitude[:, :1])).sum(axis=0)
spectral_flux = spectral_flux / max(float(spectral_flux.max()), 1e-9)
frame_rate = sample_rate / 512.0
min_lag = max(1, int(frame_rate * 60 / 220))
max_lag = int(frame_rate * 60 / 40)
centered_flux = spectral_flux - spectral_flux.mean()
autocorrelation = signal.correlate(centered_flux, centered_flux, mode="full", method="fft")[len(centered_flux)-1:]
lag_window = autocorrelation[min_lag:max_lag+1]
best_lag = min_lag + int(np.argmax(lag_window))
tempo_bpm = 60 * frame_rate / best_lag

valid = frequencies > 27.5
midi = np.rint(69 + 12*np.log2(np.maximum(frequencies[valid], 1e-9)/440.0)).astype(int)
pitch_class = np.mod(midi, 12)
chroma = np.zeros((12, power.shape[1]), dtype=np.float32)
for pc in range(12):
    chroma[pc] = power[valid][pitch_class == pc].sum(axis=0)
chroma /= np.maximum(chroma.sum(axis=0, keepdims=True), 1e-9)
chroma_mean = chroma.mean(axis=1)

pitch_names = np.array(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"])
key_candidates = []
for tonic in range(12):
    major_score = chroma_mean[tonic] + 0.72*chroma_mean[(tonic+4)%12] + 0.62*chroma_mean[(tonic+7)%12]
    minor_score = chroma_mean[tonic] + 0.72*chroma_mean[(tonic+3)%12] + 0.62*chroma_mean[(tonic+7)%12]
    key_candidates += [(major_score, f"{pitch_names[tonic]} major"), (minor_score, f"{pitch_names[tonic]} minor")]
key_candidates.sort(reverse=True)

print(f"Notebook tempo hypothesis: {tempo_bpm:.1f} BPM")
print("Top transparent key hypotheses:", ", ".join(f"{name} ({score:.3f})" for score, name in key_candidates[:3]))

fig, axes = plt.subplots(2, 1, figsize=(13, 8))
axes[0].plot(frame_times, spectral_flux, color="#ffb347", linewidth=0.7)
axes[0].set(title=f"Spectral-flux onset envelope | autocorrelation tempo ≈ {tempo_bpm:.1f} BPM", xlabel="Time (seconds)", ylabel="Normalized flux")
im = axes[1].imshow(chroma, origin="lower", aspect="auto", extent=[frame_times[0], frame_times[-1], -0.5, 11.5], cmap="cividis")
axes[1].set(title=f"Pitch-class energy | strongest transparent key: {key_candidates[0][1]}", xlabel="Time (seconds)", ylabel="Pitch class", yticks=range(12), yticklabels=pitch_names)
fig.colorbar(im, ax=axes[1], label="Normalized energy")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "chroma_key.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 6. Models used by the working project

The repository has two distinct intelligence paths and keeps them separate from generation:

1. **Production-direction audio intelligence:** frozen ACE-Step 1.5 `AutoencoderOobleck` VAE encoder → 128-D pooled embedding → shared 256-D neural projection → independent calibrated heads for language, singing/speech, vocal technique, mood, genre, tempo family, melodic character, and out-of-distribution probability. The full recording is covered in contiguous 6-second windows and logits are averaged.
2. **Legacy/research mel-CNN:** 64-band log-mel input → Conv2D 24/48/96 channels → batch normalization, GELU and pooling → 96-D embedding → language and genre heads. The checkpoint remains available for comparison and backwards compatibility.
3. **Music generation:** ACE-Step 1.5 generates new instrumental arrangements. It is not the classifier.
4. **Source separation:** Demucs separates vocals/instrumental for full-song or music inputs.
5. **Melody/transcription:** Basic Pitch is preferred for MIDI; a librosa `pyin` contour is a guarded fallback.
6. **Transcription/language evidence:** Whisper contributes lyrics/language evidence when configured.
7. **Mixing and validation:** FFmpeg/Python mixing preserves the vocal, applies phrase-aware ducking, and validates duration, intelligibility, leakage, and diversity.
"""
        ),
        code(
            r"""
fig, ax = plt.subplots(figsize=(14, 7))
ax.set_xlim(0, 14); ax.set_ylim(0, 7); ax.axis("off")

def box(x, y, w, h, title, subtitle, color):
    ax.add_patch(patches.FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.03,rounding_size=0.12", facecolor=color, edgecolor="#e8e8e8", linewidth=1.1))
    ax.text(x+w/2, y+h*0.63, title, ha="center", va="center", fontsize=11, fontweight="bold", color="#ffffff")
    ax.text(x+w/2, y+h*0.30, subtitle, ha="center", va="center", fontsize=8.5, color="#d8d8d8", wrap=True)

def arrow(x1, y1, x2, y2):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle="->", color="#e1c47a", lw=1.7))

box(0.3, 4.7, 2.0, 1.25, "Audio input", "vocal / full song / music", "#24324a")
box(3.0, 5.2, 2.2, 1.25, "Demucs", "source separation when needed", "#3b2851")
box(3.0, 3.7, 2.2, 1.25, "Signal analysis", "tempo · key · phrases · MIDI", "#24483e")
box(6.0, 5.2, 2.4, 1.25, "Frozen VAE encoder", "6 s windows → 128-D", "#604526")
box(6.0, 3.7, 2.4, 1.25, "Multi-head NN", "256-D shared projection", "#704038")
box(9.2, 4.45, 2.1, 1.25, "Producer plans", "5 diverse prompt blueprints", "#3c4e66")
box(11.8, 4.45, 1.9, 1.25, "ACE-Step", "5 new backings", "#6b4f22")
box(9.2, 1.7, 2.1, 1.25, "Adaptive mixer", "preserved vocal + ducking", "#315844")
box(11.8, 1.7, 1.9, 1.25, "QA + export", "duration · leakage · stems", "#4d3559")

arrow(2.3, 5.3, 3.0, 5.8); arrow(2.3, 5.1, 3.0, 4.3)
arrow(5.2, 5.8, 6.0, 5.8); arrow(5.2, 4.3, 6.0, 4.3)
arrow(8.4, 5.8, 9.2, 5.3); arrow(8.4, 4.3, 9.2, 5.0)
arrow(11.3, 5.1, 11.8, 5.1); arrow(12.75, 4.45, 12.75, 2.95)
arrow(11.8, 2.3, 11.3, 2.3); arrow(10.25, 1.7, 10.25, 1.05)
ax.text(7, 6.7, "Skarly working architecture and protected generation boundary", ha="center", fontsize=16, fontweight="bold")
ax.text(7, 0.45, "Classifier heads guide routing; they do not synthesize or clone the singer.", ha="center", color="#bcbcbc")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "model_architecture.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 7. CNN and neural-network structure

The legacy CNN is useful for explaining convolution: each 2-D kernel learns a local time-frequency pattern, pooling adds small shift tolerance, and global average pooling produces one vector for the classification heads. The current production direction replaces scratch feature learning with a frozen, pretrained music-audio VAE representation, then trains only compact neural heads.
"""
        ),
        code(
            r"""
cnn_layers = pd.DataFrame([
    ["Input", "1 × 64 × frames", "Log-mel image"],
    ["Conv block 1", "24 channels, 5×5", "BatchNorm → GELU → 2×2 pool"],
    ["Conv block 2", "48 channels, 3×3", "BatchNorm → GELU → 2×2 pool"],
    ["Conv block 3", "96 channels, 3×3", "BatchNorm → GELU"],
    ["Global pooling", "96 values", "Adaptive average pool"],
    ["Embedding", "96 values", "Linear → GELU → dropout 0.15"],
    ["Heads", "2 + 10 logits", "Language + broad genre"],
], columns=["Stage", "Shape / width", "Operation"])
display(cnn_layers)

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
legacy = [("Mel\n1×64×T", 1), ("Conv\n24", 24), ("Conv\n48", 48), ("Conv\n96", 96), ("Embed\n96", 96), ("Heads\n2 + 10", 12)]
current = [("VAE latent\n64×T", 64), ("Mean + std\n128", 128), ("Linear\n256", 256), ("Linear\n256", 256), ("8 task\nheads", 8)]
for ax, stages, title, palette in [
    (axes[0], legacy, "Legacy mel-CNN (research/backwards compatibility)", "Blues"),
    (axes[1], current, "Current shared-encoder multi-head NN", "YlOrBr"),
]:
    ax.set_xlim(0, len(stages)); ax.set_ylim(0, 1); ax.axis("off")
    cmap = plt.get_cmap(palette)
    for i, (label, width) in enumerate(stages):
        height = 0.28 + 0.5*np.sqrt(width/max(v for _, v in stages))
        ax.add_patch(patches.FancyBboxPatch((i+0.08, 0.5-height/2), 0.72, height, boxstyle="round,pad=0.02", facecolor=cmap(0.35+0.55*i/max(1,len(stages)-1)), edgecolor="#f2f2f2"))
        ax.text(i+0.44, 0.5, label, ha="center", va="center", fontsize=9, color="#111111" if palette=="YlOrBr" else "#ffffff", fontweight="bold")
        if i < len(stages)-1: ax.annotate("", (i+1.05,0.5), (i+0.82,0.5), arrowprops=dict(arrowstyle="->", color="#e1c47a"))
    ax.set_title(title, pad=12, fontweight="bold")
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "nn_cnn_comparison.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 8. Real checkpoint training curves

The plot below reads the metadata exported from `skarly_audio_cnn.pt`; it is not a simulated learning curve. Because the broad-genre prior is weaker and rights-cleared Hindi genre coverage remains limited, Skarly retains creator confirmation and uses stricter confidence gates. The checkpoint selection used the grouped validation metrics, with excerpts from one recording kept on the same side of the split.
"""
        ),
        code(
            r"""
history_path = PROJECT_ROOT / "research" / "data" / "skarly_audio_cnn_history.json"
checkpoint_meta = json.loads(history_path.read_text(encoding="utf-8"))
history = pd.json_normalize(checkpoint_meta["history"])
display(pd.DataFrame({
    "Checkpoint format": [checkpoint_meta["format"]],
    "Training examples": [checkpoint_meta["training_examples"]],
    "Validation examples": [checkpoint_meta["validation_examples"]],
    "Best epoch": [checkpoint_meta["best_epoch"]],
    "Best validation language accuracy": [checkpoint_meta["best_validation"]["language_accuracy"]],
    "Best validation genre accuracy": [checkpoint_meta["best_validation"]["genre_accuracy"]],
}))

fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
axes[0].plot(history["epoch"], history["train.loss"], marker="o", label="Train", color="#e1c47a")
axes[0].plot(history["epoch"], history["validation.loss"], marker="o", label="Grouped validation", color="#6ec5ff")
axes[0].axvline(checkpoint_meta["best_epoch"], color="#8ee0b7", linestyle="--", alpha=0.8, label="Selected epoch")
axes[0].set(title="Joint training loss", xlabel="Epoch", ylabel="Loss")
axes[0].legend(); axes[0].grid(alpha=0.15)
axes[1].plot(history["epoch"], history["train.language_accuracy"], label="Language train", color="#e1c47a")
axes[1].plot(history["epoch"], history["validation.language_accuracy"], label="Language validation", color="#ffd166")
axes[1].plot(history["epoch"], history["train.genre_accuracy"], label="Genre train", color="#6ec5ff")
axes[1].plot(history["epoch"], history["validation.genre_accuracy"], label="Genre validation", color="#8ee0b7")
axes[1].set(title="Head accuracy", xlabel="Epoch", ylabel="Accuracy", ylim=(0,1.02))
axes[1].legend(fontsize=8); axes[1].grid(alpha=0.15)
fig.tight_layout()
fig.savefig(ARTIFACT_DIR / "cnn_training_curves.png", bbox_inches="tight")
plt.show()
"""
        ),
        md(
            """
## 9. Procedure: how one upload becomes five final versions

1. **Private upload:** the client requests a signed/private path and verifies that the upload exists.
2. **Source routing:** vocal-only audio is preserved; full-song/music input is separated with Demucs according to the chosen mode.
3. **Complete-song analysis:** tempo, key, phrases, energy, lyric/language evidence, melody, and shared-encoder predictions are aggregated across the decoded duration.
4. **Creator confirmation:** low-confidence genre/key/language decisions remain visible and editable; training contribution is off by default.
5. **Five producer blueprints:** each plan has a distinct instrument palette, groove, bass movement, energy arc, stereo treatment, and prompt.
6. **ACE-Step generation:** each blueprint produces a new backing. Generation telemetry records CUDA/model/runtime data.
7. **Protected mix:** the original singer is reused, phrase-aware ducking makes space, and source duration is treated as the truth.
8. **Quality gates:** Skarly checks decode, duration, loudness/silence, vocal leakage, musical compatibility, and pairwise arrangement diversity.
9. **Final version UI:** the five outputs remain independently playable/selectable; remixing reuses stems, while one-producer regeneration preserves the other four.
10. **Export:** WAV, MP3, instrumental, vocal, song map, metadata, and disclosure are bundled.

### Research limitations

- A single attached recording is a case study, not a dataset-level evaluation.
- Notebook tempo/key estimates are transparent signal-processing hypotheses; production results can differ.
- The legacy genre head's grouped validation score is not evidence for fine-grained regional genre recognition.
- A production claim requires rights-cleared, singer-disjoint data, calibration, and independent human listening tests.
- No voice cloning is performed or evaluated here.
"""
        ),
        code(
            r"""
summary = {
    "audio": AUDIO_PATH.name,
    "duration_seconds": round(duration_seconds, 3),
    "notebook_tempo_bpm": round(float(tempo_bpm), 2),
    "notebook_key_hypothesis": key_candidates[0][1],
    "checkpoint_best_epoch": checkpoint_meta["best_epoch"],
    "checkpoint_language_accuracy": checkpoint_meta["best_validation"]["language_accuracy"],
    "checkpoint_genre_accuracy": checkpoint_meta["best_validation"]["genre_accuracy"],
    "charts": sorted(path.name for path in ARTIFACT_DIR.glob("*.png")),
}
(ARTIFACT_DIR / "research_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
display(pd.Series(summary, name="Research summary").to_frame())
"""
        ),
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, OUTPUT)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
