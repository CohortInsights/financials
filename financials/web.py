import argparse
import os
import sys
import tempfile
from financials.drive import GoogleDrive
from financials.calculator import FinancialsCalculator

from flask import Flask, render_template, redirect, send_file


def get_drive_service(use_cache=True) -> GoogleDrive:
    drive = None
    if hasattr(app, 'drive') and use_cache:
        drive : GoogleDrive = getattr(app, 'drive')
    else:
        drive = GoogleDrive('roger_drive')
        setattr(app, 'drive', drive)
    return drive


def get_calculator(drive: GoogleDrive) -> FinancialsCalculator:
    calculator = None
    if hasattr(drive, 'calculator'):
        calculator = getattr(drive, 'calculator')
    else:
        calculator = FinancialsCalculator(drive)
        setattr(drive, 'calculator', calculator)
    return calculator


def set_cache_dir(dir):
    cache_path = os.path.abspath(dir)
    setattr(app, 'data_cache', os.path.abspath(cache_path))


# Initialize web application before call to __main__
app = Flask(__name__)
app.config["DEBUG"] = True


def main():
    parser = argparse.ArgumentParser(description="Argument parser for this web app")
    parser.add_argument('--port', type=int, required=False, help="Port number to use")

    # Debugging statements
    args = parser.parse_args()
    print("Arguments received:")
    print(f"Port: {args.port}")
    print("Full command-line arguments received:", sys.argv)

    port = args.port

    # Invoked from __main__
    with tempfile.TemporaryDirectory() as data_cache:
        service = get_drive_service()
        with app.app_context() as context:
            setattr(app, 'initialized', False)
            set_cache_dir(data_cache)
            # app.register_blueprint(main_app, url_prefix='/fitbit')
            app.run(host="0.0.0.0", port=port)


@app.route('/')
def home():
    return redirect('dashboard')


@app.route('/templates/<file_name>')
def get_templates_file(file_name: str):
    file_name = 'templates/' + file_name
    return send_file(file_name)


@app.route('/reload')
def reload():
    drive = get_drive_service(use_cache=False)
    return redirect('dashboard')

@app.route('/dashboard')
def plot_dashboard():
    drive = get_drive_service()
    calculator = get_calculator(drive)
    year_list = calculator.get_folder_names()
    user_data = {'years': year_list}
    return render_template('dashboard.html', user_data=user_data)