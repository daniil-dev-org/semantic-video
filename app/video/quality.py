import cv2
import numpy as np
import time
from pathlib import Path
from typing import Dict, Any, List

from ..core.logging import setup_logger

logger = setup_logger("app.video.quality")

def compute_phash(image: np.ndarray) -> int:
    """
    Compute a 64-bit 2D Discrete Cosine Transform (DCT) Perceptual Hash.
    Resizes image to 32x32, converts to gray, runs DCT, and hashes top-left 8x8.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    resized = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(resized.astype(np.float32))
    
    # Extract the top-left 8x8 DCT coefficients (excluding DC term)
    dct_8x8 = dct[:8, :8]
    median_val = np.median(dct_8x8)
    
    hash_val = 0
    for i in range(8):
        for j in range(8):
            hash_val = (hash_val << 1) | (1 if dct_8x8[i, j] > median_val else 0)
    return hash_val

def hamming_distance(h1: int, h2: int) -> int:
    """Calculate the Hamming distance (differing bits) between two 64-bit integers."""
    return bin(h1 ^ h2).count("1")

def compute_ssim(img1: np.ndarray, img2: np.ndarray) -> float:
    """
    Compute Gaussian-weighted Structural Similarity (SSIM) index.
    Accurately measures structural degradation.
    """
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)
        
    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    
    x = gray1.astype(np.float32) / 255.0
    y = gray2.astype(np.float32) / 255.0
    
    # Standard SSIM constants
    C1 = 0.01 ** 2
    C2 = 0.03 ** 2
    
    mu_x = cv2.GaussianBlur(x, (11, 11), 1.5)
    mu_y = cv2.GaussianBlur(y, (11, 11), 1.5)
    
    mu_x_sq = mu_x ** 2
    mu_y_sq = mu_y ** 2
    mu_xy = mu_x * mu_y
    
    sigma_x_sq = cv2.GaussianBlur(x ** 2, (11, 11), 1.5) - mu_x_sq
    sigma_y_sq = cv2.GaussianBlur(y ** 2, (11, 11), 1.5) - mu_y_sq
    sigma_xy = cv2.GaussianBlur(x * y, (11, 11), 1.5) - mu_xy
    
    num = (2 * mu_xy + C1) * (2 * sigma_xy + C2)
    den = (mu_x_sq + mu_y_sq + C1) * (sigma_x_sq + sigma_y_sq + C2)
    
    ssim_map = num / den
    return float(np.mean(ssim_map))

def compute_psnr(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute Peak Signal-to-Noise Ratio (PSNR) between two images."""
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)
        
    mse = np.mean((img1.astype(np.float32) - img2.astype(np.float32)) ** 2)
    if mse == 0:
        return 100.0
    return 20.0 * np.log10(255.0 / np.sqrt(mse))

def compute_histogram_distance(img1: np.ndarray, img2: np.ndarray) -> float:
    """Compute normalized color histogram correlation per BGR channel."""
    if img1.shape != img2.shape:
        img2 = cv2.resize(img2, (img1.shape[1], img1.shape[0]), interpolation=cv2.INTER_AREA)
        
    correlations = []
    for ch in range(3):
        h1 = cv2.calcHist([img1], [ch], None, [256], [0, 256])
        h2 = cv2.calcHist([img2], [ch], None, [256], [0, 256])
        cv2.normalize(h1, h1, 0, 1, cv2.NORM_MINMAX)
        cv2.normalize(h2, h2, 0, 1, cv2.NORM_MINMAX)
        corr = cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)
        correlations.append(corr)
    return float(np.mean(correlations))

def compare_videos(
    orig_path: Path,
    var_path: Path,
    sample_frames: int = 5
) -> Dict[str, Any]:
    """
    Compare original video with variant video by sampling evenly spaced frames.
    Computes SSIM, PSNR, pHash, histogram similarity, and size/duration deltas.
    """
    t0 = time.perf_counter()
    
    cap_orig = cv2.VideoCapture(str(orig_path))
    cap_var = cv2.VideoCapture(str(var_path))
    
    if not cap_orig.isOpened() or not cap_var.isOpened():
        raise RuntimeError("Failed to open video files for quality assessment.")
        
    len_orig = int(cap_orig.get(cv2.CAP_PROP_FRAME_COUNT))
    len_var = int(cap_var.get(cv2.CAP_PROP_FRAME_COUNT))
    
    fps_orig = cap_orig.get(cv2.CAP_PROP_FPS) or 25.0
    fps_var = cap_var.get(cv2.CAP_PROP_FPS) or 25.0
    
    dur_orig_ms = int((len_orig / fps_orig) * 1000)
    dur_var_ms = int((len_var / fps_var) * 1000)
    
    # Pick sample indices
    indices_orig = [int(len_orig * i / (sample_frames + 1)) for i in range(1, sample_frames + 1)]
    indices_var = [int(len_var * i / (sample_frames + 1)) for i in range(1, sample_frames + 1)]
    
    ssims = []
    psnrs = []
    hist_similarities = []
    phash_distances = []
    
    for i in range(sample_frames):
        # Read original frame
        cap_orig.set(cv2.CAP_PROP_POS_FRAMES, indices_orig[i])
        ret1, frame_orig = cap_orig.read()
        
        # Read variant frame
        cap_var.set(cv2.CAP_PROP_POS_FRAMES, indices_var[i])
        ret2, frame_var = cap_var.read()
        
        if not ret1 or not ret2:
            continue
            
        # Compute metrics
        ssims.append(compute_ssim(frame_orig, frame_var))
        psnrs.append(compute_psnr(frame_orig, frame_var))
        hist_similarities.append(compute_histogram_distance(frame_orig, frame_var))
        
        h1 = compute_phash(frame_orig)
        h2 = compute_phash(frame_var)
        phash_distances.append(hamming_distance(h1, h2))
        
    cap_orig.release()
    cap_var.release()
    
    # Calculate averages
    avg_ssim = round(float(np.mean(ssims)), 3) if ssims else 1.0
    avg_psnr = round(float(np.mean(psnrs)), 1) if psnrs else 100.0
    avg_hist = round(float(np.mean(hist_similarities)), 3) if hist_similarities else 1.0
    avg_phash_dist = round(float(np.mean(phash_distances)), 1) if phash_distances else 0.0
    
    # Compute size delta
    size_orig = orig_path.stat().st_size
    size_var = var_path.stat().st_size
    size_ratio = round(size_var / size_orig, 2) if size_orig > 0 else 1.0
    
    # Compute duration delta percent
    duration_delta_pct = round(abs(dur_orig_ms - dur_var_ms) / (dur_orig_ms or 1) * 100, 2)
    
    # A composite quality score (0.0 to 1.0)
    # Excellent visual similarity if SSIM > 0.85 and average pHash Hamming distance is low
    quality_score = round(max(0.0, min(1.0, (avg_ssim * 0.5 + avg_hist * 0.3 + (1.0 - avg_phash_dist/64.0) * 0.2))), 3)
    
    # Define A/B viability acceptance:
    # 1. Video structures must not be completely distorted (SSIM >= 0.70)
    # 2. Key features remain perceptually matching (phash distance < 18)
    accepted = avg_ssim >= 0.70 and avg_phash_dist < 18.0
    
    elapsed = time.perf_counter() - t0
    logger.info(
        f"Compared {orig_path.name} vs {var_path.name} "
        f"(SSIM={avg_ssim:.2f}, PSNR={avg_psnr:.1f}dB, pHashDist={avg_phash_dist:.1f}, "
        f"quality={quality_score:.2f}, accepted={accepted}) in {elapsed:.2f}s"
    )
    
    return {
        "variant": var_path.name,
        "visual_similarity": avg_ssim,
        "psnr_db": avg_psnr,
        "color_histogram_distance": avg_hist,
        "phash_distance": avg_phash_dist,
        "duration_delta_percent": duration_delta_pct,
        "compression_ratio": size_ratio,
        "quality_score": quality_score,
        "accepted": bool(accepted)
    }
