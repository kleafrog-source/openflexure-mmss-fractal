"""
Mock OpenFlexure Microscope API for testing and validation.
"""
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MockOpenFlexureAPI:
    """
    A mock class to simulate the OpenFlexure Microscope API.
    """
    def __init__(self):
        self.position = {'x': 0, 'y': 0, 'z': 0}
        self.light_settings = {'wavelength': 450, 'power': 0.5}
        self.resolution = (1920, 1080)
        self.command_whitelist = [
            'MOVE_Z', 'MOVE_X', 'MOVE_Y',
            'SET_LIGHT_SPECTRUM',
            'CAPTURE_IMAGE'
        ]

    def _validate_command(self, command: str, *args, **kwargs):
        """
        Validate a command against the whitelist.
        """
        command_base = command.split('(')[0]
        if command_base not in self.command_whitelist:
            raise ValueError(f"Command '{command_base}' is not in the whitelist.")

    def execute_command(self, command: str, *args, **kwargs):
        """
        Execute a command after validation.
        """
        self._validate_command(command, *args, **kwargs)

        if command.startswith('MOVE_Z'):
            value = kwargs.get('value')
            self.move_z(value)
        elif command.startswith('MOVE_X'):
            value = kwargs.get('value')
            self.move_x(value)
        elif command.startswith('MOVE_Y'):
            value = kwargs.get('value')
            self.move_y(value)
        elif command.startswith('SET_LIGHT_SPECTRUM'):
            wavelength = kwargs.get('wavelength')
            power = kwargs.get('power')
            self.set_light_spectrum(wavelength, power)
        elif command.startswith('CAPTURE_IMAGE'):
            resolution = kwargs.get('resolution')
            return self.capture_image(resolution)
        else:
            raise ValueError(f"Unknown command: {command}")

    def move_z(self, value: int):
        """Simulate moving the Z axis."""
        self.position['z'] += value
        logger.info(f"MockOpenFlexure: Moved Z by {value} um. New position: {self.position}")

    def move_x(self, value: int):
        """Simulate moving the X axis."""
        self.position['x'] += value
        logger.info(f"MockOpenFlexure: Moved X by {value} um. New position: {self.position}")

    def move_y(self, value: int):
        """Simulate moving the Y axis."""
        self.position['y'] += value
        logger.info(f"MockOpenFlexure: Moved Y by {value} um. New position: {self.position}")

    def set_light_spectrum(self, wavelength: int, power: float):
        """Simulate setting the light spectrum."""
        self.light_settings['wavelength'] = wavelength
        self.light_settings['power'] = power
        logger.info(f"MockOpenFlexure: Set light spectrum to {wavelength} nm at {power} power.")

    def capture_image(self, resolution: tuple):
        """Simulate capturing an image."""
        self.resolution = resolution
        logger.info(f"MockOpenFlexure: Captured image at {resolution} resolution.")
        # In a real scenario, this would return an image object.
        # For the mock, we can return the path to a test image.
        return "path/to/mock/image.jpg"
