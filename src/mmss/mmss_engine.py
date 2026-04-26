"""
Core engine for the MMSS-Alpha-Formula (v2.0) architecture.
Orchestrates the bi-directional, iterative control loop.
"""
import os
import json
import logging
import base64
from typing import Dict, Any
from pathlib import Path
from jinja2 import Environment, FileSystemLoader
from mistralai.client import MistralClient
import httpx
import datetime
import cv2

from .env_utils import load_project_env
from .safe_microscope import SafeMicroscopeWrapper
from .openflexure_mock import MockOpenFlexureAPI

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from project env files.
load_project_env()

class MMSS_Engine:
    """
    The MMSS-Engine orchestrates the iterative control loop for meta-formula synthesis.
    """
    def __init__(self, config: Dict[str, Any]):
        """
        Initializes the MMSS-Engine.

        Args:
            config: A dictionary containing the configuration for the engine.
        """
        self.config = config
        self.safety_mode_active = os.getenv('MMSS_SAFETY_MODE_ACTIVE', 'False').lower() == 'true'
        self.analysis_mode = os.getenv('MMSS_ANALYSIS_MODE', 'invariants').lower()
        if self.analysis_mode not in {'invariants', 'hybrid', 'vision_only'}:
            logger.warning("Unknown MMSS_ANALYSIS_MODE=%s, falling back to 'invariants'", self.analysis_mode)
            self.analysis_mode = 'invariants'
        self.vision_enabled = self.analysis_mode in {'hybrid', 'vision_only'}
        self.vision_model = os.getenv('MISTRAL_VISION_MODEL', 'mistral-small-latest')
        self.vision_max_size = int(os.getenv('MISTRAL_VISION_MAX_SIZE', '1024'))
        self.vision_retry_count = int(os.getenv('MISTRAL_VISION_RETRY_COUNT', '3'))
        self._vision_cache: Dict[str, Any] = {}
        self._last_vision_error: str | None = None
        
        # Использовать mock API для разработки (без реального микроскопа)
        # Для реального микроскопа использовать SafeMicroscopeWrapper
        use_real_microscope = os.getenv('USE_REAL_MICROSCOPE', 'False').lower() == 'true'
        
        if use_real_microscope:
            self.microscope = SafeMicroscopeWrapper(
                server_url=os.getenv('MICROSCOPE_SERVER_URL', 'http://localhost:5000'),
                microscope_id=int(os.getenv('MICROSCOPE_ID', '1')),
                safe_mode=True
            )
            logger.info("🔌 Using real microscope via SafeMicroscopeWrapper")
        else:
            self.microscope = MockOpenFlexureAPI()
            logger.info("🎭 Using mock microscope API (development mode)")
        
        self.max_iterations = 3
        self._last_successful_atoms = None
        self.MAX_Z_MOVEMENT = 50  # Maximum Z movement in microns

        # Initialize FractalClassifier
        from .fractal_detectors import FractalClassifier
        self.fractal_classifier = FractalClassifier()

        # Initialize Mistral client with extended timeout for vision calls
        self.mistral_api_key = os.getenv('MISTRAL_API_KEY')
        if self.mistral_api_key:
            try:
                # Configure httpx client with longer timeouts for vision calls
                timeout = httpx.Timeout(60.0, connect=10.0)
                self.mistral_client = MistralClient(
                    api_key=self.mistral_api_key,
                    timeout=timeout
                )
                logger.info("Mistral client initialized with extended timeout (60s)")
            except Exception as e:
                logger.error(f"Failed to initialize Mistral client: {e}")
                self.mistral_client = None
        else:
            self.mistral_client = None
            logger.warning("MISTRAL_API_KEY not found. Mistral API calls will be simulated.")

        # Initialize Jinja2 environment
        self.jinja_env = Environment(loader=FileSystemLoader('src/mmss/'))

        if self.safety_mode_active:
            logger.info("MMSS_SAFETY_MODE_ACTIVE is True. Microscope commands will be simulated.")

    def run(self, initial_image_path: str) -> Dict[str, Any]:
        """
        Runs the iterative control loop to derive a meta-formula.

        Args:
            initial_image_path: The path to the initial image for analysis.

        Returns:
            A dictionary containing the final result of the analysis.
        """
        logger.info("Starting MMSS-Alpha-Formula (v2.0) run.")
        
        # Create output directory if it doesn't exist
        os.makedirs('output/reports', exist_ok=True)
        
        # Generate base filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        image_name = os.path.splitext(os.path.basename(initial_image_path))[0]
        report_filename = f'mmss_alpha_formula_result_{image_name}_{timestamp}.json'
        report_path = os.path.join('output', 'reports', report_filename)
        
        # Initialize results dictionary
        results = {
            "iterations": [],
            "final_formula": None,
            "final_metrics": None,
            "vision_analysis": None,
            "vision_status": "disabled" if not self.vision_enabled else "pending",
            "vision_error": None,
            "analysis_mode": self.analysis_mode,
            "timestamp": datetime.datetime.now().isoformat(),
            "image_path": initial_image_path,
            "report_path": report_path,
            "status": "running"
        }
        
        # Save initial results
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        current_image_path = initial_image_path
        v_stability_counter = 0
        last_v = 0.0
        candidate_formula = "N/A"

        try:
            # In vision_only mode, do single iteration with vision analysis only
            if self.analysis_mode == "vision_only":
                logger.info("vision_only mode: Single iteration with Mistral vision only")
                mmss_atoms = self._capture_and_atomize_vision_only(current_image_path)
                if mmss_atoms.get("vision_analysis"):
                    results["vision_analysis"] = mmss_atoms.get("vision_analysis")
                results["vision_status"] = mmss_atoms.get("vision_status", results["vision_status"])
                results["vision_error"] = mmss_atoms.get("vision_error")
                
                # Generate hypothesis based on vision result
                mistral_response = self._generate_hypothesis(mmss_atoms)
                candidate_formula = mistral_response.get("formula")
                
                # Store single iteration result
                iteration_data = {
                    "iteration": 1,
                    "mmss_atoms": mmss_atoms,
                    "mistral_response": mistral_response,
                    "command_validated": False,
                    "command_executed": None,
                    "formula": candidate_formula,
                    "v_stability_counter": 1,
                    "vision_analysis": mmss_atoms.get("vision_analysis"),
                    "vision_status": mmss_atoms.get("vision_status"),
                    "vision_error": mmss_atoms.get("vision_error"),
                    "timestamp": datetime.datetime.now().isoformat()
                }
                results["iterations"].append(iteration_data)
                results["last_update"] = datetime.datetime.now().isoformat()
                
                # Set final metrics from vision-only analysis
                results["final_formula"] = candidate_formula
                results["final_metrics"] = {
                    "V": mmss_atoms.get("V", 0),
                    "S": mmss_atoms.get("S", 0),
                    "D_f": mmss_atoms.get("D_f", 0),
                    "R_T": mmss_atoms.get("R_T", 0),
                    "detected_type": mmss_atoms.get("detected_type"),
                    "detected_source": mmss_atoms.get("detected_source"),
                }
                
                # Save final results for vision_only mode
                results["completion_time"] = datetime.datetime.now().isoformat()
                results["status"] = "completed"
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                
                logger.info("vision_only mode: Single analysis complete")
                return results
            else:
                # Standard multi-iteration mode for invariants/hybrid
                for i in range(self.max_iterations):
                    logger.info(f"--- Iteration {i + 1}/{self.max_iterations} ---")
                    
                    # Step A: Capture & Atomization (simulated for now)
                    mmss_atoms = self._capture_and_atomize(current_image_path)
                    if mmss_atoms.get("vision_analysis"):
                        results["vision_analysis"] = mmss_atoms.get("vision_analysis")
                    if mmss_atoms.get("vision_status"):
                        results["vision_status"] = mmss_atoms.get("vision_status")
                    if mmss_atoms.get("vision_error"):
                        results["vision_error"] = mmss_atoms.get("vision_error")

                    # Step B: Hypothesis Generation (Mistral API call)
                    mistral_response = self._generate_hypothesis(mmss_atoms)
                    candidate_formula = mistral_response.get("formula")
                    refinement_command = mistral_response.get("command")

                    # Step C: Safety & Validation
                    command_validated = False
                    if self.safety_mode_active:
                        logger.info(f"Command '{refinement_command}' simulated and skipped.")
                    else:
                        command_validated = self._validate_command(refinement_command, mmss_atoms)

                    # Step D: Execution & Iteration
                    if not self.safety_mode_active and command_validated:
                        if refinement_command.startswith('MOVE_Z'):
                            value = float(refinement_command.split('(')[1].split(')')[0])
                            current_image_path = self.microscope.execute_command(refinement_command, value=value)
                            
                            # Check max Z movement
                            if abs(self.microscope.position['z']) > self.MAX_Z_MOVEMENT:
                                logger.warning(f"Max Z movement reached ({self.microscope.position['z']} um), stopping")
                                break

                    # Step E: Termination Check
                    current_v = self._calculate_semantic_value(mmss_atoms)
                    
                    # If confident detection found, stop early
                    if mmss_atoms.get("detected_type") and v_stability_counter >= 1:
                        logger.info(f"Confident detection ({mmss_atoms['detected_type']}), stopping refinement")
                        break
                    
                    if current_v >= 0.999:
                        logger.info(f"Termination criteria met: V ({current_v}) >= 0.999")
                        break

                    if abs(current_v - last_v) < 0.001:
                        v_stability_counter += 1
                        if v_stability_counter >= 3:
                            logger.info("Termination criteria met: V stability over 3 iterations.")
                            break
                    else:
                        v_stability_counter = 0

                    last_v = current_v

                    # Store iteration results
                    iteration_data = {
                        "iteration": i + 1,
                        "mmss_atoms": mmss_atoms,
                        "mistral_response": mistral_response,
                        "command_validated": command_validated,
                        "command_executed": None,
                        "formula": candidate_formula,
                        "v_stability_counter": v_stability_counter,
                        "vision_analysis": mmss_atoms.get("vision_analysis"),
                        "vision_status": mmss_atoms.get("vision_status"),
                        "vision_error": mmss_atoms.get("vision_error"),
                        "timestamp": datetime.datetime.now().isoformat()
                    }
                    results["iterations"].append(iteration_data)
                    results["last_update"] = datetime.datetime.now().isoformat()
                    
                    # Save intermediate results after each iteration
                    with open(report_path, 'w', encoding='utf-8') as f:
                        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                    
                    # Check termination conditions
                    if current_v >= 0.999 or v_stability_counter >= 3:
                        logger.info(f"Termination condition met: V={current_v}, stability={v_stability_counter}")
                        break

            # After loop completes, select best iteration based on detection confidence
            best_iteration = None
            best_confidence = 0
            
            for iter_data in results["iterations"]:
                if iter_data["mmss_atoms"].get("detected_type"):
                    # If there's a detection, this is high confidence
                    confidence = 0.9
                else:
                    confidence = 0.5
                
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_iteration = iter_data
            
            if best_iteration:
                results["final_formula"] = best_iteration["formula"]
                results["final_metrics"] = {
                    "V": best_iteration["mmss_atoms"].get("V", 0),
                    "S": best_iteration["mmss_atoms"].get("S", 0),
                    "D_f": best_iteration["mmss_atoms"].get("D_f", 0),
                    "R_T": best_iteration["mmss_atoms"].get("R_T", 0),
                    "detected_type": best_iteration["mmss_atoms"].get("detected_type"),
                    "detected_source": best_iteration["mmss_atoms"].get("detected_source"),
                    "branching_angle": best_iteration["mmss_atoms"].get("branching_angle"),
                    "mean_curvature": best_iteration["mmss_atoms"].get("mean_curvature")
                }
            else:
                # Fallback to last iteration
                final_metrics = {
                    "V": last_v,
                    "S": mmss_atoms.get("S", 0),
                    "D_f": mmss_atoms.get("D_f", 0),
                    "R_T": mmss_atoms.get("R_T", 0),
                    "detected_type": mmss_atoms.get("detected_type"),
                    "detected_source": mmss_atoms.get("detected_source"),
                }
                results["final_formula"] = candidate_formula
                results["final_metrics"] = final_metrics
            
            results["completion_time"] = datetime.datetime.now().isoformat()
            results["status"] = "completed"
            
            # Save final results
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False, default=str)
                
            logger.info("MMSS-Alpha-Formula run finished.")
            
            # Return the results
            return results
            
        except Exception as e:
            error_msg = f"Error during MMSS execution: {str(e)}"
            logger.error(error_msg, exc_info=True)
            
            # Save error state to results
            results["status"] = "error"
            results["error"] = error_msg
            results["error_time"] = datetime.datetime.now().isoformat()
            
            try:
                with open(report_path, 'w', encoding='utf-8') as f:
                    json.dump(results, f, indent=2, ensure_ascii=False, default=str)
            except Exception as save_error:
                logger.error(f"Failed to save error state: {save_error}")
            
            raise

    def _capture_and_atomize_vision_only(self, image_path: str) -> Dict[str, Any]:
        """
        Vision-only atomization: single Mistral vision call without geometric classification.
        Used in vision_only mode for one-shot analysis.
        """
        import sys
        from pathlib import Path
        import numpy as np
        import cv2
        from skimage.feature import graycomatrix, graycoprops
        from skimage.measure import shannon_entropy
        from skimage.morphology import skeletonize

        sys.path.append(str(Path(__file__).parent.parent))
        from invariant_measurer import measure_invariants

        logger.info("vision_only atomization: Single Mistral vision call only")

        image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
        if image is None:
            return {
                "V": 0.0,
                "S": 0.0,
                "D_f": 0.0,
                "R_T": 0.0,
                "detected_type": None,
                "detected_source": "none",
                "fractal_category": "BIOLOGICAL",
                "microscopy_advice": {},
                "vision_analysis": None,
                "vision_status": "error",
                "vision_error": f"Failed to load image: {image_path}",
                "branching_angle": None,
                "mean_curvature": None,
            }

        image = cv2.resize(image, (256, 256))
        binary_for_skeleton = image < 128
        skeleton = skeletonize(binary_for_skeleton).astype(np.uint8) * 255
        invariants = measure_invariants(skeleton)

        mean_intensity = float(np.mean(image) / 255.0)
        edges = cv2.Canny(image, 100, 200)
        edge_density = float(np.mean(edges > 0))
        roi_uint8 = np.clip(image // 4, 0, 63).astype('uint8')
        try:
            glcm = graycomatrix(roi_uint8, distances=[1], angles=[0], levels=64, symmetric=True, normed=True)
            homogeneity = float(graycoprops(glcm, 'homogeneity')[0, 0])
            energy = float(graycoprops(glcm, 'energy')[0, 0])
        except Exception:
            homogeneity, energy = 0.5, 0.5
        entropy = float(shannon_entropy(image))
        V = float(np.clip(0.3 * mean_intensity + 0.4 * (1 - homogeneity) + 0.3 * edge_density, 0, 1))
        S = float(np.clip(0.5 * edge_density + 0.5 * (1 - energy), 0, 1))
        D_f = float(np.clip(invariants.get('dimensionality', 0.0), 0.0, 2.0))
        R_T = float(self._calculate_topology_ratio(invariants))

        vision_analysis = self._analyze_raw_image_with_mistral(image_path)

        # Extract classification from vision result
        detected_type = None
        fractal_category = "BIOLOGICAL"
        detected_source = "none"
        microscopy_advice = {}
        vision_status = "ready" if vision_analysis else "unavailable"
        vision_error = None if vision_analysis else self._last_vision_error

        if vision_analysis:
            vision_object_guess = vision_analysis.get("object_guess") or vision_analysis.get("focus_guess")
            if not vision_object_guess or str(vision_object_guess).lower() == "unknown":
                vision_object_guess = vision_analysis.get("category_guess")
            
            if vision_object_guess:
                detected_type = vision_object_guess
                fractal_category = vision_analysis.get("category_guess", fractal_category)
                detected_source = "mistral_raw_vision"
                microscopy_advice = {}
                summary = vision_analysis.get("summary") or vision_analysis.get("biological_interpretation")
                if summary:
                    microscopy_advice["vision_note"] = summary
                logger.info(f"vision_only classification: {detected_type}")
        
        # Return minimal atomization result
        return {
            "V": V if detected_type else max(V, 0.15),
            "S": S,
            "D_f": D_f,
            "R_T": R_T,
            "detected_type": detected_type,
            "detected_source": detected_source,
            "fractal_category": fractal_category,
            "microscopy_advice": microscopy_advice,
            "vision_analysis": vision_analysis,
            "vision_status": vision_status,
            "vision_error": vision_error,
            "entropy": entropy,
            "branching_angle": float(invariants.get('branching_angle', 0)),
            "mean_curvature": float(invariants.get('mean_curvature', 0)),
        }

    def _capture_and_atomize(self, image_path: str) -> Dict[str, Any]:
        """
        Performs the MMSS atomization process with actual image analysis.
        Fixed for thin-line fractals.
        """
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent))
        from invariant_measurer import measure_invariants
        import cv2
        import numpy as np
        from skimage.feature import graycomatrix, graycoprops
        from skimage.measure import shannon_entropy
        from skimage.morphology import skeletonize
        
        try:
            # Load image
            image = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
            if image is None:
                logger.error(f"Failed to load image: {image_path}")
                # Return last successful atoms if available
                if self._last_successful_atoms is not None:
                    logger.warning("Using last successful atoms")
                    return self._last_successful_atoms
                return self._get_default_atoms()
            
            image = cv2.resize(image, (256, 256))
            
            # === AUTO-ROI DETECTION ===
            _, binary_detect = cv2.threshold(image, 128, 255, cv2.THRESH_BINARY_INV)
            contours, _ = cv2.findContours(binary_detect, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            if not contours:
                logger.warning("No contours found! Using full image.")
                roi_image = image
            else:
                largest_contour = max(contours, key=cv2.contourArea)
                x, y, w, h = cv2.boundingRect(largest_contour)
                pad_x, pad_y = int(w * 0.1), int(h * 0.1)
                x1, y1 = max(0, x - pad_x), max(0, y - pad_y)
                x2, y2 = min(image.shape[1], x + w + pad_x), min(image.shape[0], y + h + pad_y)
                roi_image = image[y1:y2, x1:x2]
                logger.info(f"Auto-ROI: x={x1}, y={y1}, w={x2-x1}, h={y2-y1}")
                if roi_image.size == 0:
                    roi_image = image
            
            # === СКЕЛЕТИЗАЦИЯ для D_f ===
            binary_for_skeleton = roi_image < 128  # Чёрные линии → True
            skeleton = skeletonize(binary_for_skeleton).astype(np.uint8) * 255
            sk_density = np.mean(skeleton > 0)
            logger.info(f"Skeleton: density={sk_density:.3f}, nonzero={np.count_nonzero(skeleton)}")
            if sk_density < 0.05:
                logger.warning("Low skeleton density — fractal may be too thin or binarization issue")
            
            # === ИЗМЕРЕНИЕ ИНВАРИАНТОВ на скелете ===
            invariants = measure_invariants(skeleton)
            
            # === ФРАКТАЛЬНАЯ КЛАССИФИКАЦИЯ через FractalClassifier ===
            match = self.fractal_classifier.classify_from_invariants(skeleton, invariants)
            
            fractal_category = None  # Сохранить категорию для structural_relations
            
            detected_confidence = 0.0
            if match and match.confidence > 0.7:
                detected_type = match.fractal_type
                fractal_category = match.category
                detected_confidence = float(match.confidence)
                symmetry = f"{match.category}_{match.fractal_type.replace(' ', '_')}"
                microscopy_advice = match.microscopy_advice
                detected_source = "geometric_invariants"
                logger.info(f"✓ Fractal classified: {detected_type} (conf: {match.confidence:.2f})")
            else:
                # Fallback на старую логику из measure_invariants
                detected_type = invariants.get('detected_type')
                symmetry = invariants.get('symmetry_approx', 'C1')
                microscopy_advice = invariants.get('microscopy_advice', {})
                detected_source = "invariant_fallback" if detected_type else "none"
                if detected_type:
                    logger.info(f"Fractal detected from invariants: {detected_type}")
                else:
                    logger.info(f"Fractal not classified. Using fallback symmetry: {symmetry}")
            
            # Basic statistics на оригинальном ROI
            vision_analysis = None
            vision_status = "disabled" if not self.vision_enabled else "pending"
            vision_error = None
            if self.vision_enabled:
                vision_analysis = self._analyze_raw_image_with_mistral(image_path)
                vision_status = "ready" if vision_analysis else "unavailable"
                vision_error = None if vision_analysis else self._last_vision_error
                vision_object_guess = None
                if vision_analysis:
                    vision_object_guess = vision_analysis.get("object_guess") or vision_analysis.get("focus_guess")
                    if not vision_object_guess or str(vision_object_guess).lower() == "unknown":
                        vision_object_guess = vision_analysis.get("category_guess")
                
                # In vision_only mode, Mistral result is primary and overrides geometric classification
                if self.analysis_mode == "vision_only" and vision_analysis and vision_object_guess:
                    detected_type = vision_object_guess
                    fractal_category = vision_analysis.get("category_guess", fractal_category or "BIOLOGICAL")
                    detected_source = "mistral_raw_vision"
                    microscopy_advice = dict(microscopy_advice)
                    summary = vision_analysis.get("summary") or vision_analysis.get("biological_interpretation")
                    if summary:
                        microscopy_advice["vision_note"] = summary
                    logger.info(f"vision_only mode: Using Mistral classification: {detected_type}")
                # In hybrid mode, use Mistral as fallback or override obvious geometric false-positives.
                elif self.analysis_mode == "hybrid" and vision_analysis and vision_object_guess:
                    should_prefer_vision = (
                        not detected_type or
                        self._should_prefer_vision_over_geometry(
                            detected_type=detected_type,
                            fractal_category=fractal_category,
                            detected_source=detected_source,
                            vision_analysis=vision_analysis,
                            detected_confidence=detected_confidence,
                        )
                    )
                    if should_prefer_vision:
                        detected_type = vision_object_guess
                        fractal_category = vision_analysis.get("category_guess", fractal_category or "BIOLOGICAL")
                        detected_source = "mistral_raw_vision"
                        microscopy_advice = dict(microscopy_advice)
                        summary = vision_analysis.get("summary") or vision_analysis.get("biological_interpretation")
                        if summary:
                            microscopy_advice["vision_note"] = summary
                        logger.info(f"hybrid mode: Preferring Mistral vision result: {detected_type}")
            mean_intensity = np.mean(roi_image) / 255.0
            std_intensity = np.std(roi_image) / 255.0
            
            # Edge detection
            edges = cv2.Canny(roi_image, 100, 200)
            edge_density = np.mean(edges > 0)
            
            # Texture analysis
            roi_uint8 = np.clip(roi_image // 4, 0, 63).astype('uint8')  # 64 levels for GLCM stability
            try:
                glcm = graycomatrix(roi_uint8, distances=[1], angles=[0], levels=64, symmetric=True, normed=True)
                contrast = graycoprops(glcm, 'contrast')[0, 0]
                homogeneity = graycoprops(glcm, 'homogeneity')[0, 0]
                energy = graycoprops(glcm, 'energy')[0, 0]
            except:
                contrast, homogeneity, energy = 0.5, 0.5, 0.5
            
            entropy = shannon_entropy(roi_image)
            
            # === ВЫЧИСЛЕНИЕ МЕТРИК ===
            V = 0.3 * mean_intensity + 0.4 * (1 - homogeneity) + 0.3 * edge_density
            S = 0.5 * edge_density + 0.5 * (1 - energy)
            D_f = invariants['dimensionality']
            R_T = self._calculate_topology_ratio(invariants)
            
            # === УМНАЯ ВАЛИДАЦИЯ РОИ ===
            # Не предупреждать для тонких фракталов
            if mean_intensity > 0.95 and edge_density < 0.01 and std_intensity < 0.05:
                logger.warning("ROI appears to be empty background!")
            
            # Формирование language_atoms и structural_relations
            language_atoms = [
                f"intensity_{mean_intensity:.2f}", 
                f"contrast_{contrast:.2f}",
                f"entropy_{entropy:.2f}",
                f"dimensionality_{D_f:.2f}"
            ]
            
            structural_relations = [
                f"edge_density_{edge_density:.3f}",
                f"homogeneity_{homogeneity:.3f}",
                f"symmetry_{invariants['symmetry_approx']}"
            ]
            
            # Добавить атомы для спиралей
            if invariants.get('spiral_detected', False):
                spiral_type = invariants.get('spiral_type', 'UNKNOWN')
                spiral_tightness = invariants.get('spiral_tightness', 0.0)
                language_atoms.append(f"spiral_{spiral_type.lower()}")
                structural_relations.append(f"spiral_tightness_{spiral_tightness:.2f}")
            
            # Добавить результаты фрактальной классификации
            if detected_type:
                language_atoms.append(f"fractal_{detected_type.lower().replace(' ', '_')}")
                # Использовать категорию из классификатора, или определить из detected_type
                if fractal_category:
                    category = fractal_category
                elif "Tree" in detected_type:
                    category = "TREE"
                elif "Dragon" in detected_type or "Koch" in detected_type:
                    category = "CURVE"
                elif "Spiral" in detected_type or "Mandelbrot" in detected_type or "Julia" in detected_type:
                    category = "SET"
                elif any(term in detected_type for term in ["Fern", "Vascular", "root", "Coral", "Radial biological", "Mycelium", "biofilm"]):
                    category = "BIOLOGICAL"
                elif "Crystal" in detected_type:
                    category = "CRYSTALLINE"
                else:
                    category = "UNKNOWN"
                structural_relations.append(f"fractal_category_{category}")
            
            atoms = {
                "V": float(np.clip(V, 0, 1)),
                "S": float(np.clip(S, 0, 1)),
                "D_f": float(np.clip(D_f, 1.0, 2.0)),
                "R_T": float(R_T),
                "intensity": float(mean_intensity),
                "contrast": float(contrast),
                "homogeneity": float(homogeneity),
                "edge_density": float(edge_density),
                "entropy": float(entropy),
                "language_atoms": language_atoms,
                "structural_relations": structural_relations,
                "detected_type": detected_type,
                "detected_source": detected_source,
                "detected_confidence": detected_confidence,
                "fractal_category": fractal_category,
                "microscopy_advice": microscopy_advice,
                "branching_angle": float(invariants.get('branching_angle', 0)),
                "mean_curvature": float(invariants.get('mean_curvature', 0)),
                "vision_analysis": vision_analysis,
                "vision_status": vision_status,
                "vision_error": vision_error,
            }
            
            # Save successful atoms for fallback
            self._last_successful_atoms = atoms
            return atoms
            
        except Exception as e:
            logger.error(f"Error in image analysis: {e}", exc_info=True)
            return self._get_default_atoms()
            
    def _get_default_atoms(self) -> Dict[str, Any]:
        """Return default atom values when image processing fails"""
        return {
            "V": 0.8,
            "S": 0.1,
            "D_f": 1.8,
            "R_T": 2.0,
            "language_atoms": ["default_atom1", "default_atom2"],
            "structural_relations": ["default_rel1"],
            "detected_source": "default_fallback",
            "vision_analysis": None
        }

    def _calculate_topology_ratio(self, invariants: Dict) -> float:
        """Calculate topological ratio from invariants."""
        symmetry = invariants.get('symmetry_approx', 'C1')
        
        # === НОВОЕ: Обработка спиральной симметрии ===
        if symmetry.startswith('SPIRAL'):
            # Для спиралей R_T зависит от tightness
            spiral_tightness = invariants.get('spiral_tightness', 0.5)
            spiral_type = invariants.get('spiral_type', 'LOGARITHMIC')
            
            if spiral_type == 'MULTIPLE':
                # Множественные спирали (Julia set) — R_T ~ 2.5-3.5
                return 2.5 + spiral_tightness  # 2.5-3.5
            elif spiral_type == 'LOGARITHMIC':
                # Логарифмическая спираль — золотое сечение
                return 1.618 + spiral_tightness  # 1.6-2.6
            else:
                # Архимедова — ближе к 2
                return 2.0 + spiral_tightness * 0.5
        # ============================================
        
        # Существующий код для дискретной симметрии
        if symmetry == 'C6':
            return 3.0  # Koch: деление на 3
        elif symmetry == 'C3':
            return 3.0
        elif symmetry == 'C12':
            return 3.0
        elif symmetry == 'C4':
            return 4.0
        elif symmetry == 'C8':
            return 4.0
        
        # Fallback: branching angles
        branching = invariants.get('branching', {})
        angles = branching.get('angles', [])
        if angles:
            avg_angle = np.mean(angles)
            if 55 <= avg_angle <= 65:
                return 3.0
            elif 85 <= avg_angle <= 95:
                return 4.0
        
        return 2.0  # Default

    def _fix_latex_escapes(self, json_str: str) -> str:
        """Fix common LaTeX escape issues in JSON response"""
        import re
        # Escape single backslashes before letters (but not before " or /)
        json_str = re.sub(r'(?<!\\)\\(frac|mathcal|cdot|sqrt|sum|prod|int)(?![\\"])', r'\\\\\1', json_str)
        # Replace \_ with \\_ (escaped underscore)
        json_str = json_str.replace('\\_', '\\\\_')
        return json_str

    def _extract_json_payload(self, response_text: str) -> Dict[str, Any]:
        """Extract a JSON object from a model response."""
        response_text = response_text.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```", 1)[1].split("```", 1)[0].strip()

        return json.loads(response_text)

    def _vision_looks_biological(self, vision_analysis: Dict[str, Any] | None) -> bool:
        if not vision_analysis:
            return False

        biological_tokens = (
            "bio", "organic", "fung", "hypha", "mycel", "root", "vascular",
            "plant", "leaf", "pollen", "coral", "filament", "branch"
        )
        fields = [
            vision_analysis.get("object_guess"),
            vision_analysis.get("category_guess"),
            vision_analysis.get("summary"),
            vision_analysis.get("biological_interpretation"),
        ]
        haystack = " ".join(str(value).lower() for value in fields if value)
        return any(token in haystack for token in biological_tokens)

    def _should_prefer_vision_over_geometry(
        self,
        detected_type: str | None,
        fractal_category: str | None,
        detected_source: str | None,
        vision_analysis: Dict[str, Any] | None,
        detected_confidence: float,
    ) -> bool:
        if not vision_analysis or not self._vision_looks_biological(vision_analysis):
            return False

        if detected_source != "geometric_invariants":
            return False

        geometric_text = f"{fractal_category or ''} {detected_type or ''}".lower()
        set_like_tokens = (" set", "mandelbrot", "julia", "eisenstein", "sierpinski pyramid", "foam")
        if any(token in geometric_text for token in set_like_tokens):
            return True

        if (fractal_category or "").upper() == "SET":
            return True

        return detected_confidence < 0.8

    def _encode_image_for_vision(self, image_path: str) -> str | None:
        """Resize and encode image for Mistral raw vision analysis."""
        image = cv2.imread(image_path)
        if image is None:
            self._last_vision_error = f"Unable to load image for Mistral vision: {image_path}"
            logger.warning("Vision analysis skipped: cannot load image %s", image_path)
            return None

        h, w = image.shape[:2]
        max_dim = max(h, w)
        if max_dim > self.vision_max_size:
            scale = self.vision_max_size / max_dim
            new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
            image = cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)

        ok, encoded = cv2.imencode(".jpg", image, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        if not ok:
            self._last_vision_error = f"JPEG encoding failed for Mistral vision: {image_path}"
            logger.warning("Vision analysis skipped: JPEG encoding failed for %s", image_path)
            return None

        return base64.b64encode(encoded.tobytes()).decode("utf-8")

    def _analyze_raw_image_with_mistral(self, image_path: str) -> Dict[str, Any] | None:
        """
        Send a resized but otherwise unprocessed image to Mistral vision so it can
        suggest what is currently in microscope focus.
        Uses caching and retry logic for reliability.
        """
        if not self.mistral_client:
            self._last_vision_error = "Mistral client is unavailable. Check MISTRAL_API_KEY and network access."
            return None

        # Check cache first
        image_key = str(Path(image_path).stat().st_mtime) + str(Path(image_path).stat().st_size)
        if image_key in self._vision_cache:
            logger.info("Using cached vision analysis for %s", image_path)
            return self._vision_cache[image_key]

        image_b64 = self._encode_image_for_vision(image_path)
        if not image_b64:
            return None

        self._last_vision_error = None

        prompt = (
            "You are analyzing a microscope image. The image is sent raw except for downscaling. "
            "Return strict JSON with keys: object_guess, focus_quality, category_guess, biological_interpretation, "
            "fractal_character, confidence, summary, visible_structures, recommended_followup. "
            "Prefer broad, careful biological or organic morphology classes such as root-like, "
            "vascular, pollen-like, fungal network, crystal-like, debris, or unknown. "
            "Do not claim species-level identification."
        )

        # Retry logic with exponential backoff
        import time
        for attempt in range(self.vision_retry_count):
            try:
                chat_response = self.mistral_client.chat(
                    model=self.vision_model,
                    response_format={"type": "json_object"},
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": prompt},
                                {
                                    "type": "image_url",
                                    "image_url": f"data:image/jpeg;base64,{image_b64}",
                                },
                            ],
                        }
                    ],
                )
                response_text = chat_response.choices[0].message.content
                if isinstance(response_text, list):
                    response_text = "".join(part.get("text", "") for part in response_text if isinstance(part, dict))
                payload = self._extract_json_payload(str(response_text))
                payload["mode"] = "mistral_raw_vision"
                payload["model"] = self.vision_model
                payload["image_resize_max"] = self.vision_max_size
                self._last_vision_error = None
                
                # Cache the result
                self._vision_cache[image_key] = payload
                logger.info("Vision analysis cached for %s", image_path)
                
                return payload
            except Exception as exc:
                self._last_vision_error = str(exc)
                logger.error("Mistral raw vision call failed (attempt %d/%d): %s", attempt + 1, self.vision_retry_count, exc)
                if attempt < self.vision_retry_count - 1:
                    backoff_time = (2 ** attempt) * 1  # Exponential backoff: 1s, 2s, 4s
                    logger.info("Retrying in %d seconds...", backoff_time)
                    time.sleep(backoff_time)
                else:
                    logger.error("All retry attempts exhausted for vision analysis")
                    return None

    def _generate_hypothesis(self, mmss_atoms: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates a hypothesis using the Mistral API with a Jinja2 template.
        """
        if not self.mistral_client:
            logger.warning("Mistral client not available. Using simulated response.")
            return self._get_simulated_hypothesis()

        try:
            template = self.jinja_env.get_template('mistral_prompt.jinja2')
            prompt = template.render(mmss_atoms=mmss_atoms)

            # Updated to use the correct API for mistralai v0.4.2
            chat_response = self.mistral_client.chat(
                model="mistral-large-latest",
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = chat_response.choices[0].message.content
            logger.debug(f"Raw response: {response_text}")

            try:
                response_text = self._fix_latex_escapes(str(response_text))
                return self._extract_json_payload(response_text)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON response: {e}")
                logger.error(f"Response content: {response_text}")
                raise

        except Exception as e:
            logger.error(f"Mistral API call failed: {e}. Using simulated response.")
            return self._get_simulated_hypothesis()

    def _get_simulated_hypothesis(self) -> Dict[str, Any]:
        """
        Returns a simulated hypothesis for fallback.
        """
        iteration = self.max_iterations - (self.max_iterations - 1)
        command = f"MOVE_Z({100 * iteration})"
        return {
            "formula": f"SIMULATED_FORMULA_ITER_{iteration}",
            "command": command
        }

    def _validate_command(self, command: str, current_metrics: Dict[str, Any]) -> bool:
        logger.info(f"Validating command: {command}")
        r_t = current_metrics.get("R_T")
        d_f = current_metrics.get("D_f")

        # Расширенные диапазоны для фракталов
        if not (2.0 <= r_t <= 4.0):
            logger.warning(f"Command validation failed: R_T ({r_t}) is out of bounds [2.0, 4.0].")
            return False
        if not (1.0 <= d_f <= 2.2):
            logger.warning(f"Command validation failed: D_f ({d_f}) is out of bounds [1.0, 2.2].")
            return False

        try:
            self.microscope._validate_command(command)
        except ValueError as e:
            logger.warning(f"Command validation failed: {e}")
            return False
        logger.info("Command validation successful.")
        return True

    def _calculate_semantic_value(self, mmss_atoms: Dict[str, Any]) -> float:
        """
        Calculates the semantic value (V) from the MMSS atoms.
        """
        return mmss_atoms.get("V", 0.0)

    def _generate_final_output(self, formula: str, final_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generates the final output in the specified JSON format.
        """
        with open("MMSS-Blockly.json", "r") as f:
            blockly_data = json.load(f)

        return {
            "final_meta_formula": formula,
            "object_description": "A description of the derived formula and structure.",
            "light_spectrums_used": ["Warm-White_450nm"],
            "final_mmss_module": {
                "system_name": blockly_data["system_name"],
                "version": blockly_data["version"],
                "description": blockly_data["description"],
                "workflow_blocks": blockly_data["workflow_blocks"],
                "control_flow": blockly_data["control_flow"],
                "current_metrics": final_metrics
            }
        }
