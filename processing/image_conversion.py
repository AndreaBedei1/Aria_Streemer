from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover - optional runtime dependency
    cv2 = None


@dataclass(frozen=True)
class CandidateImage:
    name: str
    image_rgb: np.ndarray
    metadata: Dict[str, Any]


def normalize_image_for_display(
    image_data: Any, image_record: Any = None, source_name: str = "unknown"
) -> tuple[np.ndarray, dict]:
    """Normalize SDK image data or numpy arrays to display-safe RGB uint8.

    The returned metadata contains a `valid` flag. Invalid/suspicious frames are
    still returned as normalized arrays for debugging, but callers should avoid
    displaying them as live video.
    """

    metadata: Dict[str, Any] = {
        "source_name": source_name,
        "camera_id": _safe_attr(image_record, "camera_id"),
        "frame_number": _safe_attr(image_record, "frame_number"),
        "capture_timestamp_ns": _safe_attr(image_record, "capture_timestamp_ns"),
        "conversion_path": "none",
        "valid": False,
        "warning": "",
        "error": "",
    }

    try:
        arr = _extract_array(image_data)
    except Exception as exc:
        metadata["error"] = f"cannot extract image array: {exc}"
        return _placeholder_rgb(), metadata

    metadata.update(_array_stats(arr, prefix="original"))
    if not isinstance(arr, np.ndarray):
        metadata["error"] = "input is not a numpy array"
        return _placeholder_rgb(), metadata
    if arr.size == 0:
        metadata["error"] = "empty image array"
        return _placeholder_rgb(), metadata
    try:
        numeric_arr = arr.astype(np.float32, copy=False)
    except Exception as exc:
        metadata["error"] = f"image array is not numeric: {exc}"
        return _placeholder_rgb(), metadata
    if not np.all(np.isfinite(numeric_arr)):
        metadata["error"] = "image contains NaN or Inf"
        return _placeholder_rgb(), metadata

    candidates = conversion_candidates(arr)
    if not candidates:
        metadata["error"] = f"unsupported image shape {arr.shape}"
        return _placeholder_rgb(), metadata

    source_is_et = _is_et_source(source_name, metadata.get("camera_id"))
    scored: List[CandidateImage] = []
    for name, candidate in candidates:
        rgb = _ensure_uint8_rgb(candidate)
        quality = assess_display_quality(rgb, source_is_et=source_is_et)
        cand_meta = {
            **metadata,
            **_array_stats(rgb, prefix="display"),
            **quality,
            "conversion_path": name,
            "valid": quality["valid"],
            "warning": quality["warning"],
            "error": "",
        }
        scored.append(CandidateImage(name, rgb, cand_meta))

    chosen = _choose_candidate(scored)
    return np.ascontiguousarray(chosen.image_rgb), chosen.metadata


def conversion_candidates(arr: np.ndarray) -> List[Tuple[str, np.ndarray]]:
    """Return reasonable display conversion candidates for debugging."""

    arr = np.asarray(arr)
    candidates: List[Tuple[str, np.ndarray]] = []

    if arr.ndim == 2:
        candidates.append(("gray_to_rgb", _gray_to_rgb(arr)))
        if cv2 is not None and arr.shape[0] % 3 == 0:
            h = arr.shape[0] * 2 // 3
            if h > 0:
                yuv = arr.reshape((arr.shape[0], arr.shape[1]))
                try:
                    rgb = cv2.cvtColor(_ensure_uint8_2d(yuv), cv2.COLOR_YUV2RGB_I420)
                    candidates.append(("yuv_i420_to_rgb", rgb))
                except Exception:
                    pass
        return candidates

    if arr.ndim != 3:
        return candidates

    channels = arr.shape[2]
    if channels == 1:
        candidates.append(("gray_to_rgb", _gray_to_rgb(arr[:, :, 0])))
    elif channels == 3:
        candidates.append(("as_rgb", arr[:, :, :3]))
        candidates.append(("bgr_to_rgb", arr[:, :, ::-1]))
        if cv2 is not None:
            u8 = _ensure_uint8_rgb(arr[:, :, :3])
            for name, code in (
                ("yuv_to_rgb", cv2.COLOR_YUV2RGB),
                ("ycrcb_to_rgb", cv2.COLOR_YCrCb2RGB),
            ):
                try:
                    candidates.append((name, cv2.cvtColor(u8, code)))
                except Exception:
                    pass
    elif channels == 4:
        candidates.append(("rgba_to_rgb", arr[:, :, :3]))
        candidates.append(("bgra_to_rgb", arr[:, :, [2, 1, 0]]))
    return candidates


def assess_display_quality(rgb: np.ndarray, source_is_et: bool = False) -> Dict[str, Any]:
    if not isinstance(rgb, np.ndarray) or rgb.ndim != 3 or rgb.shape[2] != 3:
        return {
            "valid": False,
            "warning": "invalid display shape",
            "quality_score": 0.0,
            "yellow_fraction": 0.0,
        }

    sample = _sample_for_quality(rgb)
    values = sample.astype(np.float32)
    red = values[:, :, 0]
    green = values[:, :, 1]
    blue = values[:, :, 2]
    gray = values.mean(axis=2)
    gray_std = float(np.std(gray))
    channel_means = values.reshape(-1, 3).mean(axis=0)

    yellow_pixels = (
        (red > 145.0)
        & (green > 120.0)
        & (blue < 90.0)
        & ((np.minimum(red, green) - blue) > 55.0)
    )
    yellow_fraction = float(np.mean(yellow_pixels))
    blue_starved = channel_means[2] < 0.45 * max(1.0, min(channel_means[0], channel_means[1]))
    broad_yellow_cast = (
        channel_means[0] > 95.0 and channel_means[1] > 90.0 and blue_starved
    )

    warnings: List[str] = []
    valid = True
    if gray_std < 1.5 and not source_is_et:
        valid = False
        warnings.append("nearly flat image")
    if yellow_fraction > 0.55 and gray_std < 55.0:
        valid = False
        warnings.append("mostly yellow/orange with low contrast")
    if broad_yellow_cast and gray_std < 42.0:
        valid = False
        warnings.append("suspicious yellow color cast")

    quality_score = float(
        max(0.0, min(1.0, (gray_std / 45.0) * (1.0 - min(1.0, yellow_fraction))))
    )
    if source_is_et and not valid and warnings == ["nearly flat image"]:
        valid = True
        warnings = []

    return {
        "valid": valid,
        "warning": "; ".join(warnings),
        "quality_score": quality_score,
        "yellow_fraction": yellow_fraction,
        "gray_std": gray_std,
        "channel_means": [float(x) for x in channel_means],
    }


def _extract_array(image_data: Any) -> np.ndarray:
    if hasattr(image_data, "to_numpy_array"):
        return np.asarray(image_data.to_numpy_array())
    return np.asarray(image_data)


def _choose_candidate(candidates: Iterable[CandidateImage]) -> CandidateImage:
    items = list(candidates)
    valid = [c for c in items if c.metadata.get("valid")]
    for preferred_name in ("as_rgb", "rgba_to_rgb", "gray_to_rgb"):
        for candidate in valid:
            if candidate.name == preferred_name and not candidate.metadata.get("warning"):
                return candidate
    pool = valid or items
    return max(
        pool,
        key=lambda c: (
            float(c.metadata.get("quality_score", 0.0)),
            -float(c.metadata.get("yellow_fraction", 1.0)),
            c.name == "as_rgb",
        ),
    )


def _ensure_uint8_rgb(arr: np.ndarray) -> np.ndarray:
    rgb = np.asarray(arr)
    if rgb.ndim == 2:
        rgb = _gray_to_rgb(rgb)
    elif rgb.ndim == 3 and rgb.shape[2] == 1:
        rgb = np.repeat(rgb, 3, axis=2)
    elif rgb.ndim == 3 and rgb.shape[2] > 3:
        rgb = rgb[:, :, :3]
    if rgb.dtype == np.uint8:
        return np.ascontiguousarray(rgb)

    rgb_float = rgb.astype(np.float32)
    finite = np.isfinite(rgb_float)
    if not np.any(finite):
        return np.zeros((*rgb.shape[:2], 3), dtype=np.uint8)
    min_val = float(np.min(rgb_float[finite]))
    max_val = float(np.max(rgb_float[finite]))
    if max_val <= 1.0 and min_val >= 0.0:
        rgb_float = rgb_float * 255.0
    elif max_val > 255.0 or min_val < 0.0:
        lo = float(np.percentile(rgb_float[finite], 1))
        hi = float(np.percentile(rgb_float[finite], 99))
        if hi <= lo:
            hi = lo + 1.0
        rgb_float = (rgb_float - lo) * (255.0 / (hi - lo))
    return np.ascontiguousarray(np.clip(rgb_float, 0, 255).astype(np.uint8))


def _ensure_uint8_2d(arr: np.ndarray) -> np.ndarray:
    u8 = _ensure_uint8_rgb(_gray_to_rgb(arr))
    return u8[:, :, 0]


def _gray_to_rgb(gray: np.ndarray) -> np.ndarray:
    gray_u8 = _ensure_uint8_gray(gray)
    return np.repeat(gray_u8[:, :, None], 3, axis=2)


def _ensure_uint8_gray(gray: np.ndarray) -> np.ndarray:
    g = np.asarray(gray)
    if g.dtype == np.uint8:
        return np.ascontiguousarray(g)
    gf = g.astype(np.float32)
    finite = np.isfinite(gf)
    if not np.any(finite):
        return np.zeros(g.shape, dtype=np.uint8)
    min_val = float(np.min(gf[finite]))
    max_val = float(np.max(gf[finite]))
    if max_val <= 1.0 and min_val >= 0.0:
        gf = gf * 255.0
    elif max_val > 255.0 or min_val < 0.0:
        lo = float(np.percentile(gf[finite], 1))
        hi = float(np.percentile(gf[finite], 99))
        if hi <= lo:
            hi = lo + 1.0
        gf = (gf - lo) * (255.0 / (hi - lo))
    return np.ascontiguousarray(np.clip(gf, 0, 255).astype(np.uint8))


def _sample_for_quality(rgb: np.ndarray) -> np.ndarray:
    if rgb.shape[0] <= 240 and rgb.shape[1] <= 320:
        return rgb
    y_idx = np.linspace(0, rgb.shape[0] - 1, min(180, rgb.shape[0])).astype(int)
    x_idx = np.linspace(0, rgb.shape[1] - 1, min(240, rgb.shape[1])).astype(int)
    return rgb[y_idx][:, x_idx]


def _array_stats(arr: Any, prefix: str) -> Dict[str, Any]:
    if not isinstance(arr, np.ndarray):
        return {
            f"{prefix}_shape": None,
            f"{prefix}_dtype": str(type(arr)),
        }
    out: Dict[str, Any] = {
        f"{prefix}_shape": [int(x) for x in arr.shape],
        f"{prefix}_dtype": str(arr.dtype),
    }
    try:
        numeric = arr.astype(np.float32, copy=False)
        finite = numeric[np.isfinite(numeric)]
        if finite.size:
            out.update(
                {
                    f"{prefix}_min": float(np.min(finite)),
                    f"{prefix}_max": float(np.max(finite)),
                    f"{prefix}_mean": float(np.mean(finite)),
                    f"{prefix}_std": float(np.std(finite)),
                }
            )
    except Exception as exc:
        out[f"{prefix}_stats_error"] = str(exc)
    return out


def _safe_attr(obj: Any, name: str) -> Any:
    if obj is None:
        return None
    try:
        value = getattr(obj, name)
    except Exception:
        return None
    if callable(value):
        try:
            value = value()
        except Exception:
            return None
    if isinstance(value, np.generic):
        return value.item()
    return value


def _is_et_source(source_name: str, camera_id: Any) -> bool:
    if str(source_name).lower().startswith("et"):
        return True
    try:
        return int(camera_id) in {16, 32}
    except Exception:
        return False


def _placeholder_rgb() -> np.ndarray:
    return np.zeros((64, 64, 3), dtype=np.uint8)
