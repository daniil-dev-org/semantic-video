from pathlib import Path
from stp.config import load_config
from stp.proxy_encoder import encode_proxy
from stp.ffmpeg_tools import VideoMeta

def encode_proxy_bridge(input_path: Path, output_dir: Path, meta: VideoMeta) -> Path:
    """
    Bridge function calling the existing STP proxy encoder.
    Uses current project-wide config.yaml settings.
    """
    cfg = load_config()
    proxy_path, manifest = encode_proxy(input_path, output_dir, cfg.proxy, meta)
    return proxy_path
