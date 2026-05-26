import yaml
from pathlib import Path
from typing import Dict, Any

from ..core.config import PROFILES_DIR
from ..core.logging import setup_logger

logger = setup_logger("app.video.profiles")

def load_profile(profile_name: str) -> Dict[str, Any]:
    """
    Load YAML-based processing profile from profiles/ directory.
    Falls back to a safe dictionary if the profile doesn't exist.
    """
    profile_path = PROFILES_DIR / f"{profile_name}.yaml"
    if not profile_path.exists():
        logger.warning(f"Profile '{profile_name}' not found at {profile_path}. Falling back to default 'light_ab_test'")
        profile_path = PROFILES_DIR / "light_ab_test.yaml"
        
    if not profile_path.exists():
        # Hard fallback dictionary if even light_ab_test is missing
        logger.error("No profile files found. Returning minimal hardcoded settings.")
        return {
            "speed": {"enabled": True, "factor_min": 0.98, "factor_max": 1.02},
            "crop": {"enabled": True, "max_percent": 1},
            "color": {"enabled": True, "brightness_delta": [-0.02, 0.02], "contrast_delta": [-0.02, 0.02]},
            "noise": {"enabled": True, "strength": [1, 3]}
        }
        
    try:
        with open(profile_path, "r", encoding="utf-8") as f:
            profile_data = yaml.safe_load(f) or {}
        logger.info(f"Successfully loaded profile '{profile_name}' from {profile_path.name}")
        return profile_data
    except Exception as e:
        logger.error(f"Failed to parse profile '{profile_name}': {e}. Returning empty dictionary.")
        return {}
