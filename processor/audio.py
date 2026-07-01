"""Live microphone frame capture."""

from __future__ import annotations

import ctypes
import ctypes.util
import os
import queue
import re
import shutil
import subprocess
from typing import Iterator


def iter_microphone_frames(
    *,
    sample_rate: int = 16000,
    frame_ms: int = 40,
    device: int | str | None = None,
) -> Iterator[list[float]]:
    try:
        import sounddevice as sd  # type: ignore
    except Exception as sounddevice_error:
        if _is_wsl():
            try:
                yield from _iter_windows_ffmpeg_frames(
                    sample_rate=sample_rate,
                    frame_ms=frame_ms,
                    device=None if device is None else str(device),
                    sounddevice_error=sounddevice_error,
                )
                return
            except Exception as windows_error:
                yield from _iter_alsa_frames(
                    sample_rate=sample_rate,
                    frame_ms=frame_ms,
                    device=str(device or "default"),
                    sounddevice_error=sounddevice_error,
                    extra_error=windows_error,
                )
                return

        yield from _iter_alsa_frames(
            sample_rate=sample_rate,
            frame_ms=frame_ms,
            device=str(device or "default"),
            sounddevice_error=sounddevice_error,
            extra_error=None,
        )
        return

    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    frames: queue.Queue[list[float]] = queue.Queue()

    def callback(indata, _frames, _time, status) -> None:  # type: ignore[no-untyped-def]
        if status:
            print(f"audio status: {status}")
        mono = indata[:, 0]
        frames.put([float(value) for value in mono])

    with sd.InputStream(
        samplerate=sample_rate,
        blocksize=frame_size,
        channels=1,
        dtype="float32",
        device=device,
        callback=callback,
    ):
        while True:
            yield frames.get()


def _iter_alsa_frames(
    *,
    sample_rate: int,
    frame_ms: int,
    device: str,
    sounddevice_error: Exception,
    extra_error: Exception | None,
) -> Iterator[list[float]]:
    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    alsa = _AlsaCapture(device=device, sample_rate=sample_rate, frame_size=frame_size)
    try:
        while True:
            yield alsa.read_frame()
    except Exception as alsa_error:
        extra = f"; Windows DirectShow failed: {extra_error}" if extra_error is not None else ""
        raise RuntimeError(
            "Live recording requires either working sounddevice+PortAudio or an ALSA capture device. "
            f"sounddevice failed: {sounddevice_error}{extra}; ALSA failed: {alsa_error}"
        ) from alsa_error
    finally:
        alsa.close()


def _iter_windows_ffmpeg_frames(
    *,
    sample_rate: int,
    frame_ms: int,
    device: str | None,
    sounddevice_error: Exception,
) -> Iterator[list[float]]:
    ffmpeg = _find_windows_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError(f"Windows ffmpeg.exe was not found; sounddevice failed: {sounddevice_error}")

    selected_device = device or _first_directshow_audio_device(ffmpeg)
    if not selected_device:
        raise RuntimeError("No Windows DirectShow audio capture device was found.")

    frame_size = max(1, int(sample_rate * frame_ms / 1000))
    bytes_per_frame = frame_size * 2
    command = [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "dshow",
        "-audio_buffer_size",
        "50",
        "-i",
        f"audio={selected_device}",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
    )

    assert process.stdout is not None
    try:
        while True:
            chunk = process.stdout.read(bytes_per_frame)
            if len(chunk) == bytes_per_frame:
                yield [
                    int.from_bytes(chunk[offset : offset + 2], "little", signed=True) / 32768.0
                    for offset in range(0, len(chunk), 2)
                ]
                continue

            stderr = _read_process_stderr(process)
            raise RuntimeError(
                f"Windows DirectShow capture stopped for device {selected_device!r}. {stderr}".strip()
            )
    finally:
        _terminate_process(process)


def _is_wsl() -> bool:
    if os.environ.get("WSL_INTEROP"):
        return True
    try:
        version = open("/proc/version", "r", encoding="utf-8").read().lower()
    except OSError:
        return False
    return "microsoft" in version or "wsl" in version


def _find_windows_ffmpeg() -> str | None:
    found = shutil.which("ffmpeg.exe")
    if found:
        return found

    candidates = [
        "/mnt/c/Program Files/ImageMagick-7.1.1-Q16-HDRI/ffmpeg.exe",
        "/mnt/c/Program Files/ffmpeg/bin/ffmpeg.exe",
        "/mnt/c/ffmpeg/bin/ffmpeg.exe",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _first_directshow_audio_device(ffmpeg: str) -> str | None:
    completed = subprocess.run(
        [ffmpeg, "-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        text=True,
        capture_output=True,
        check=False,
        timeout=10,
    )
    output = completed.stderr or completed.stdout
    in_audio_section = False
    for line in output.splitlines():
        if "DirectShow audio devices" in line:
            in_audio_section = True
            continue
        if "DirectShow video devices" in line:
            in_audio_section = False
            continue
        if not in_audio_section:
            continue

        match = re.search(r'\]\s+"([^"]+)"', line)
        if match and not match.group(1).startswith("@device_"):
            return match.group(1)
    return None


def _read_process_stderr(process: subprocess.Popen[bytes]) -> str:
    try:
        if process.stderr is None:
            return ""
        data = process.stderr.read() or b""
    except Exception:
        return ""
    return data.decode("utf-8", errors="replace")


def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=2)


class _AlsaCapture:
    SND_PCM_STREAM_CAPTURE = 1
    SND_PCM_FORMAT_S16_LE = 2
    SND_PCM_ACCESS_RW_INTERLEAVED = 3
    EPIPE = -32

    def __init__(self, *, device: str, sample_rate: int, frame_size: int) -> None:
        library_name = ctypes.util.find_library("asound")
        if library_name is None:
            raise RuntimeError("libasound.so.2 was not found")

        self._lib = ctypes.CDLL(library_name)
        self._handle = ctypes.c_void_p()
        self._frame_size = frame_size
        self._configure_functions()

        err = self._lib.snd_pcm_open(
            ctypes.byref(self._handle),
            device.encode("utf-8"),
            self.SND_PCM_STREAM_CAPTURE,
            0,
        )
        self._check(err, f"open ALSA capture device {device!r}")

        err = self._lib.snd_pcm_set_params(
            self._handle,
            self.SND_PCM_FORMAT_S16_LE,
            self.SND_PCM_ACCESS_RW_INTERLEAVED,
            1,
            sample_rate,
            1,
            max(100000, int(frame_size / sample_rate * 1_000_000 * 4)),
        )
        self._check(err, "configure ALSA capture")

    def read_frame(self) -> list[float]:
        buffer_type = ctypes.c_int16 * self._frame_size
        buffer = buffer_type()

        while True:
            read = self._lib.snd_pcm_readi(self._handle, buffer, self._frame_size)
            if read == self.EPIPE:
                self._lib.snd_pcm_prepare(self._handle)
                continue
            self._check(read, "read ALSA capture frame")
            break

        samples = [buffer[index] / 32768.0 for index in range(int(read))]
        if len(samples) < self._frame_size:
            samples.extend([0.0] * (self._frame_size - len(samples)))
        return samples

    def close(self) -> None:
        if self._handle:
            self._lib.snd_pcm_close(self._handle)
            self._handle = ctypes.c_void_p()

    def _configure_functions(self) -> None:
        self._lib.snd_pcm_open.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_int,
        ]
        self._lib.snd_pcm_open.restype = ctypes.c_int
        self._lib.snd_pcm_set_params.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.c_int,
            ctypes.c_uint,
        ]
        self._lib.snd_pcm_set_params.restype = ctypes.c_int
        self._lib.snd_pcm_readi.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
        self._lib.snd_pcm_readi.restype = ctypes.c_long
        self._lib.snd_pcm_prepare.argtypes = [ctypes.c_void_p]
        self._lib.snd_pcm_prepare.restype = ctypes.c_int
        self._lib.snd_pcm_close.argtypes = [ctypes.c_void_p]
        self._lib.snd_pcm_close.restype = ctypes.c_int
        self._lib.snd_strerror.argtypes = [ctypes.c_int]
        self._lib.snd_strerror.restype = ctypes.c_char_p

    def _check(self, err: int, action: str) -> None:
        if err >= 0:
            return
        message = self._lib.snd_strerror(err).decode("utf-8", errors="replace")
        raise RuntimeError(f"could not {action}: {message}")
