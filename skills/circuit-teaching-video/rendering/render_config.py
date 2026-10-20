"""Resolution-independent output configuration, with no implicit proxy renders."""
from dataclasses import asdict, dataclass
import math

LOGICAL_WIDTH = 1920
LOGICAL_HEIGHT = 1080


@dataclass(frozen=True)
class RenderConfig:
    width: int = 3840
    height: int = 2160
    fps: float = 30
    crf: int = 19
    preset: str = "fast"
    threads: int = 4
    cache_mib: int = 192
    audio_bitrate: str = "192k"
    audio_sample_rate: int = 48000
    user_override_fields: tuple = ()

    def __post_init__(self):
        for name in ("width", "height"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 2 or value % 2:
                raise ValueError(f"{name} must be a positive even integer for yuv420p")
        if not isinstance(self.fps, (int, float)) or not math.isfinite(self.fps) or self.fps <= 0:
            raise ValueError("fps must be finite and positive")
        if not 0 <= self.crf <= 51:
            raise ValueError("crf must be between 0 and 51")
        if self.threads < 1 or self.cache_mib < 1:
            raise ValueError("threads and cache_mib must be positive")
        if self.audio_sample_rate != 48000 or self.audio_bitrate != "192k":
            raise ValueError("This adapter currently supports AAC 192k / 48000 Hz only")
        if self.preset not in {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}:
            raise ValueError("unsupported x264 preset")

    @property
    def ui_scale(self):
        return min(self.width / LOGICAL_WIDTH, self.height / LOGICAL_HEIGHT)

    @property
    def viewport(self):
        # Fit the authored composition, preserving geometry for non-16:9 overrides.
        w = round(LOGICAL_WIDTH * self.ui_scale)
        h = round(LOGICAL_HEIGHT * self.ui_scale)
        return ((self.width - w) // 2, (self.height - h) // 2, w, h)

    def manifest(self):
        result = asdict(self)
        result.update(profile_source="explicit_override" if self.user_override_fields else "default",
                      logical_canvas=[LOGICAL_WIDTH, LOGICAL_HEIGHT],
                      viewport=list(self.viewport), native_rasterization=True,
                      color_primaries="bt709", transfer="bt709", matrix="bt709", color_range="tv",
                      automatic_proxy=False, non_16_9_policy="contain; preserve authored composition")
        return result


class ByteLRU:
    """Budget native bitmap caches by bytes, not by a misleading entry count."""
    def __init__(self, max_bytes):
        from collections import OrderedDict
        self.data = OrderedDict()
        self.max_bytes = int(max_bytes)
        self.bytes = self.peak_bytes = self.hits = self.misses = self.evictions = 0

    def get(self, key):
        if key not in self.data:
            self.misses += 1
            return None
        value, size = self.data.pop(key)
        self.data[key] = (value, size)
        self.hits += 1
        return value

    def put(self, key, value, size):
        if key in self.data:
            _, previous = self.data.pop(key)
            self.bytes -= previous
        if size > self.max_bytes:
            return value
        while self.data and self.bytes + size > self.max_bytes:
            _, (_, previous) = self.data.popitem(last=False)
            self.bytes -= previous
            self.evictions += 1
        self.data[key] = value, int(size)
        self.bytes += int(size)
        self.peak_bytes = max(self.peak_bytes, self.bytes)
        return value

    def stats(self):
        return {key: getattr(self, key) for key in ("max_bytes", "bytes", "peak_bytes", "hits", "misses", "evictions")}
