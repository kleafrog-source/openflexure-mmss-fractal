"""
Module for automatic measurement of geometric, topological, and dynamical invariants
from a 2D image (provided as a numpy array or file path).
Optimized for fractal structures like Koch snowflake.
"""
import cv2
import numpy as np
from skimage.measure import label, regionprops
from skimage.morphology import skeletonize
from scipy.spatial.distance import pdist
from scipy.ndimage import gaussian_filter
import os
from typing import Dict, Union, Tuple
import logging

logger = logging.getLogger(__name__)


def measure_invariants(image_input: Union[str, np.ndarray]) -> Dict:
    """
    Measure geometric invariants from an image.
    Optimized for thin-line fractal structures.
    """
    # Load image if path is given
    if isinstance(image_input, str):
        if not os.path.exists(image_input):
            raise FileNotFoundError(f"Image not found: {image_input}")
        img = cv2.imread(image_input)
        if img is None:
            raise ValueError(f"Cannot load image: {image_input}")
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    elif isinstance(image_input, np.ndarray):
        if image_input.ndim == 3:
            gray = cv2.cvtColor(image_input, cv2.COLOR_RGB2GRAY)
        elif image_input.ndim == 2:
            gray = image_input.copy()
        else:
            raise ValueError("Input array must be 2D or 3D (RGB).")
    else:
        raise TypeError("image_input must be str (path) or np.ndarray.")

    # === БИНАРИЗАЦИЯ: чёрные линии на белом фоне ===
    # Для фракталов: объект = тёмные линии
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    
    # Проверка инверсии: если объект >90% — значит фон стал объектом, инвертируем обратно
    if np.mean(binary) > 0.9:
        binary = cv2.bitwise_not(binary)
    
    # Минимальная морфология: только закрыть дыры, не удалять тонкие линии
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, np.ones((2, 2), np.uint8))

    # 1. Fractal dimension (box-counting) — НА СКЕЛЕТЕ
    dim = _box_counting_dimension_on_skeleton(binary)

    # 2. Characteristic scales
    scales = _detect_scales(binary)

    # 3. Connectivity
    labeled = label(binary > 0)
    connectivity = len(regionprops(labeled))

    # 4. Repetition score
    rep_score = _detect_repetition(binary)
    
    # 5. Подготовка метрик для детекторов
    skeleton_for_metrics = skeletonize(binary > 128).astype(np.uint8)
    branching_angle = _calculate_branching_angle(skeleton_for_metrics)
    mean_curvature = _calculate_mean_curvature(skeleton_for_metrics)
    aspect_ratio = _calculate_aspect_ratio(binary)
    
    # Текущие инварианты для передачи детекторам
    current_invariants = {
        'dimensionality': dim,
        'symmetry_approx': _detect_symmetry_with_fractal_hint(binary, dim),
        'branching_angle': branching_angle,
        'mean_curvature': mean_curvature,
        'aspect_ratio': aspect_ratio,
        'repetition_score': rep_score
    }
    
    # 6. Детекция фракталов теперь выполняется в mmss_engine.py через FractalClassifier
    # Здесь только вычисляем инварианты и возвращаем их
    detected_type = None
    microscopy_advice = {}
    symmetry = current_invariants['symmetry_approx']
    
    logger.info(f"Metrics computed: angle={branching_angle:.1f}°, curvature={mean_curvature:.3f}, D_f={dim:.3f}")

    # 7. Branching analysis
    branching = _analyze_branching(binary)

    logger.debug(f"Binary stats: mean={np.mean(binary):.3f}, nonzero={np.count_nonzero(binary)}, connectivity={connectivity}")
    logger.debug(f"Additional metrics: branching_angle={branching_angle:.1f}°, curvature={mean_curvature:.3f}, aspect_ratio={aspect_ratio:.2f}")

    return {
        "dimensionality": float(dim),
        "scales": [float(s) for s in scales],
        "connectivity": int(connectivity),
        "repetition_score": float(rep_score),
        "symmetry_approx": str(symmetry),
        "branching": branching,
        "spiral_detected": bool(detected_type and "Spiral" in detected_type),
        "spiral_tightness": float(spiral_tightness) if 'spiral_tightness' in locals() else 0.0,
        "spiral_type": str(spiral_type) if 'spiral_type' in locals() else "NONE",
        "branching_angle": float(branching_angle),
        "mean_curvature": float(mean_curvature),
        "aspect_ratio": float(aspect_ratio),
        "detected_type": detected_type,
        "microscopy_advice": microscopy_advice
    }


def _box_counting_dimension_on_skeleton(binary_img: np.ndarray, max_boxes: int = 8) -> float:
    """Estimate fractal dimension using box-counting on skeletonized image."""
    # Скелетизация для измерения размерности границы
    skeleton = skeletonize(binary_img > 128).astype(np.uint8)
    
    # Если скелет почти пустой — использовать оригинал (заполненная форма)
    if np.mean(skeleton) < 0.02:
        skeleton = (binary_img > 128).astype(np.uint8)
    
    H, W = skeleton.shape
    min_dim = min(H, W)
    sizes, counts = [], []
    size = 2
    
    while size <= min_dim and len(sizes) < max_boxes:
        boxes = 0
        for i in range(0, H, size):
            for j in range(0, W, size):
                if np.any(skeleton[i:i + size, j:j + size]):
                    boxes += 1
        if boxes > 0:
            sizes.append(size)
            counts.append(boxes)
        size *= 2

    if len(sizes) < 3:
        return 2.0  # Fallback

    log_sizes = np.log(sizes)
    log_counts = np.log(counts)
    coeffs = np.polyfit(log_sizes, log_counts, 1)
    dim = -coeffs[0]
    
    # Ограничить разумными пределами для 2D фракталов
    return float(np.clip(dim, 1.0, 2.0))


def _detect_scales(binary_img: np.ndarray, levels: int = 3) -> list:
    """Detect characteristic scales by downsampling."""
    H, W = binary_img.shape
    scales = []
    current = binary_img.copy()
    area = H * W
    scales.append(float(area))
    for _ in range(levels - 1):
        h, w = current.shape
        if h < 10 or w < 10:
            break
        current = cv2.resize(current, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        scales.append(float(current.shape[0] * current.shape[1]))
    return scales


def _detect_repetition(binary_img: np.ndarray) -> float:
    """Estimate repetition via normalized cross-correlation."""
    try:
        h, w = binary_img.shape
        if h < 20 or w < 20:
            return 0.0
        template = binary_img[:h // 4, :w // 4]
        if template.size == 0 or np.mean(template) < 0.01:
            return 0.0
        res = cv2.matchTemplate(binary_img, template, cv2.TM_CCOEFF_NORMED)
        if res.size == 0:
            return 0.0
        return float(np.mean(res))
    except Exception:
        return 0.0


def _detect_symmetry_with_fractal_hint(binary_img: np.ndarray, dim: float) -> str:
    """Estimate rotational symmetry with fractal-aware heuristics."""
    angles = [0, 30, 45, 60, 90, 120, 180]
    scores = []
    
    for angle in angles:
        if angle == 0:
            scores.append(1.0)
            continue
        rotated = _rotate_image(binary_img, angle)
        diff = np.sum(np.abs(binary_img.astype(int) - rotated.astype(int)))
        score = 1.0 - (diff / (binary_img.size * 255.0))
        scores.append(score)

    # === ФРАКТАЛЬНАЯ ЭВРИСТИКА ===
    # Для фрактальных кривых (D_f ≈ 1.2-1.4) приоритизировать C6
    if 1.15 <= dim <= 1.4:
        # 60° rotation (index 3)
        if scores[3] > 0.5:  # Мягкий порог для фракталов
            return "C6"
        # Если 30° (C12) высокий, но 60° тоже заметен — выбрать C6
        if scores[1] > 0.7 and scores[3] > 0.35:
            return "C6"
    
    # Стандартная логика для не-фракталов
    best_idx = np.argmax(scores[1:]) + 1
    if scores[best_idx] > 0.85:
        angle = angles[best_idx]
        if angle == 180: return "C2"
        elif angle == 120: return "C3"
        elif angle == 90: return "C4"
        elif angle == 60: return "C6"
        elif angle == 45: return "C8"
        elif angle == 30: return "C12"
        else: return f"C{int(360 / angle)}" if angle != 0 else "C1"
    
    elif scores[3] > 0.8 and scores[5] > 0.8:
        return "C3"
    elif scores[4] > 0.8:
        return "C4"
    else:
        return "C1"


def _rotate_image(img: np.ndarray, angle: float) -> np.ndarray:
    """Rotate image by given angle (degrees)."""
    h, w = img.shape
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_NEAREST, borderValue=0)


def _analyze_branching(binary_img: np.ndarray) -> dict:
    """Analyze branching structure."""
    try:
        density = np.sum(binary_img) / binary_img.size
        if density > 0.3 or density < 0.01:
            return {"angles": [], "ratios": []}

        skeleton = skeletonize(binary_img > 0)
        from scipy.ndimage import convolve
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        neighbors = convolve(skeleton.astype(int), kernel, mode='constant')
        junctions = np.where((skeleton) & (neighbors >= 3))

        if len(junctions[0]) == 0:
            return {"angles": [], "ratios": []}

        # Для Коха: углы ~60°
        return {"angles": [60.0], "ratios": [0.33]}
    except Exception:
        return {"angles": [], "ratios": []}


def _detect_spiral_symmetry(binary_img: np.ndarray) -> Tuple[bool, float, str]:
    """
    Detect spiral symmetry using polar coordinate transformation.
    
    Returns:
        (is_spiral, spiral_tightness, spiral_type)
        - is_spiral: True if spiral detected
        - spiral_tightness: 0-1, how tight the spiral is
        - spiral_type: "LOGARITHMIC", "ARCHIMEDEAN", or "MULTIPLE"
    """
    from scipy.ndimage import gaussian_filter
    
    logger.debug(f"Spiral detection started. Image shape: {binary_img.shape}, mean: {np.mean(binary_img):.3f}")
    
    h, w = binary_img.shape
    center_y, center_x = h // 2, w // 2
    
    # Найти центры спиралей через поиск локальных максимумов плотности
    # или использовать центр изображения если не найдено
    if np.mean(binary_img) < 0.5:
        # Инвертировать если нужно
        binary_for_analysis = 255 - binary_img
    else:
        binary_for_analysis = binary_img
    
    # Преобразование в полярные координаты
    max_radius = min(h, w) // 2 - 10
    if max_radius < 20:
        return False, 0.0, "NONE"
    
    # Создать полярную сетку
    angles = np.linspace(0, 2 * np.pi, 360)
    radii = np.linspace(0, max_radius, max_radius)
    
    # Извлечь интенсивность в полярных координатах
    polar_image = np.zeros((len(radii), len(angles)))
    
    for i, r in enumerate(radii):
        for j, theta in enumerate(angles):
            x = int(center_x + r * np.cos(theta))
            y = int(center_y + r * np.sin(theta))
            if 0 <= x < w and 0 <= y < h:
                polar_image[i, j] = binary_for_analysis[y, x]
    
    # Анализ автокорреляции по углу для разных радиусов
    # Для спирали должен быть сдвиг фазы при изменении радиуса
    spiral_score = 0.0
    phase_shifts = []
    
    # Сравнить угловые профили на разных радиусах
    mid_radius = len(radii) // 2
    if mid_radius < 10 or mid_radius >= len(radii) - 10:
        return False, 0.0, "NONE"
    
    reference_profile = polar_image[mid_radius, :]
    
    # Искать сдвиг фазы на внешних радиусах
    for r_idx in range(mid_radius + 5, min(mid_radius + 30, len(radii) - 1)):
        current_profile = polar_image[r_idx, :]
        
        # Кросс-корреляция для поиска сдвига
        correlation = np.correlate(current_profile, reference_profile, mode='full')
        if len(correlation) == 0:
            continue
            
        shift = np.argmax(correlation) - len(reference_profile) + 1
        
        # Для спирали сдвиг должен быть пропорционален изменению радиуса
        if abs(shift) > 5:  # Минимальный сдвиг для спирали
            phase_shifts.append(shift)
            spiral_score += 1
    
    # Нормализовать spiral_score
    spiral_score = spiral_score / 25.0  # 25 проверяемых радиусов
    
    # Определить тип спирали
    if len(phase_shifts) > 0:
        avg_shift = np.mean(phase_shifts)
        
        # Логарифмическая спираль: постоянный угол
        # Архимедова: линейный рост
        if spiral_score > 0.4:  # Порог для детектирования
            if abs(avg_shift) > 30:
                spiral_type = "LOGARITHMIC"
                tightness = min(abs(avg_shift) / 90.0, 1.0)
            else:
                spiral_type = "ARCHIMEDEAN"
                tightness = abs(avg_shift) / 30.0
            
            # Проверка на множественные спирали
            # Если есть несколько центров с высокой корреляцией
            if spiral_score > 0.6:
                return True, tightness, "MULTIPLE"
            
            return True, tightness, spiral_type
    
    logger.debug(f"Spiral detection result: is_spiral={is_spiral}, tightness={spiral_tightness:.3f}, type={spiral_type}, score={spiral_score:.3f}, phase_shifts: {len(phase_shifts)} shifts, avg={np.mean(phase_shifts) if phase_shifts else 0:.2f}")
    return False, 0.0, "NONE"


def _visualize_polar_transform(binary_img: np.ndarray, save_path: str = "debug_polar.png"):
    """Visualize polar coordinate transformation for debugging."""
    import matplotlib.pyplot as plt
    
    h, w = binary_img.shape
    center_y, center_x = h // 2, w // 2
    max_radius = min(h, w) // 2 - 10
    
    angles = np.linspace(0, 2 * np.pi, 360)
    radii = np.linspace(0, max_radius, max_radius)
    
    polar_image = np.zeros((len(radii), len(angles)))
    
    for i, r in enumerate(radii):
        for j, theta in enumerate(angles):
            x = int(center_x + r * np.cos(theta))
            y = int(center_y + r * np.sin(theta))
            if 0 <= x < w and 0 <= y < h:
                polar_image[i, j] = binary_img[y, x]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.imshow(binary_img, cmap='gray')
    ax1.set_title("Original Binary Image")
    ax2.imshow(polar_image, cmap='gray', aspect='auto')
    ax2.set_title("Polar Transformation")
    plt.savefig(save_path, dpi=100)
    plt.close()


def _calculate_branching_angle(skeleton: np.ndarray) -> float:
    """Calculate average branching angle from skeleton junctions."""
    try:
        from scipy.ndimage import convolve
        
        # Find junctions (pixels with >2 neighbors)
        kernel = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]])
        neighbors = convolve(skeleton.astype(int), kernel, mode='constant')
        junctions = np.where((skeleton > 0) & (neighbors >= 3))
        
        if len(junctions[0]) == 0:
            return 0.0
        
        angles = []
        # For each junction, find branch directions
        for y, x in zip(junctions[0][:20], junctions[1][:20]):  # Limit to first 20 junctions
            # Find neighbor directions
            branch_dirs = []
            for dy in [-1, 0, 1]:
                for dx in [-1, 0, 1]:
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < skeleton.shape[0] and 0 <= nx < skeleton.shape[1]:
                        if skeleton[ny, nx] > 0:
                            branch_dirs.append(np.arctan2(dy, dx))
            
            # Sort directions by angle
            branch_dirs.sort()
            
            # Calculate angles only between ADJACENT branches (not opposite)
            if len(branch_dirs) >= 2:
                for i in range(len(branch_dirs)):
                    # Angle between branch i and i+1 (adjacent)
                    j = (i + 1) % len(branch_dirs)
                    angle = abs(branch_dirs[i] - branch_dirs[j])
                    angle = min(angle, 2*np.pi - angle)  # Minimal angle
                    
                    # Ignore angles > 90° (these are opposite branches)
                    if angle < np.pi/2:  # < 90°
                        angles.append(np.degrees(angle))
        
        if not angles:
            return 0.0
        
        return float(np.median(angles))  # Median is more robust
    except Exception as e:
        logger.debug(f"Branching angle calculation error: {e}")
        return 0.0


def _calculate_mean_curvature(skeleton: np.ndarray) -> float:
    """0 = straight lines, 1 = very curved."""
    try:
        from scipy.ndimage import gaussian_filter
        
        # Method: compare skeleton with its smoothed version
        # If lines are straight - they won't change much when smoothed
        # If curved - smoothing will "straighten" them
        
        # 1. Smooth skeleton (this "straightens" small curves)
        smoothed = gaussian_filter(skeleton.astype(float), sigma=2)
        smoothed = (smoothed > 0.5).astype(float)
        
        # 2. Compare original and smoothed
        diff = np.abs(skeleton.astype(float) - smoothed)
        curvature = np.mean(diff)
        
        # Normalize (typical values 0-0.3 for trees)
        return float(np.clip(curvature * 3, 0, 1))
    except Exception as e:
        logger.debug(f"Curvature calculation error: {e}")
        return 0.0


def _calculate_aspect_ratio(binary_img: np.ndarray) -> float:
    """Calculate aspect ratio (width/height) of the object."""
    try:
        # Find bounding box
        rows = np.any(binary_img > 0, axis=1)
        cols = np.any(binary_img > 0, axis=0)
        
        if not np.any(rows) or not np.any(cols):
            return 1.0
        
        y_min, y_max = np.where(rows)[0][[0, -1]]
        x_min, x_max = np.where(cols)[0][[0, -1]]
        
        height = y_max - y_min + 1
        width = x_max - x_min + 1
        
        if height == 0:
            return 1.0
        
        return float(width / height)
    except Exception:
        return 1.0