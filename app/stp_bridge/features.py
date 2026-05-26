from pathlib import Path
from stp.config import load_config
from stp.video_features import extract_features, select_keyframes, save_keyframes
from stp.sidecar_schema import build_sidecar, save_sidecar
from stp.ffmpeg_tools import VideoMeta
from stp.utils import sha256_file

def extract_features_bridge(input_path: Path, output_dir: Path, meta: VideoMeta) -> Path:
    """
    Bridge function extracting OpenCV metrics, selecting keyframes, and 
    generating the final STP-0.1 video_metrics_sidecar.json.
    """
    cfg = load_config()
    
    # 1. OpenCV Feature Extraction
    metrics = extract_features(input_path, cfg.video_features, meta.fps, meta.duration_ms)
    
    # 2. Select and Save Keyframes
    kf_dir = output_dir / "keyframes"
    kf_indices = select_keyframes(metrics, cfg.video_features.keyframe_count)
    kf_files = save_keyframes(input_path, metrics, kf_indices, kf_dir, meta.fps)
    
    # 3. Build Sidecar Document
    sidecar_doc = build_sidecar(
        asset_id=input_path.stem,
        source_name=input_path.name,
        meta=meta,
        metrics=metrics,
        proxy_cfg=cfg.proxy,
        feat_cfg=cfg.video_features,
        keyframe_files=kf_files
    )
    
    # Fill integrity hashes
    sidecar_doc.integrity.source_sha256 = sha256_file(input_path)
    
    proxy_path = output_dir / "proxy_144p.mp4"
    if proxy_path.exists():
        sidecar_doc.integrity.proxy_sha256 = sha256_file(proxy_path)
        
    sidecar_path = output_dir / "video_metrics_sidecar.json"
    save_sidecar(sidecar_doc, sidecar_path)
    
    # Self-referential hash update
    sidecar_doc.integrity.sidecar_sha256 = sha256_file(sidecar_path)
    save_sidecar(sidecar_doc, sidecar_path)
    
    return sidecar_path
