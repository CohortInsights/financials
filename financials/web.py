import argparse
import os
import sys
import tempfile

import numpy as np

from financials.drive import GoogleDrive
from financials.calculator import FinancialsCalculator

from flask import Flask, render_template, redirect, send_file


def get_drive_service(use_cache=True) -> GoogleDrive:
    drive = None
    if hasattr(app, 'drive') and use_cache:
        drive: GoogleDrive = getattr(app, 'drive')
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


@app.route("/api/transactions")
def api_transactions():
    """
    Returns JSON transaction data for the selected year, used by the dashboard DataTable.
    """
    from flask import request, jsonify
    from financials import db as db_module
    import pandas as pd
    from datetime import datetime

    transactions = db_module.db["transactions"]

    # Get the selected year from the query string
    year = request.args.get("year")
    query = {}

    if year and year.isdigit():
        start = datetime(int(year), 1, 1)
        end = datetime(int(year) + 1, 1, 1)
        query = {"date": {"$gte": start, "$lt": end}}

    # Fetch documents for the year
    cursor = transactions.find(query, {"_id": 0})
    df = pd.DataFrame(list(cursor))

    if not df.empty and "date" in df.columns:
        df = df.replace({np.nan: ""})
        # Convert datetime to string for JSON serialization
        df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    return_values = jsonify(df.to_dict(orient="records"))
    return return_values
