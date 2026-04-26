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
        
        # Проверка доступности сервера
        try:
            response = requests.get(f"{self.server_url}/api/microscopes/", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Connected to Management Server at {server_url}")
            else:
                logger.warning(f"⚠️  Server returned status {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.error(f"❌ Cannot connect to Management Server at {server_url}")
            logger.error("📝 Make sure server is running: python manage.py runserver")
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
        
        # Выполнение через Management Server API
        try:
            response = requests.post(
                f"{self.server_url}/api/microscopes/{self.microscope_id}/control/light/",
                json={
                    'wavelength_nm': wavelength,
                    'power_percent': power
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"✅ Light set to {wavelength}nm at {power}%")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to set light: {e}")
            return False
    
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
            if relative:
                endpoint = f"api/microscopes/{self.microscope_id}/control/z/relative/"
            else:
                endpoint = f"api/microscopes/{self.microscope_id}/control/z/absolute/"
            
            response = requests.post(
                f"{self.server_url}/{endpoint}",
                json={'distance_um': distance_um},
                timeout=10
            )
            response.raise_for_status()
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
            endpoint = f"api/microscopes/{self.microscope_id}/control/xy/relative/" if relative \
                      else f"api/microscopes/{self.microscope_id}/control/xy/absolute/"
            
            response = requests.post(
                f"{self.server_url}/{endpoint}",
                json={'x_um': x_um, 'y_um': y_um},
                timeout=10
            )
            response.raise_for_status()
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
            response = requests.post(
                f"{self.server_url}/api/microscopes/{self.microscope_id}/capture/",
                json={'width': resolution[0], 'height': resolution[1]},
                timeout=30
            )
            response.raise_for_status()
            
            # Сохранить изображение
            output_path = f"output/{filename}"
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'wb') as f:
                f.write(response.content)
            
            logger.info(f"✅ Image captured: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"❌ Failed to capture image: {e}")
            return None
    
    def get_status(self) -> Optional[Dict]:
        """Get microscope status from server"""
        try:
            response = requests.get(
                f"{self.server_url}/api/microscopes/{self.microscope_id}/",
                timeout=5
            )
            response.raise_for_status()
            return response.json()
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
