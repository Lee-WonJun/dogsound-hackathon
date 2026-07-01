"""Audio feature extraction and a-z tokenization for dogsound inputs."""

from __future__ import annotations

import math
import statistics
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

ALPHABET = "abcdefghijklmnopqrstuvwxyz"


@dataclass(frozen=True)
class FeatureFrame:
    rms: float
    centroid: float
    bandwidth: float
    zero_crossing: float


@dataclass(frozen=True)
class TokenRun:
    char: str
    start: int
    end: int
    length: int


def normalize(values: Sequence[float]) -> list[float]:
    if not values:
        return []

    min_value = min(values)
    max_value = max(values)
    spread = max_value - min_value
    if spread < 1e-12:
        return [0.0 for _ in values]

    return [(value - min_value) / spread for value in values]


def quantize_to_letters(values: Sequence[float]) -> str:
    letters = []
    for value in values:
        clipped = min(1.0, max(0.0, value))
        letters.append(ALPHABET[int(clipped * 25)])
    return "".join(letters)


def summarize_tokens(tokens: str) -> dict:
    cleaned = "".join(ch for ch in tokens.lower() if "a" <= ch <= "z")
    if not cleaned:
        raise ValueError("Token source does not contain a-z token letters.")

    values = [ord(ch) - ord("a") for ch in cleaned]
    rises = 0
    falls = 0
    flats = 0
    jumps = 0
    counts = {ch: 0 for ch in ALPHABET}

    for index, value in enumerate(values):
        counts[cleaned[index]] += 1
        if index == 0:
            continue

        diff = value - values[index - 1]
        if diff > 0:
            rises += 1
        elif diff < 0:
            falls += 1
        else:
            flats += 1

        if abs(diff) >= 4:
            jumps += 1

    return {
        "length": len(cleaned),
        "min": min(values),
        "max": max(values),
        "average": sum(values) / len(values),
        "rises": rises,
        "falls": falls,
        "flats": flats,
        "jumps": jumps,
        "counts": counts,
        "longest_runs": [
            run.__dict__ for run in sorted(_detect_runs(cleaned), key=lambda item: item.length, reverse=True)[:12]
        ],
    }


def tokenize_samples(
    samples: Sequence[float],
    *,
    sample_rate: int = 16000,
    frame_ms: int = 40,
    hop_ms: int | None = None,
    token_length: int | None = None,
    silence_floor: float = 0.003,
) -> str:
    features = extract_feature_series(
        samples,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        hop_ms=hop_ms,
        silence_floor=silence_floor,
    )

    if token_length is not None and token_length > 0:
        features = _resample_values(features, token_length)

    return quantize_to_letters(features)


def extract_feature_series(
    samples: Sequence[float],
    *,
    sample_rate: int = 16000,
    frame_ms: int = 40,
    hop_ms: int | None = None,
    silence_floor: float = 0.003,
) -> list[float]:
    clean_samples = [float(sample) for sample in samples]
    if not clean_samples:
        raise ValueError("Audio is empty.")

    overall_rms = _rms(clean_samples)
    if overall_rms < silence_floor:
        raise ValueError("Audio is empty or too quiet to tokenize.")

    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    hop_size = max(1, int(sample_rate * (hop_ms if hop_ms is not None else frame_ms) / 1000))
    frames = list(_iter_frames(clean_samples, frame_size, hop_size))
    if not frames:
        raise ValueError("Audio did not contain enough samples for one frame.")

    frame_features = [_extract_frame_features(frame, sample_rate) for frame in frames]
    rms_values = normalize([frame.rms for frame in frame_features])
    centroid_values = normalize([frame.centroid for frame in frame_features])
    bandwidth_values = normalize([frame.bandwidth for frame in frame_features])
    zcr_values = normalize([frame.zero_crossing for frame in frame_features])

    combined = [
        rms_value * 0.40
        + centroid_value * 0.30
        + bandwidth_value * 0.20
        + zcr_value * 0.10
        for rms_value, centroid_value, bandwidth_value, zcr_value in zip(
            rms_values,
            centroid_values,
            bandwidth_values,
            zcr_values,
        )
    ]
    return normalize(combined)


def tokenize_audio_file(
    audio_path: str | Path,
    *,
    sample_rate: int = 16000,
    frame_ms: int = 40,
    hop_ms: int | None = None,
    token_length: int | None = None,
) -> str:
    path = Path(audio_path)
    samples, source_rate = load_audio_file(path, sample_rate=sample_rate)
    if source_rate != sample_rate:
        samples = _resample_samples(samples, source_rate, sample_rate)

    return tokenize_samples(
        samples,
        sample_rate=sample_rate,
        frame_ms=frame_ms,
        hop_ms=hop_ms,
        token_length=token_length,
    )


def load_audio_file(path: Path, *, sample_rate: int = 16000) -> tuple[list[float], int]:
    if not path.exists():
        raise FileNotFoundError(path)

    if path.suffix.lower() == ".wav":
        return _load_wav(path)

    return _load_with_optional_backend(path, sample_rate=sample_rate)


def _extract_frame_features(frame: Sequence[float], sample_rate: int) -> FeatureFrame:
    rms_value = _rms(frame)
    zero_crossing = _zero_crossing_rate(frame)

    spectral = _numpy_spectral_features(frame, sample_rate)
    if spectral is None:
        spectral = _stdlib_spectral_proxy(frame, sample_rate)

    centroid, bandwidth = spectral
    return FeatureFrame(
        rms=rms_value,
        centroid=centroid,
        bandwidth=bandwidth,
        zero_crossing=zero_crossing,
    )


def _numpy_spectral_features(frame: Sequence[float], sample_rate: int) -> tuple[float, float] | None:
    try:
        import numpy as np  # type: ignore
    except Exception:
        return None

    values = np.asarray(frame, dtype=float)
    if values.size == 0:
        return 0.0, 0.0

    window = np.hanning(values.size)
    spectrum = np.abs(np.fft.rfft(values * window))
    freqs = np.fft.rfftfreq(values.size, d=1.0 / sample_rate)
    total = float(np.sum(spectrum))
    if total <= 1e-12:
        return 0.0, 0.0

    centroid = float(np.sum(freqs * spectrum) / total)
    bandwidth = float(np.sqrt(np.sum(((freqs - centroid) ** 2) * spectrum) / total))
    return centroid, bandwidth


def _stdlib_spectral_proxy(frame: Sequence[float], sample_rate: int) -> tuple[float, float]:
    if len(frame) < 2:
        return 0.0, 0.0

    diffs = [frame[index] - frame[index - 1] for index in range(1, len(frame))]
    high_frequency_energy = _rms(diffs)
    centroid = high_frequency_energy * sample_rate / 2.0

    if len(diffs) < 2:
        return centroid, 0.0

    second_diffs = [diffs[index] - diffs[index - 1] for index in range(1, len(diffs))]
    bandwidth = _rms(second_diffs) * sample_rate / 2.0
    return centroid, bandwidth


def _iter_frames(samples: Sequence[float], frame_size: int, hop_size: int) -> Iterable[list[float]]:
    if len(samples) <= frame_size:
        padded = list(samples)
        padded.extend([0.0] * (frame_size - len(padded)))
        yield padded
        return

    for start in range(0, len(samples) - frame_size + 1, hop_size):
        yield list(samples[start : start + frame_size])


def _rms(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return math.sqrt(sum(value * value for value in values) / len(values))


def _zero_crossing_rate(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0

    crossings = 0
    previous = values[0]
    for value in values[1:]:
        if (previous < 0 <= value) or (previous >= 0 > value):
            crossings += 1
        previous = value

    return crossings / (len(values) - 1)


def _detect_runs(tokens: str) -> list[TokenRun]:
    if not tokens:
        return []

    runs: list[TokenRun] = []
    start = 0
    for index in range(1, len(tokens) + 1):
        if index == len(tokens) or tokens[index] != tokens[start]:
            runs.append(TokenRun(char=tokens[start], start=start, end=index - 1, length=index - start))
            start = index
    return runs


def _resample_values(values: Sequence[float], target_length: int) -> list[float]:
    if not values:
        return []
    if len(values) == target_length:
        return list(values)
    if target_length <= 1:
        return [values[0]]

    result = []
    source_max = len(values) - 1
    target_max = target_length - 1
    for index in range(target_length):
        position = index * source_max / target_max
        left = int(math.floor(position))
        right = min(source_max, left + 1)
        ratio = position - left
        result.append(values[left] * (1.0 - ratio) + values[right] * ratio)
    return result


def _resample_samples(samples: Sequence[float], source_rate: int, target_rate: int) -> list[float]:
    if source_rate == target_rate or not samples:
        return list(samples)

    duration = len(samples) / source_rate
    target_length = max(1, int(duration * target_rate))
    return _resample_values(samples, target_length)


def _load_wav(path: Path) -> tuple[list[float], int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frames = wav_file.readframes(wav_file.getnframes())

    if sample_width not in {1, 2, 3, 4}:
        raise ValueError(f"Unsupported WAV sample width: {sample_width}")

    samples = []
    step = sample_width * channels
    for offset in range(0, len(frames), step):
        channel_values = []
        for channel in range(channels):
            start = offset + channel * sample_width
            raw = frames[start : start + sample_width]
            channel_values.append(_decode_pcm(raw, sample_width))
        samples.append(statistics.fmean(channel_values))

    return samples, sample_rate


def _decode_pcm(raw: bytes, sample_width: int) -> float:
    if sample_width == 1:
        return (raw[0] - 128) / 128.0

    if sample_width == 3:
        extended = raw + (b"\xff" if raw[-1] & 0x80 else b"\x00")
        value = int.from_bytes(extended, byteorder="little", signed=True)
        return value / 8388608.0

    value = int.from_bytes(raw, byteorder="little", signed=True)
    max_value = float(2 ** (sample_width * 8 - 1))
    return value / max_value


def _load_with_optional_backend(path: Path, *, sample_rate: int) -> tuple[list[float], int]:
    try:
        import librosa  # type: ignore
    except Exception:
        librosa = None

    if librosa is not None:
        audio, source_rate = librosa.load(str(path), sr=sample_rate, mono=True)
        return [float(value) for value in audio], int(source_rate)

    try:
        import soundfile as sf  # type: ignore
    except Exception as exc:
        raise RuntimeError(
            "Non-WAV audio requires librosa or soundfile. Install processor requirements first."
        ) from exc

    audio, source_rate = sf.read(str(path), dtype="float32", always_2d=True)
    mono = audio.mean(axis=1)
    return [float(value) for value in mono], int(source_rate)
