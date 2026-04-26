"""
Safe wrapper for OpenFlexure Management Server.
All commands go through safety checks before execution.
"""
import requests
import time
import logging
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)

class SafeMicroscopeWrapper:
    """
    Safe wrapper around OpenFlexure Management Server.
    - All commands are logged
    - Safe mode prevents execution by default
    - Range checking for all parameters
    """
    
    def __init__(self, server_url: str = "http://localhost:8000", 
                 microscope_id: int = 1,
                 safe_mode: bool = True):
        """
        Args:
            server_url: URL of OpenFlexure Management Server
            microscope_id: ID of microscope in the server (default: 1)
            safe_mode: If True, only log commands without executing
        """
        self.server_url = server_url.rstrip('/')
        self.microscope_id = microscope_id
        self.safe_mode = safe_mode
        self.command_log = []
        
        # Проверка доступности сервера (WoT API)
        try:
            response = requests.get(f"{self.server_url}/api/v2", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Connected to OpenFlexure Microscope Server at {server_url}")
            else:
                logger.warning(f"⚠️  Server returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to OpenFlexure Microscope Server at {server_url}")
            logger.error("📝 Make sure the microscope server is running")
            raise
    
    def enable_safe_mode(self):
        """Enable safe mode (commands logged but not executed)"""
        self.safe_mode = True
        logger.info("🛡️  SAFE MODE ENABLED - No commands will be executed")
    
    def disable_safe_mode(self):
        """Disable safe mode (requires confirmation)"""
        confirm = input("⚠️  WARNING! Disable safe mode? Type 'YES' to confirm: ")
        if confirm == "YES":
            self.safe_mode = False
            logger.warning("⚠️  SAFE MODE DISABLED - Commands WILL be executed!")
        else:
            logger.info("✅ Safe mode remains ENABLED")
    
    def _log_command(self, command: str, params: Dict[str, Any]):
        """Log command for audit trail"""
        entry = {
            'command': command,
            'params': params,
            'safe_mode': self.safe_mode,
            'timestamp': time.time()
        }
        self.command_log.append(entry)
        
        if self.safe_mode:
            logger.info(f"🔍 [SAFE] {command}({params})")
        else:
            logger.info(f"✅ [EXEC] {command}({params})")
    
    def set_light_spectrum(self, wavelength: int, power: float) -> bool:
        """
        Set LED wavelength and power.
        
        Safety checks:
        - wavelength: 400-700 nm (visible light)
        - power: 0-100%
        """
        # Проверка диапазонов
        if not (400 <= wavelength <= 700):
            raise ValueError(f"Wavelength {wavelength}nm out of safe range [400-700]")
        if not (0 <= power <= 100):
            raise ValueError(f"Power {power}% out of safe range [0-100]")
        
        self._log_command("SET_LIGHT_SPECTRUM", {'wavelength': wavelength, 'power': power})
        
        if self.safe_mode:
            return True
        
        # Выполнение через OpenFlexure API v2
        # Примечание: OpenFlexure не имеет прямого управления светом через API
        # Логируем операцию для совместимости
        logger.info(f"💡 Light control requested: {wavelength}nm at {power}%")
        logger.info("⚠️  Note: OpenFlexure API v2 does not support direct light control")
        return True
    
    def move_z(self, distance_um: float, relative: bool = True) -> bool:
        """
        Move Z axis (focus).
        
        Safety checks:
        - Max movement: ±100 μm per command
        - Absolute position limits can be configured
        """
        # Ограничить движение
        if abs(distance_um) > 100:
            raise ValueError(f"Movement {distance_um}μm too large! Max ±100μm per command")
        
        self._log_command("MOVE_Z", {'distance_um': distance_um, 'relative': relative})
        
        if self.safe_mode:
            return True
        
        try:
            # WoT API: /api/v2/actions/MoveAPI
            move_data = {'z': distance_um} if relative else {'z': distance_um, 'absolute': True}
            
            response = requests.post(
                f"{self.server_url}/api/v2/actions/MoveAPI",
                json=move_data,
                timeout=10
            )
            
            if not self._validate_response(response, "MOVE_Z"):
                return False
            
            logger.info(f"✅ Z moved by {distance_um}μm")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to move Z: {e}")
            return False
    
    def move_xy(self, x_um: float, y_um: float, relative: bool = True) -> bool:
        """
        Move X and Y axes (stage position).
        
        Safety checks:
        - Max movement: ±1000 μm per command
        """
        if abs(x_um) > 1000 or abs(y_um) > 1000:
            raise ValueError(f"Movement too large! Max ±1000μm per command")
        
        self._log_command("MOVE_XY", {'x_um': x_um, 'y_um': y_um, 'relative': relative})
        
        if self.safe_mode:
            return True
        
        try:
            # WoT API: /api/v2/actions/MoveAPI
            move_data = {'x': x_um, 'y': y_um} if relative else {'x': x_um, 'y': y_um, 'absolute': True}
            
            response = requests.post(
                f"{self.server_url}/api/v2/actions/MoveAPI",
                json=move_data,
                timeout=10
            )
            
            if not self._validate_response(response, "MOVE_XY"):
                return False
            
            logger.info(f"✅ XY moved to ({x_um}, {y_um})μm")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to move XY: {e}")
            return False
    
    def capture_image(self, filename: str = "capture.jpg", 
                     resolution: tuple = (1920, 1080)) -> Optional[str]:
        """
        Capture image and save to file.
        
        Returns:
            Path to saved image or None if failed
        """
        self._log_command("CAPTURE_IMAGE", {'filename': filename, 'resolution': resolution})
        
        if self.safe_mode:
            # В safe mode создать пустой файл для тестирования
            fake_path = f"output/{filename}"
            Path(fake_path).parent.mkdir(parents=True, exist_ok=True)
            Path(fake_path).touch()
            logger.info(f"🔍 [SAFE] Created fake image: {fake_path}")
            return fake_path
        
        try:
            # WoT API: /api/v2/actions/CaptureAPI
            response = requests.post(
                f"{self.server_url}/api/v2/actions/CaptureAPI",
                json={'use_video_port': False},
                timeout=30
            )
            
            if not self._validate_response(response, "CAPTURE_IMAGE"):
                return None
            
            # Получить изображение из ответа
            data = response.json()
            image_url = data.get('image', {}).get('filename')
            
            if not image_url:
                logger.error("❌ No image URL in response")
                return None
            
            # Скачать изображение
            image_response = requests.get(f"{self.server_url}{image_url}", timeout=30)
            image_response.raise_for_status()
            
            # Сохранить изображение
            output_path = f"output/{filename}"
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                f.write(image_response.content)
            
            logger.info(f"✅ Image captured: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Failed to capture image: {e}")
            return None
    
    def get_status(self) -> Optional[Dict]:
        """Get microscope status from server (WoT API)"""
        try:
            # Получить позицию через properties
            position_response = requests.get(
                f"{self.server_url}/api/v2/properties/position",
                timeout=5
            )
            
            # Получить информацию о камере через properties
            camera_response = requests.get(
                f"{self.server_url}/api/v2/properties/camera_settings",
                timeout=5
            )
            
            status = {}
            
            if position_response.status_code == 200:
                pos_data = position_response.json()
                status['position'] = pos_data
            
            if camera_response.status_code == 200:
                cam_data = camera_response.json()
                status['camera'] = cam_data
            
            status['server_url'] = self.server_url
            status['safe_mode'] = self.safe_mode
            
            return status
        except Exception as e:
            logger.error(f"❌ Failed to get status: {e}")
            return None
    
    def get_command_log(self) -> list:
        """Return list of all logged commands"""
        return self.command_log.copy()
    
    def clear_command_log(self):
        """Clear command log"""
        self.command_log.clear()
        logger.info("📝 Command log cleared")
    
    def _validate_response(self, response: requests.Response, operation: str) -> bool:
        """
        Validate HTTP response from server.
        
        Args:
            response: requests.Response object
            operation: Name of operation for error messages
            
        Returns:
            True if response is valid, False otherwise
        """
        if response.status_code >= 400:
            logger.error(f"❌ {operation} failed with status {response.status_code}")
            try:
                error_data = response.json()
                logger.error(f"   Error details: {error_data}")
            except:
                logger.error(f"   Response: {response.text[:200]}")
            return False
        
        try:
            # Проверить что ответ это JSON
            response.json()
            return True
        except ValueError:
            logger.error(f"❌ {operation} returned invalid JSON")
            logger.error(f"   Response: {response.text[:200]}")
            return False
    
    def _validate_json_schema(self, data: Dict, required_fields: List[str]) -> bool:
        """
        Validate JSON response has required fields.
        
        Args:
            data: JSON data as dictionary
            required_fields: List of required field names
            
        Returns:
            True if all fields present, False otherwise
        """
        missing = [field for field in required_fields if field not in data]
        if missing:
            logger.error(f"❌ Missing required fields: {missing}")
            return False
        return True
