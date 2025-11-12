from flask import render_template, redirect, send_file
from financials.web import app
from financials.utils.services import get_drive_service, get_calculator

@app.route('/')
def home():
    return redirect('dashboard')

@app.route('/dashboard')
def plot_dashboard():
    drive = get_drive_service()
    calculator = get_calculator(drive)
    year_list = calculator.get_folder_names()
    user_data = {'years': year_list}
    return render_template('dashboard.html', user_data=user_data)

@app.route('/reload')
def reload():
    drive = get_drive_service(use_cache=False)
    return redirect('dashboard')

@app.route('/templates/<file_name>')
def get_templates_file(file_name: str):
    return send_file(f'templates/{file_name}')
