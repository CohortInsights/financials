# financials/utils/services.py
import os
from financials.drive import GoogleDrive
from financials.calculator import FinancialsCalculator


def _get_app():
    """Lazy import of the Flask app to avoid circular imports."""
    from financials import web
    return web.app


def get_drive_service(use_cache=True):
    app = _get_app()
    drive = getattr(app, 'drive', None) if use_cache else None
    if not drive:
        drive = GoogleDrive('roger_drive')
        setattr(app, 'drive', drive)
    return drive


def get_calculator(drive: GoogleDrive):
    app = _get_app()
    calculator = getattr(drive, 'calculator', None)
    if not calculator:
        calculator = FinancialsCalculator(drive)
        setattr(drive, 'calculator', calculator)
    return calculator


def set_cache_dir(dir_path):
    app = _get_app()
    abs_path = os.path.abspath(dir_path)
    setattr(app, 'data_cache', abs_path)
    return abs_path
