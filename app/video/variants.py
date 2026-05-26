import hashlib
import random
from typing import Dict, Any, List, Tuple

from ..core.logging import setup_logger

logger = setup_logger("app.video.variants")

def get_deterministic_rng(seed_str: str) -> random.Random:
    """Generate a portable, robust Python random.Random instance from a seed string."""
    h = hashlib.sha256(seed_str.encode("utf-8")).hexdigest()
    seed_int = int(h, 16) % (2**32)
    return random.Random(seed_int)

def generate_variants_config(
    job_id: str,
    profile_data: Dict[str, Any],
    count: int
) -> List[Dict[str, Any]]:
    """
    Generate configurations for N variants deterministically using RNG seeded by job ID.
    
    Each variant dictionary contains the generated parameter values for speed, crop, color, etc.
    """
    variants = []
    for idx in range(count):
        # Unique deterministic seed for each variant index of this job
        seed_str = f"{job_id}-{idx + 1}"
        rng = get_deterministic_rng(seed_str)
        
        variant_cfg = {
            "name": f"v{idx + 1}",
            "speed": 1.0,
            "crop_percent": 0.0,
            "brightness": 0.0,
            "contrast": 1.0,
            "saturation": 1.0,
            "noise_strength": 0,
            "volume_db": 0.0,
            "mirror": False,
            "rotation_deg": 0.0,
            "aspect_ratio": None
        }
        
        # 1. Aspect Ratio Presets
        if profile_data.get("aspect_ratio", {}).get("enabled", False):
            variant_cfg["aspect_ratio"] = profile_data["aspect_ratio"].get("target")
            
        # 2. Speed (e.g. 0.97 - 1.05)
        speed_opt = profile_data.get("speed", {})
        if speed_opt.get("enabled", False):
            f_min = speed_opt.get("factor_min", 0.97)
            f_max = speed_opt.get("factor_max", 1.04)
            variant_cfg["speed"] = round(rng.uniform(f_min, f_max), 3)
            
        # 3. Crop (e.g. up to 3%)
        crop_opt = profile_data.get("crop", {})
        if crop_opt.get("enabled", False):
            max_p = crop_opt.get("max_percent", 2)
            variant_cfg["crop_percent"] = round(rng.uniform(0.1, max_p), 2)
            
        # 4. Color Grading
        color_opt = profile_data.get("color", {})
        if color_opt.get("enabled", False):
            # Brightness delta (usually -0.1 to 0.1)
            b_range = color_opt.get("brightness_delta", [-0.03, 0.03])
            variant_cfg["brightness"] = round(rng.uniform(b_range[0], b_range[1]), 3)
            
            # Contrast delta (multiplier, 1 + delta)
            c_range = color_opt.get("contrast_delta", [-0.05, 0.05])
            variant_cfg["contrast"] = round(1.0 + rng.uniform(c_range[0], c_range[1]), 3)
            
            # Saturation delta (multiplier, 1 + delta)
            s_range = color_opt.get("saturation_delta", [-0.08, 0.08])
            variant_cfg["saturation"] = round(1.0 + rng.uniform(s_range[0], s_range[1]), 3)
            
        # 5. Noise strength
        noise_opt = profile_data.get("noise", {})
        if noise_opt.get("enabled", False):
            str_range = noise_opt.get("strength", [2, 5])
            variant_cfg["noise_strength"] = rng.randint(str_range[0], str_range[1])
            
        # 6. Audio Volume delta
        audio_opt = profile_data.get("audio", {})
        if audio_opt.get("enabled", False):
            vol_range = audio_opt.get("volume_delta", [-0.5, 0.5])
            variant_cfg["volume_db"] = round(rng.uniform(vol_range[0], vol_range[1]), 2)
            
        # 7. Mirror (dynamic fallback or extra)
        # Flip 30% of the time if we are looking for variation
        if rng.random() < 0.3:
            variant_cfg["mirror"] = True
            
        variants.append(variant_cfg)
        logger.info(f"Generated deterministic config for variant {variant_cfg['name']}: {variant_cfg}")
        
    return variants

def compile_filters(cfg: Dict[str, Any], has_audio: bool) -> Tuple[List[str], List[str]]:
    """
    Compile a variant config dictionary into list of FFmpeg video (vf) and audio (af) filters.
    
    Returns (video_filters_list, audio_filters_list).
    """
    vf = []
    af = []
    
    # 1. Formats/Aspect Ratio
    aspect = cfg.get("aspect_ratio")
    if aspect == "9:16":
        # Centered crop from 16:9 to 9:16, then scale back to a standardized size or preserve h
        vf.append("crop=ih*9/16:ih:(iw-ow)/2:(ih-oh)/2")
    elif aspect == "1:1":
        # Centered crop to square
        vf.append("crop=ih:ih:(iw-ow)/2:0")
        
    # 2. Geometry - symmetrical cropping and scaling back to preserve source frame size
    crop_p = cfg.get("crop_percent", 0.0)
    if crop_p > 0.0:
        factor = crop_p / 100.0
        vf.append(f"crop=iw*(1-{factor:.4f}):ih*(1-{factor:.4f})")
        vf.append("scale=iw:ih") # scale back to restore original dimensions
        
    # 3. Geometry - Flip
    if cfg.get("mirror", False):
        vf.append("hflip")
        
    # 4. Color adjustments (brightness, contrast, saturation)
    b = cfg.get("brightness", 0.0)
    c = cfg.get("contrast", 1.0)
    s = cfg.get("saturation", 1.0)
    if b != 0.0 or c != 1.0 or s != 1.0:
        vf.append(f"eq=brightness={b:.3f}:contrast={c:.3f}:saturation={s:.3f}")
        
    # 5. Noise injection
    noise_str = cfg.get("noise_strength", 0)
    if noise_str > 0:
        vf.append(f"noise=alls={noise_str}:allf=t+u")
        
    # 6. Time (Speed)
    speed = cfg.get("speed", 1.0)
    if speed != 1.0:
        # Video speed is setpts = PTS / speed
        vf.append(f"setpts=PTS/{speed:.3f}")
        
        # Audio tempo = speed
        if has_audio:
            # atempo limit in FFmpeg is [0.5, 2.0]
            # Since our limits are tight, a single filter is perfect
            af.append(f"atempo={speed:.3f}")
            
    # 7. Audio Volume
    vol = cfg.get("volume_db", 0.0)
    if vol != 0.0 and has_audio:
        af.append(f"volume={vol:.2f}dB")
        
    # If filter list is empty, add a null filter to maintain chain sanity in complex filters
    if not vf:
        vf.append("null")
    if has_audio and not af:
        af.append("anull")
        
    return vf, af
