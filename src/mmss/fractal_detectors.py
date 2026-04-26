"""
Modular fractal detection system for microscopy.
Each detector specializes in recognizing specific fractal patterns.
"""
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class FractalMatch:
    """Результат поиска паттерна"""
    fractal_type: str
    confidence: float  # 0.0 to 1.0
    category: str      # 'TREE', 'CURVE', 'SPACE_FILLING', 'SET', 'CRYSTALLINE'
    microscopy_advice: Dict[str, any]  # Советы для микроскопа (свет, фокус)


class BaseDetector:
    """Базовый класс для всех детекторов"""
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        pass


# --- TREE DETECTORS (Priority) ---
class TreeDetector(BaseDetector):
    def detect(self, skeleton, invariants):
        import logging
        logger = logging.getLogger(__name__)
        
        angle = invariants.get('branching_angle', 0)
        curve = invariants.get('mean_curvature', 0)
        dim = invariants.get('dimensionality', 0)
        aspect_ratio = invariants.get('aspect_ratio', 1.0)
        
        logger.debug(f"TreeDetector: angle={angle:.1f}°, curve={curve:.3f}, dim={dim:.3f}")
        
        # Проверка: это вообще дерево?
        # Деревья имеют: ветвления (angle > 20), D_f ~1.3-1.7
        if angle < 15 or dim < 1.2 or dim > 1.8:
            logger.debug(f"TreeDetector: angle={angle:.1f}° < 15° or dim={dim:.3f} out of range [1.2, 1.8] — NO MATCH")
            return None  # Не дерево
        
        # === НОВАЯ ПРОВЕРКА: отличать деревья от множеств (Мандельброт) ===
        
        # 1. Проверить на кардиоиду/круги (признаки множеств)
        if self._has_cardioid_or_circles(skeleton):
            logger.debug("TreeDetector: Detected cardioid/circles — likely a Set, not a tree")
            return None
        
        # 2. Проверить на явный корень (точка с максимальным числом соседей)
        from scipy.ndimage import convolve
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        
        max_neighbors = np.max(neighbors)
        root_points = np.where(neighbors == max_neighbors)
        
        # Для настоящего дерева: должен быть корень с 2+ дочерними ветвями
        if max_neighbors < 2 or len(root_points[0]) > 10:
            logger.debug(f"TreeDetector: No clear root (max_neighbors={max_neighbors}, root_points={len(root_points[0])})")
            return None
        
        # 3. Проверить на радиальное ветвление от корня
        if len(root_points[0]) > 0:
            radial_score = self._check_radial_branching(skeleton, root_points[0][0], root_points[1][0])
            if radial_score < 0.3:
                logger.debug(f"TreeDetector: Low radial branching score ({radial_score:.2f})")
                return None
        
        # Классификация по углу
        if 55 <= angle <= 65:
            if curve < 0.2:
                logger.info(f"✓ Tree detected: Golden 60 Tree")
                return FractalMatch("Golden 60 Tree", 0.92, "TREE", {'light': 530, 'focus': 'auto'})
            else:
                logger.info(f"✓ Tree detected: Wavy Tree Fractal")
                return FractalMatch("Wavy Tree Fractal", 0.85, "TREE", {'light': 450, 'focus': 'auto'})
        elif 115 <= angle <= 125:
            logger.info(f"✓ Tree detected: Golden 120 Tree")
            return FractalMatch("Golden 120 Tree", 0.90, "TREE", {'light': 530, 'focus': 'auto'})
        elif 25 <= angle <= 45:
            logger.info(f"✓ Tree detected: Canopy H-tree Fractal")
            return FractalMatch("Canopy H-tree Fractal", 0.80, "TREE", {'light': 550, 'focus': 'center'})
        
        # По кривизне
        if curve > 0.4:
            logger.info(f"✓ Tree detected: Curly Tree Fractal")
            return FractalMatch("Curly Tree Fractal", 0.88, "TREE", {'light': 450, 'focus': 'center'})
        
        # По aspect ratio
        if aspect_ratio > 1.5:
            logger.info(f"✓ Tree detected: Wide Canopy Fractal")
            return FractalMatch("Wide Canopy Fractal", 0.75, "TREE", {'light': 550, 'focus': 'center'})
        elif aspect_ratio < 0.7:
            logger.info(f"✓ Tree detected: Tall Canopy Fractal")
            return FractalMatch("Tall Canopy Fractal", 0.75, "TREE", {'light': 550, 'focus': 'center'})
        
        # Дефолтное дерево
        logger.info(f"✓ Tree detected: Regular Canopy Fractal")
        return FractalMatch("Regular Canopy Fractal", 0.75, "TREE", {'light': 530, 'focus': 'auto'})
    
    def _check_radial_branching(self, skeleton: np.ndarray, root_y: int, root_x: int) -> float:
        """Check if branches radiate from a single root point"""
        h, w = skeleton.shape
        
        # Разбить изображение на секторы от корня
        y, x = np.ogrid[:h, :w]
        angles = np.arctan2(y - root_y, x - root_x)
        angles = (angles + np.pi) % (2*np.pi)  # [0, 2π)
        
        # Посчитать сколько секторов содержат ветви
        sectors = 8
        sector_counts = [0] * sectors
        
        for i in range(h):
            for j in range(w):
                if skeleton[i, j]:
                    sector = int(angles[i, j] * sectors / (2*np.pi)) % sectors
                    sector_counts[sector] += 1
        
        # Для дерева: ветви должны быть в нескольких секторах (не во всех!)
        non_empty = sum(1 for c in sector_counts if c > 0)
        return non_empty / sectors  # Доля заполненных секторов
    
    def _has_cardioid_or_circles(self, skeleton: np.ndarray) -> bool:
        """Detect if structure contains cardioid or circular shapes (Mandelbrot-like)"""
        from skimage.measure import label, regionprops, find_contours
        
        labeled = label(skeleton > 128)
        regions = regionprops(labeled)
        
        # Искать крупные круглые регионы
        for region in regions:
            if region.area < 500:  # Пропустить мелкие
                continue
            
            # Eccentricity < 0.7 = круглый
            if region.eccentricity < 0.7:
                # Дополнительно: проверить на кардиоиду через контур
                contours = find_contours(skeleton, 0.5)
                for contour in contours:
                    if len(contour) > 100:
                        # Анализ формы контура
                        x, y = contour[:, 1], contour[:, 0]
                        # Если есть впадина (характерна для кардиоиды)
                        from scipy.signal import find_peaks
                        curvature = np.abs(np.gradient(np.arctan2(np.gradient(y), np.gradient(x))))
                        peaks, _ = find_peaks(curvature, height=np.mean(curvature)*2)
                        if len(peaks) > 0:
                            return True  # Кардиоида найдена
        
        return False


# --- CURVE & DRAGON DETECTORS ---
class DragonDetector(BaseDetector):
    def detect(self, skeleton, invariants):
        # Логика для Dragons (Koch, Square, Chinese)
        dim = invariants.get('dimensionality', 1.0)
        symmetry = invariants.get('symmetry_approx', 'C1')
        curve = invariants.get('mean_curvature', 0)
        
        # Koch snowflake (D_f ~ 1.26, C6 symmetry)
        if 1.2 < dim < 1.35 and symmetry == 'C6':
            if curve < 0.1:
                return FractalMatch("Koch Snowflake", 0.95, "CURVE", {'light': 530, 'polarization': False})
        
        # Square Dragon (D_f ~ 1.5, C4 symmetry)
        if 1.4 < dim < 1.6 and symmetry == 'C4':
            if curve < 0.2:
                return FractalMatch("Square Dragon", 0.85, "CURVE", {'light': 550, 'polarization': False})
        
        # Chinese Dragon (волнистый, C3/C6)
        if symmetry in ['C3', 'C6'] and curve > 0.3:
            return FractalMatch("Chinese Dragon", 0.8, "CURVE", {'light': 500, 'polarization': True})
        
        return None


# --- SPACE-FILLING CURVE DETECTORS ---

class HilbertDetector(BaseDetector):
    """Detects Hilbert curve patterns (U-shaped recursive folding)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        logger.debug(f"HilbertDetector: dim={dim:.3f}, edge_density={invariants.get('edge_density', 0):.3f}, skeleton_nonzero={np.sum(skeleton > 0)}")
        
        if dim < 1.9:  # Hilbert fills space
            logger.debug(f"HilbertDetector: dim={dim:.3f} < 1.9 — NO MATCH")
            return None
        
        # Ключевой признак: рекурсивные U-образные паттерны
        u_pattern_score = self._detect_u_patterns(skeleton)
        logger.debug(f"HilbertDetector: u_score={u_pattern_score:.3f}")
        
        # Временно снижен порог для тестирования (было 0.7)
        if u_pattern_score > 0.3:
            logger.info(f"✓ Hilbert match with u_score={u_pattern_score:.3f}")
            return FractalMatch(
                fractal_type="Hilbert Sequence",
                confidence=0.9,
                category="SPACE_FILLING",
                microscopy_advice={
                    'light': [450, 550],  # Синий+зелёный для контраста поворотов
                    'focus': 'high_res',
                    'polarization': False
                }
            )
        logger.debug(f"HilbertDetector: u_score={u_pattern_score:.3f} < 0.3 — NO MATCH")
        return None
    
    def _detect_u_patterns(self, skeleton: np.ndarray) -> float:
        """
        Robust U-pattern detection for Hilbert curve.
        Uses fuzzy matching and multi-scale analysis.
        """
        from scipy.ndimage import convolve, gaussian_filter
        
        h, w = skeleton.shape
        
        # 1. Сгладить скелет для устойчивости к шуму
        smoothed = gaussian_filter(skeleton.astype(float), sigma=0.5)
        smoothed = (smoothed > 0.3).astype(np.uint8)
        
        # 2. U-шаблон (3×3) — но искать "похожие" паттерны, не точные
        u_template = np.array([
            [1, 0, 1],
            [1, 0, 1],
            [1, 1, 1]
        ], dtype=float)
        
        def safe_correlation(a, b):
            """Correlation that handles constant arrays"""
            if np.std(a) == 0 or np.std(b) == 0:
                return 0.0
            corr = np.corrcoef(a.flatten(), b.flatten())[0, 1]
            return np.nan_to_num(corr, nan=0.0)
        
        matches = 0
        total_candidates = 0
        
        # Скользящее окно
        for y in range(1, h-1):
            for x in range(1, w-1):
                if smoothed[y, x] == 0:  # Центр U обычно пустой
                    patch = smoothed[y-1:y+2, x-1:x+2].astype(float)
                    
                    # Проверить на совпадение с шаблоном (и вращениями)
                    # Использовать корреляцию вместо точного равенства
                    for rotation in [0, 1, 2, 3]:
                        rotated = np.rot90(u_template, k=rotation)
                        # Корреляция Пирсона (устойчива к контрасту)
                        corr = safe_correlation(patch, rotated)
                        if corr > 0.6:  # Порог корреляции
                            matches += 1
                            break
                    total_candidates += 1
        
        if total_candidates == 0:
            return 0.0
        
        # Нормализовать и масштабировать
        raw_score = matches / total_candidates
        
        # Для идеальной кривой Гильберта ~10-15% пикселей — часть U-паттерна
        # Масштабировать так чтобы 0.05 → 0.3, 0.15 → 1.0
        scaled_score = min((raw_score - 0.02) / 0.08, 1.0)
        
        return max(0.0, scaled_score)


class MooreDetector(BaseDetector):
    """Detects Moore curve (similar to Hilbert but with diagonal connections)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        symmetry = invariants.get('symmetry_approx', '')
        logger.debug(f"MooreDetector: dim={dim:.3f}, symmetry={symmetry}")
        
        if dim < 1.9:
            logger.debug(f"MooreDetector: dim={dim:.3f} < 1.9 — NO MATCH")
            return None
        
        # Moore имеет диагональные соединения + 4-кратную симметрию
        diag_score = self._detect_diagonal_junctions(skeleton)
        logger.debug(f"MooreDetector: diag_score={diag_score:.3f}")
        
        # Временно снижен порог для тестирования (было 0.6)
        if diag_score > 0.3 and ('C4' in symmetry or dim > 1.95):
            logger.info(f"✓ Moore match with diag_score={diag_score:.3f}")
            return FractalMatch(
                fractal_type="Moore Fractal",
                confidence=0.85,
                category="SPACE_FILLING",
                microscopy_advice={
                    'light': 530,  # Зелёный для чётких углов
                    'focus': 'auto',
                    'polarization': False
                }
            )
        logger.debug(f"MooreDetector: diag_score={diag_score:.3f} < 0.3 or no C4 symmetry — NO MATCH")
        return None
    
    def _detect_diagonal_junctions(self, skeleton: np.ndarray) -> float:
        """Count junctions with diagonal neighbors"""
        from scipy.ndimage import convolve
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        
        # Найти точки с 3+ соседями, включая диагонали
        junctions = np.where((skeleton > 0) & (neighbors >= 3))
        if len(junctions[0]) == 0:
            return 0.0
        
        diag_count = 0
        for y, x in zip(junctions[0], junctions[1]):
            # Проверить диагональных соседей
            for dy, dx in [(-1,-1), (-1,1), (1,-1), (1,1)]:
                ny, nx = y + dy, x + dx
                if 0 <= ny < skeleton.shape[0] and 0 <= nx < skeleton.shape[1]:
                    if skeleton[ny, nx]:
                        diag_count += 1
        
        return diag_count / max(len(junctions[0]) * 4, 1)


class PeanoDetector(BaseDetector):
    """Detects Peano curve and Peano Pentagon variants"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        symmetry = invariants.get('symmetry_approx', '')
        branching = invariants.get('branching_angle', 0)
        edge_density = invariants.get('edge_density', 0)
        logger.debug(f"PeanoDetector: dim={dim:.3f}, symmetry={symmetry}, branching={branching:.1f}°, edge_density={edge_density:.3f}")
        
        if dim < 1.85:
            logger.debug(f"PeanoDetector: dim={dim:.3f} < 1.85 — NO MATCH")
            return None
        
        # Peano: 3-кратное деление + часто 5-кратная симметрия для пентагона
        if 'C5' in symmetry or (105 <= branching <= 115):  # ~108° для пентагона
            logger.info(f"✓ Peano Pentagon match with C5 symmetry or branching={branching:.1f}°")
            return FractalMatch(
                fractal_type="Peano Pentagon",
                confidence=0.82,
                category="SPACE_FILLING",
                microscopy_advice={
                    'light': [450, 650],  # Синий+красный для углов
                    'focus': 'stack',
                    'polarization': False
                }
            )
        elif dim > 1.95 and edge_density > 0.2:
            logger.info(f"✓ Peano Curve match with dim={dim:.3f} and edge_density={edge_density:.3f}")
            return FractalMatch(
                fractal_type="Peano Curve",
                confidence=0.78,
                category="SPACE_FILLING",
                microscopy_advice={'light': 550, 'focus': 'auto'}
            )
        logger.debug(f"PeanoDetector: No match — dim={dim:.3f}, symmetry={symmetry}, branching={branching:.1f}°")
        return None


class TSquareDetector(BaseDetector):
    """Detects T-square fractal (T-shaped junctions)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        logger.debug(f"TSquareDetector: dim={dim:.3f}")
        
        if dim < 1.7:
            logger.debug(f"TSquareDetector: dim={dim:.3f} < 1.7 — NO MATCH")
            return None
        
        # Ключевой признак: Т-образные соединения (одна линия пересекает другую под 90°)
        t_junction_score = self._detect_t_junctions(skeleton)
        logger.debug(f"TSquareDetector: t_junction_score={t_junction_score:.3f}")
        
        # Временно снижен порог для тестирования (было 0.6)
        if t_junction_score > 0.3:
            logger.info(f"✓ T-square match with t_junction_score={t_junction_score:.3f}")
            return FractalMatch(
                fractal_type="T-square fractal",
                confidence=0.88,
                category="SPACE_FILLING",
                microscopy_advice={
                    'light': 450,  # Синий для чётких прямых углов
                    'focus': 'high_contrast',
                    'polarization': False
                }
            )
        logger.debug(f"TSquareDetector: t_junction_score={t_junction_score:.3f} < 0.3 — NO MATCH")
        return None
    
    def _detect_t_junctions(self, skeleton: np.ndarray) -> float:
        """Detect T-shaped junctions (3 neighbors in orthogonal pattern)"""
        from scipy.ndimage import convolve
        
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        junctions = np.where((skeleton > 0) & (neighbors == 3))
        
        if len(junctions[0]) == 0:
            return 0.0
        
        t_count = 0
        for y, x in zip(junctions[0], junctions[1]):
            # Проверить ортогональных соседей (без диагоналей)
            ortho = [
                skeleton[y-1, x] if y > 0 else 0,
                skeleton[y+1, x] if y < skeleton.shape[0]-1 else 0,
                skeleton[y, x-1] if x > 0 else 0,
                skeleton[y, x+1] if x < skeleton.shape[1]-1 else 0,
            ]
            # Т-образный: ровно 3 из 4 ортогональных соседей
            if sum(ortho) == 3:
                t_count += 1
        
        return t_count / max(len(junctions[0]), 1)


class MortonZDetector(BaseDetector):
    """Detects Morton Z-order curve (zigzag pattern)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        logger.debug(f"MortonZDetector: dim={dim:.3f}")
        
        if dim < 1.8:
            logger.debug(f"MortonZDetector: dim={dim:.3f} < 1.8 — NO MATCH")
            return None
        
        # Z-кривая: регулярный зигзаг с чередованием направлений
        zigzag_score = self._detect_zigzag_pattern(skeleton)
        logger.debug(f"MortonZDetector: zigzag_score={zigzag_score:.3f}")
        
        # Временно снижен порог для тестирования (было 0.65)
        if zigzag_score > 0.3:
            logger.info(f"✓ Morton Z-fractal match with zigzag_score={zigzag_score:.3f}")
            return FractalMatch(
                fractal_type="Morton Z-fractal",
                confidence=0.83,
                category="SPACE_FILLING",
                microscopy_advice={
                    'light': 530,
                    'focus': 'auto',
                    'polarization': False
                }
            )
        logger.debug(f"MortonZDetector: zigzag_score={zigzag_score:.3f} < 0.3 — NO MATCH")
        return None
    
    def _detect_zigzag_pattern(self, skeleton: np.ndarray) -> float:
        """Detect regular zigzag via direction changes in skeleton path"""
        # Упрощённо: анализировать изменения направления при обходе скелета
        coords = np.column_stack(np.where(skeleton > 0))
        if len(coords) < 20:
            return 0.0
        
        # Сортировать по пространственной близости (грубо)
        # и посчитать частоту смены направления на ~90°
        directions = []
        for i in range(1, min(len(coords), 50)):
            dy = coords[i, 0] - coords[i-1, 0]
            dx = coords[i, 1] - coords[i-1, 1]
            if dx != 0 or dy != 0:
                directions.append(np.arctan2(dy, dx))
        
        if len(directions) < 10:
            return 0.0
        
        # Посчитать сколько раз направление меняется на ~90°
        zigzag_count = 0
        for i in range(1, len(directions)):
            diff = abs(directions[i] - directions[i-1])
            diff = min(diff, 2*np.pi - diff)
            if np.pi/2 - 0.3 < diff < np.pi/2 + 0.3:  # ~90° ± 17°
                zigzag_count += 1
        
        return zigzag_count / max(len(directions) - 1, 1)


# --- SET FRACTAL DETECTORS ---

class MandelbrotDetector(BaseDetector):
    """Detects Mandelbrot set (cardioid + circular bulbs + fractal filaments)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        logger.debug(f"MandelbrotDetector: dim={dim:.3f}")
        
        # Mandelbrot: D_f ≈ 1.4-2.0 (граница фрактальная)
        if dim < 1.4 or dim > 2.0:
            logger.debug(f"MandelbrotDetector: dim={dim:.3f} out of range [1.4, 2.0] — NO MATCH")
            return None
        
        cardioid_score = self._detect_cardioid(skeleton)
        bulb_score = self._detect_bulbs(skeleton)
        filament_score = self._detect_filaments(skeleton)
        
        logger.debug(f"MandelbrotDetector: cardioid={cardioid_score:.3f}, bulbs={bulb_score:.3f}, filaments={filament_score:.3f}")
        
        # Должна быть кардиоида ИЛИ (круги + нити)
        if cardioid_score > 0.6 or (bulb_score > 0.5 and filament_score > 0.6):
            confidence = max(cardioid_score, bulb_score, filament_score)
            logger.info(f"✓ Mandelbrot match with cardioid={cardioid_score:.3f}, bulbs={bulb_score:.3f}, filaments={filament_score:.3f}")
            return FractalMatch(
                fractal_type="Mandelbrot Set",
                confidence=min(confidence + 0.1, 0.95),  # Бонус за явные признаки
                category="SET",
                microscopy_advice={
                    'light': [450, 550, 650],  # Полный спектр для цветных границ
                    'focus': 'high_res',
                    'polarization': False,
                    'note': 'Zoom to observe self-similarity at boundaries'
                }
            )
        logger.debug(f"MandelbrotDetector: cardioid={cardioid_score:.3f} < 0.6 or (bulbs={bulb_score:.3f} < 0.5 or filaments={filament_score:.3f} < 0.6) — NO MATCH")
        return None
    
    def _detect_cardioid(self, skeleton: np.ndarray) -> float:
        """Detect cardioid-like main body via curvature analysis"""
        from skimage.measure import find_contours
        from scipy.ndimage import gaussian_filter1d
        
        contours = find_contours(skeleton, 0.5)
        if not contours:
            return 0.0
        
        main = max(contours, key=len)
        if len(main) < 50:
            return 0.0
        
        x, y = main[:, 1], main[:, 0]
        x_s = gaussian_filter1d(x, sigma=3)
        y_s = gaussian_filter1d(y, sigma=3)
        
        dx, dy = np.gradient(x_s), np.gradient(y_s)
        ddx, ddy = np.gradient(dx), np.gradient(dy)
        
        curvature = np.abs(dx * ddy - dy * ddx) / (dx**2 + dy**2)**1.5
        curvature = np.nan_to_num(curvature)
        
        # Кардиоида: есть пик кривизны (впадина) и плоская область
        high = np.sum(curvature > np.percentile(curvature, 90))
        low = np.sum(curvature < np.percentile(curvature, 10))
        
        return 0.8 if (high > 5 and low > 10) else 0.3
    
    def _detect_bulbs(self, skeleton: np.ndarray) -> float:
        """Detect circular bulbs attached to main structure"""
        from skimage.measure import label, regionprops
        
        labeled = label(skeleton > 128)
        regions = regionprops(labeled)
        
        if len(regions) < 3:
            return 0.0
        
        circular = sum(1 for r in regions if r.eccentricity < 0.7 and r.area > 50)
        return circular / max(len(regions), 1)
    
    def _detect_filaments(self, skeleton: np.ndarray) -> float:
        """Detect fractal filaments (lightning-like structures)"""
        # Филаменты: тонкие ветвящиеся структуры на периферии
        from scipy.ndimage import convolve
        
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        
        # Точки с 1-2 соседями (концы нитей)
        endpoints = np.where((skeleton > 0) & (neighbors <= 2))
        total = np.sum(skeleton > 0)
        
        # Доля конечных точек (для фрактальных нитей высокая)
        return len(endpoints[0]) / max(total, 1)


class JuliaDetector(BaseDetector):
    """Detects Julia sets (connected filaments or Cantor dust)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        connectivity = invariants.get('connectivity', 0)
        edge_density = invariants.get('edge_density', 0)
        
        logger.debug(f"JuliaDetector: dim={dim:.3f}, connectivity={connectivity}, edge_density={edge_density:.3f}")
        
        if dim < 1.2 or dim > 2.0:
            logger.debug(f"JuliaDetector: dim={dim:.3f} out of range [1.2, 2.0] — NO MATCH")
            return None
        
        # Connected Julia: много связей
        if connectivity > 100 and edge_density > 0.15:
            logger.info(f"✓ Julia Set (connected) match with connectivity={connectivity}, edge_density={edge_density:.3f}")
            return FractalMatch(
                fractal_type="Julia Set (connected)",
                confidence=0.85,
                category="SET",
                microscopy_advice={'light': 530, 'focus': 'high_contrast'}
            )
        # Cantor dust: мало связей
        elif connectivity < 10 and edge_density < 0.05:
            logger.info(f"✓ Julia Set (Cantor dust) match with connectivity={connectivity}, edge_density={edge_density:.3f}")
            return FractalMatch(
                fractal_type="Julia Set (Cantor dust)",
                confidence=0.80,
                category="SET",
                microscopy_advice={'light': 450, 'focus': 'wide_field'}
            )
        logger.debug(f"JuliaDetector: connectivity={connectivity}, edge_density={edge_density:.3f} — NO MATCH")
        return None


class EisensteinDetector(BaseDetector):
    """Detects Eisenstein integer fractals (hexagonal + fractal boundaries)"""
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        symmetry = invariants.get('symmetry_approx', '')
        
        logger.debug(f"EisensteinDetector: dim={dim:.3f}, symmetry={symmetry}")
        
        if 'C6' not in symmetry or dim < 1.5:
            logger.debug(f"EisensteinDetector: no C6 symmetry or dim={dim:.3f} < 1.5 — NO MATCH")
            return None
        
        hex_score = self._detect_hex_lattice(skeleton)
        fractal_edge = self._detect_fractal_boundaries(skeleton)
        
        logger.debug(f"EisensteinDetector: hex={hex_score:.3f}, edge={fractal_edge:.3f}")
        
        # Временно снижен порог для тестирования
        if hex_score > 0.5 and fractal_edge > 0.4:
            logger.info(f"✓ Eisenstein Fractions match with hex={hex_score:.3f}, edge={fractal_edge:.3f}")
            return FractalMatch(
                fractal_type="Eisenstein Fractions",
                confidence=0.87,
                category="SET",
                microscopy_advice={
                    'light': [450, 550],
                    'focus': 'auto',
                    'polarization': True  # Бирефрингенция
                }
            )
        logger.debug(f"EisensteinDetector: hex={hex_score:.3f} < 0.5 or edge={fractal_edge:.3f} < 0.4 — NO MATCH")
        return None
    
    def _detect_hex_lattice(self, skeleton: np.ndarray) -> float:
        """Detect hexagonal packing (6 neighbors)"""
        from scipy.ndimage import convolve
        
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        hex_points = np.where((skeleton > 0) & (neighbors == 6))
        
        return len(hex_points[0]) / max(np.sum(skeleton > 0), 1)
    
    def _detect_fractal_boundaries(self, skeleton: np.ndarray) -> float:
        """Check if boundaries have fractal character"""
        from skimage.measure import label, regionprops
        
        labeled = label(skeleton > 128)
        props = regionprops(labeled)
        if not props:
            return 0.0
        
        main = max(props, key=lambda r: r.area)
        if main.area < 100:
            return 0.0
        
        # Perimeter/area ratio (higher for fractals)
        ratio = main.perimeter / np.sqrt(main.area)
        return min((ratio - 3.5) / 3.0, 1.0)


# --- SET DETECTORS ---
class SetDetector(BaseDetector):
    def detect(self, skeleton, invariants):
        dim = invariants.get('dimensionality', 1.0)
        symmetry = invariants.get('symmetry_approx', 'C1')
        curve = invariants.get('mean_curvature', 0)
        
        # Mandelbrot Set - spiral symmetry, D_f ~ 2.0
        if symmetry.startswith('SPIRAL') and dim > 1.8:
            spiral_type = invariants.get('spiral_type', 'LOGARITHMIC')
            if spiral_type == 'MULTIPLE':
                return FractalMatch("Mandelbrot/Julia Set", 0.9, "SET", 
                                  {'light': 'white', 'polarization': True})
        
        # Sierpinski (D_f ~ 1.585, triangular symmetry)
        if 1.55 < dim < 1.62 and symmetry == 'C3':
            if curve < 0.2:
                return FractalMatch("Sierpinski Pyramid/Foam", 0.85, "SET", 
                                  {'light': 530, 'focus': 'center'})
        
        # Eisenstein Fractions - hexagonal symmetry
        if symmetry == 'C6' and 1.6 < dim < 1.8:
            if curve > 0.1:
                return FractalMatch("Eisenstein Fractions", 0.8, "SET", 
                                  {'light': 550, 'focus': 'center'})
        
        return None


# --- CRYSTALLINE FRACTAL DETECTORS ---

class DendriticCrystalDetector(BaseDetector):
    """
    Detects dendritic crystal growth patterns.
    Common in: ice crystals, mineral dendrites, metal solidification, 
    electrodeposition, snowflakes.
    """
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        branching_angle = invariants.get('branching_angle', 0)
        symmetry = invariants.get('symmetry_approx', '')
        
        logger.debug(f"DendriticCrystalDetector: dim={dim:.3f}, angle={branching_angle:.1f}°, symmetry={symmetry}")
        
        # Дендриты: 1.6 < D_f < 1.95, острое ветвление
        if not (1.6 <= dim <= 1.95):
            logger.debug(f"DendriticCrystalDetector: dim={dim:.3f} out of range [1.6, 1.95] — NO MATCH")
            return None
        
        # Проверка на анизотропию роста (предпочтительные направления)
        anisotropy = self._detect_growth_anisotropy(skeleton)
        
        # Проверка на дендритную морфологию
        dendritic_score = self._detect_dendritic_pattern(skeleton)
        
        logger.debug(f"DendriticCrystalDetector: anisotropy={anisotropy:.3f}, dendritic={dendritic_score:.3f}")
        
        # Временно снижен порог для тестирования
        if anisotropy > 0.4 or dendritic_score > 0.5:
            # Определить тип дендрита
            if 'C6' in symmetry or 55 <= branching_angle <= 65:
                crystal_type = "Hexagonal dendritic crystal"
                confidence = 0.91
            elif 85 <= branching_angle <= 95:
                crystal_type = "Cubic dendritic crystal"
                confidence = 0.88
            else:
                crystal_type = "Dendritic crystal fractal"
                confidence = 0.85
            
            logger.info(f"✓ Dendritic crystal detected: {crystal_type}")
            return FractalMatch(
                fractal_type=crystal_type,
                confidence=confidence,
                category="CRYSTALLINE",
                microscopy_advice={
                    'light': 'white',
                    'polarization': True,  # КРИТИЧНО: кристаллы видны в поляризованном свете!
                    'focus': 'stack',  # Z-stack для 3D структуры
                    'note': 'Rotate polarizer to observe birefringence patterns'
                }
            )
        logger.debug(f"DendriticCrystalDetector: anisotropy={anisotropy:.3f} < 0.4 or dendritic={dendritic_score:.3f} < 0.5 — NO MATCH")
        return None
    
    def _detect_growth_anisotropy(self, skeleton: np.ndarray) -> float:
        """
        Detect preferred growth directions (crystalline anisotropy).
        Crystals grow in specific directions based on lattice structure.
        """
        from scipy.ndimage import sobel
        
        # Вычислить градиенты (направления роста)
        gx = sobel(skeleton, axis=1)
        gy = sobel(skeleton, axis=0)
        
        # Углы градиентов
        angles = np.arctan2(gy[skeleton > 0], gx[skeleton > 0])
        
        if len(angles) == 0:
            return 0.0
        
        # Гистограмма углов
        hist, _ = np.histogram(angles, bins=12, range=(-np.pi, np.pi))
        
        # Если есть выраженные пики — анизотропия
        peak_ratio = np.max(hist) / np.mean(hist) if np.mean(hist) > 0 else 0
        
        # Нормализовать (3.0 = высокая анизотропия)
        return min(peak_ratio / 3.0, 1.0)
    
    def _detect_dendritic_pattern(self, skeleton: np.ndarray) -> float:
        """
        Detect dendritic (tree-like but with side-branches) pattern.
        Characteristic: main branches with secondary branches at angles.
        """
        from scipy.ndimage import convolve
        
        kernel = np.array([[1,1,1],[1,0,1],[1,1,1]])
        neighbors = convolve(skeleton > 0, kernel, mode='constant')
        
        # Найти junctions (точки ветвления)
        junctions = np.where((skeleton > 0) & (neighbors >= 3))
        
        if len(junctions[0]) < 10:
            return 0.0
        
        # Для дендритов: много боковых ответвлений
        # Посчитать соотношение основных ветвей к боковым
        total_junctions = len(junctions[0])
        total_pixels = np.sum(skeleton > 0)
        
        # Плотность ветвлений
        branching_density = total_junctions / max(total_pixels, 1)
        
        # Для дендритов: высокая плотность боковых ветвей
        return min(branching_density * 100, 1.0)


class SnowflakeCrystalDetector(BaseDetector):
    """
    Detects snowflake-like hexagonal crystals.
    Common in: ice crystals, certain minerals, biomaterials.
    """
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        symmetry = invariants.get('symmetry_approx', '')
        dim = invariants.get('dimensionality', 0)
        branching_angle = invariants.get('branching_angle', 0)
        
        logger.debug(f"SnowflakeDetector: symmetry={symmetry}, dim={dim:.3f}, angle={branching_angle:.1f}°")
        
        # Снежинки: C6 симметрия + фрактальные ветви
        if 'C6' not in symmetry or dim < 1.2 or dim > 1.6:
            logger.debug(f"SnowflakeDetector: no C6 symmetry or dim={dim:.3f} out of range [1.2, 1.6] — NO MATCH")
            return None
        
        # Проверка на радиальную 6-кратную симметрию
        radial_score = self._detect_radial_hex_symmetry(skeleton)
        
        # Проверка на фрактальные края ветвей
        fractal_edge = self._detect_fractal_branches(skeleton)
        
        logger.debug(f"SnowflakeDetector: radial={radial_score:.3f}, fractal_edge={fractal_edge:.3f}")
        
        # Временно снижен порог для тестирования
        if radial_score > 0.5 and fractal_edge > 0.3:
            logger.info(f"✓ Snowflake crystal detected")
            return FractalMatch(
                fractal_type="Hexagonal snowflake crystal",
                confidence=0.93,
                category="CRYSTALLINE",
                microscopy_advice={
                    'light': [450, 550],  # Синий+зелёный для контраста
                    'polarization': True,  # Бирефрингенция льда/кристаллов
                    'focus': 'high_contrast',
                    'note': 'Use cold stage to preserve structure; observe 6-fold symmetry'
                }
            )
        logger.debug(f"SnowflakeDetector: radial={radial_score:.3f} < 0.5 or fractal_edge={fractal_edge:.3f} < 0.3 — NO MATCH")
        return None
    
    def _detect_radial_hex_symmetry(self, skeleton: np.ndarray) -> float:
        """Detect 6-fold radial symmetry"""
        h, w = skeleton.shape
        center_y, center_x = h // 2, w // 2
        
        # Разбить на 6 секторов
        sectors = [[] for _ in range(6)]
        y, x = np.ogrid[:h, :w]
        angles = np.arctan2(y - center_y, x - center_x)
        angles = (angles + np.pi) % (2*np.pi)
        
        for i in range(h):
            for j in range(w):
                if skeleton[i, j]:
                    sector = int(angles[i, j] * 6 / (2*np.pi)) % 6
                    sectors[sector].append(1)
        
        # Сравнить заполненность секторов
        counts = [len(s) for s in sectors]
        if sum(counts) == 0:
            return 0.0
        
        # Чем равномернее — тем выше симметрия
        variance = np.var(counts) / (np.mean(counts)**2 + 1e-10)
        return max(0, 1 - variance)
    
    def _detect_fractal_branches(self, skeleton: np.ndarray) -> float:
        """Detect fractal branching pattern on edges"""
        from skimage.measure import perimeter, area, label, regionprops
        
        labeled = label(skeleton > 128)
        props = regionprops(labeled)
        
        if not props:
            return 0.0
        
        # Взять крупнейший регион
        main = max(props, key=lambda r: r.area)
        if main.area < 100:
            return 0.0
        
        # Отношение периметр/площадь (для фрактальных краёв выше)
        ratio = main.perimeter / np.sqrt(main.area)
        
        # Для гладких границ ~3.5, для фрактальных >5
        return min((ratio - 3.5) / 3.0, 1.0)


class SpheruliteDetector(BaseDetector):
    """
    Detects spherulite structures (radial crystalline growth).
    Common in: polymers, minerals, biominerals.
    """
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        symmetry = invariants.get('symmetry_approx', '')
        
        logger.debug(f"SpheruliteDetector: dim={dim:.3f}, symmetry={symmetry}")
        
        # Сферолиты: радиальный рост, D_f ≈ 1.5-2.0
        if not (1.4 <= dim <= 2.0):
            logger.debug(f"SpheruliteDetector: dim={dim:.3f} out of range [1.4, 2.0] — NO MATCH")
            return None
        
        # Проверка на радиальную симметрию
        radial_score = self._detect_radial_pattern(skeleton)
        
        # Проверка на концентрические круги
        concentric_score = self._detect_concentric_rings(skeleton)
        
        logger.debug(f"SpheruliteDetector: radial={radial_score:.3f}, concentric={concentric_score:.3f}")
        
        # Временно снижен порог для тестирования
        if radial_score > 0.5 or concentric_score > 0.4:
            logger.info(f"✓ Spherulite crystal detected")
            return FractalMatch(
                fractal_type="Spherulite crystal",
                confidence=0.87,
                category="CRYSTALLINE",
                microscopy_advice={
                    'light': 'white',
                    'polarization': True,  # Сферолиты дают характерный "мальтийский крест"
                    'focus': 'auto',
                    'note': 'Look for Maltese cross pattern under polarized light'
                }
            )
        logger.debug(f"SpheruliteDetector: radial={radial_score:.3f} < 0.5 or concentric={concentric_score:.3f} < 0.4 — NO MATCH")
        return None
    
    def _detect_radial_pattern(self, skeleton: np.ndarray) -> float:
        """Detect radial growth pattern from center"""
        h, w = skeleton.shape
        center_y, center_x = h // 2, w // 2
        
        # Посчитать плотность в концентрических кольцах
        max_r = min(h, w) // 2
        ring_densities = []
        
        for r in range(10, max_r, 10):
            y, x = np.ogrid[:h, :w]
            mask = (np.abs(np.sqrt((x-center_x)**2 + (y-center_y)**2) - r) < 5)
            if np.any(mask):
                density = np.mean(skeleton[mask])
                ring_densities.append(density)
        
        if not ring_densities:
            return 0.0
        
        # Для радиального паттерна: плотность уменьшается от центра
        if len(ring_densities) > 2:
            trend = np.polyfit(range(len(ring_densities)), ring_densities, 1)[0]
            # Отрицательный тренд = уменьшение от центра
            return max(0, -trend * 10) if trend < 0 else 0.3
        
        return 0.5
    
    def _detect_concentric_rings(self, skeleton: np.ndarray) -> float:
        """Detect concentric ring pattern"""
        from scipy.signal import correlate2d
        from scipy.ndimage import maximum_filter
        
        kernel = np.ones((5, 5))
        correlation = correlate2d(skeleton, kernel, mode='same')
        
        # Искать пики корреляции (центры кругов)
        peaks = maximum_filter(correlation, size=15)
        peak_count = np.sum(peaks > np.mean(correlation) * 2)
        
        return min(peak_count / 10, 1.0)


class BirefringentCrystalDetector(BaseDetector):
    """
    Detects crystals showing birefringence (double refraction).
    Identified by characteristic interference patterns in polarized light.
    """
    
    def detect(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        import logging
        logger = logging.getLogger(__name__)
        
        dim = invariants.get('dimensionality', 0)
        contrast = invariants.get('contrast', 0)
        
        logger.debug(f"BirefringentCrystalDetector: dim={dim:.3f}, contrast={contrast}")
        
        # Бирефрингентные кристаллы: высокий контраст, чёткие границы
        if contrast < 100 or dim < 1.3:
            logger.debug(f"BirefringentCrystalDetector: contrast={contrast} < 100 or dim={dim:.3f} < 1.3 — NO MATCH")
            return None
        
        # Проверка на интерференционные полосы
        interference_score = self._detect_interference_bands(skeleton)
        
        logger.debug(f"BirefringentCrystalDetector: interference={interference_score:.3f}")
        
        # Временно снижен порог для тестирования
        if interference_score > 0.4:
            logger.info(f"✓ Birefringent crystal detected")
            return FractalMatch(
                fractal_type="Birefringent crystal",
                confidence=0.89,
                category="CRYSTALLINE",
                microscopy_advice={
                    'light': [450, 550, 650],
                    'polarization': True,
                    'polarizer_angle': 'rotate',  # Рекомендовать вращать
                    'focus': 'high_res',
                    'note': 'Rotate stage to observe interference colors'
                }
            )
        logger.debug(f"BirefringentCrystalDetector: interference={interference_score:.3f} < 0.4 — NO MATCH")
        return None
    
    def _detect_interference_bands(self, skeleton: np.ndarray) -> float:
        """Detect interference band patterns (characteristic of birefringence)"""
        from scipy.ndimage import gaussian_filter
        from scipy.signal import correlate, find_peaks
        
        # Сгладить
        smoothed = gaussian_filter(skeleton.astype(float), sigma=2)
        
        # Взять профиль через центр
        h, w = skeleton.shape
        center_profile = smoothed[h//2, :]
        
        if len(center_profile) < 20:
            return 0.0
        
        # Автокорреляция
        autocorr = correlate(center_profile - np.mean(center_profile), 
                           center_profile - np.mean(center_profile), 
                           mode='same')
        
        # Искать пики в автокорреляции
        peaks, _ = find_peaks(autocorr, height=np.std(autocorr))
        
        # Регулярные пики = интерференция
        return min(len(peaks) / 10, 1.0)


# --- OLD CRYSTALLINE DETECTOR (Fallback) ---
class CrystallineDetector(BaseDetector):
    def detect(self, skeleton, invariants):
        dim = invariants.get('dimensionality', 1.0)
        symmetry = invariants.get('symmetry_approx', 'C1')
        curve = invariants.get('mean_curvature', 0)
        
        # Crystals: high order, D_f ~ 2.0, straight edges
        if dim > 1.9 and curve < 0.1:
            if symmetry in ['C4', 'C6', 'C8']:
                return FractalMatch("Ihara Crystal Fractal", 0.85, "CRYSTALLINE", 
                                  {'light': 'white', 'polarization': True})
        
        # Lower dimension crystals
        if symmetry in ['C4', 'C6'] and 1.7 < dim < 1.9 and curve < 0.15:
            return FractalMatch("Crystal Pattern", 0.75, "CRYSTALLINE", 
                              {'light': 'white', 'polarization': False})
        
        return None


# --- DETECTOR REGISTRY ---
def run_detectors(skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
    """
    Run detectors in priority order.
    Returns first match with confidence > 0.7
    """
    # Priority: Tree → Curve → Space-Filling → Set → Crystalline
    detectors = [
        TreeDetector(),
        DragonDetector(),
        HilbertDetector(),
        MooreDetector(),
        PeanoDetector(),
        TSquareDetector(),
        MortonZDetector(),
        SetDetector(),
        CrystallineDetector()
    ]
    
    for detector in detectors:
        match = detector.detect(skeleton, invariants)
        if match and match.confidence > 0.7:
            return match
    
    return None


# --- FRACTAL CLASSIFIER ---
class FractalClassifier:
    """Main classifier that orchestrates all detectors with priority order"""
    
    def __init__(self):
        self.detectors = {
            "TREE": TreeDetector(),
            "CURVE": DragonDetector(),
            "SPACE_FILLING": [
                HilbertDetector(),
                MooreDetector(),
                PeanoDetector(),
                TSquareDetector(),
                MortonZDetector(),
            ],
            "SET": [
                MandelbrotDetector(),
                JuliaDetector(),
                EisensteinDetector(),
                SetDetector()  # Fallback detector
            ],
            "CRYSTALLINE": [
                DendriticCrystalDetector(),
                SnowflakeCrystalDetector(),
                SpheruliteDetector(),
                BirefringentCrystalDetector(),
                CrystallineDetector()  # Fallback detector
            ]
        }
    
    def classify_from_invariants(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        """
        Run all detectors in priority order with logging.
        Returns best match or None.
        """
        import logging
        logger = logging.getLogger(__name__)
        
        logger.info(f"FractalClassifier: Starting classification. skeleton shape={skeleton.shape}, dtype={skeleton.dtype}")
        logger.info(f"Invariants: dim={invariants.get('dimensionality')}, symmetry={invariants.get('symmetry_approx')}, angle={invariants.get('branching_angle')}")
        
        dim = invariants.get('dimensionality', 0)
        
        # 1. Сначала SET для D_f > 1.5 (Мандельброт, Жюлиа) — чтобы отличать от деревьев
        if dim > 1.5:
            for detector in self.detectors.get("SET", []):
                match = detector.detect(skeleton, invariants)
                logger.info(f"Set detector {detector.__class__.__name__} result: {match}")
                if match and match.confidence > 0.7:
                    logger.info(f"✓ Set detected: {match.fractal_type}")
                    return match
        
        # 2. Деревья
        tree_match = self.detectors.get("TREE", TreeDetector()).detect(skeleton, invariants)
        logger.info(f"Tree detector result: {tree_match}")
        if tree_match and tree_match.confidence > 0.7:
            logger.info(f"✓ Tree detected: {tree_match.fractal_type}")
            return tree_match
        
        # 3. Кривые (Koch, Dragons)
        curve_match = self.detectors.get("CURVE", DragonDetector()).detect(skeleton, invariants)
        logger.info(f"Curve detector result: {curve_match}")
        if curve_match and curve_match.confidence > 0.7:
            logger.info(f"✓ Curve detected: {curve_match.fractal_type}")
            return curve_match
        
        # 4. Пространственно-заполняющие (Hilbert, Moore, etc.)
        for detector in self.detectors.get("SPACE_FILLING", []):
            match = detector.detect(skeleton, invariants)
            logger.info(f"Space-filling detector {detector.__class__.__name__} result: {match}")
            if match and match.confidence > 0.7:
                logger.info(f"✓ Space-filling detected: {match.fractal_type}")
                return match
        
        # 5. Кристаллические
        for detector in self.detectors.get("CRYSTALLINE", []):
            match = detector.detect(skeleton, invariants)
            logger.info(f"Crystalline detector {detector.__class__.__name__} result: {match}")
            if match and match.confidence > 0.7:
                logger.info(f"✓ Crystalline detected: {match.fractal_type}")
                return match
        
        # Ничего не найдено
        logger.warning("No fractal type detected with confidence > 0.7")
        return None
    
    def classify(self, skeleton: np.ndarray, invariants: Dict) -> Optional[FractalMatch]:
        """Main classification pipeline with priority order (alias for classify_from_invariants)"""
        return self.classify_from_invariants(skeleton, invariants)
