from flask import Blueprint, render_template, send_from_directory
import os

web_bp = Blueprint('web', __name__)

@web_bp.route('/pricing')
def pricing():
    return render_template('pricing.html')

@web_bp.route('/')
def index():
    return render_template('index.html')

@web_bp.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')

@web_bp.route('/perfil')
def perfil():
    return render_template('perfil.html')

@web_bp.route('/database-analysis')
def database_analysis():
    return render_template('database_analysis.html')

@web_bp.route('/projects')
def projects():
    return render_template('projects.html')

@web_bp.route('/admin')
def admin():
    return render_template('admin_dashboard.html')

@web_bp.route('/admin/users')
def admin_users():
    return render_template('admin_users.html')

@web_bp.route('/admin/projects')
def admin_projects():
    return render_template('admin_projects.html')

@web_bp.route('/admin_dashboard')
def admin_dashboard():
    return render_template('admin_dashboard.html')

@web_bp.route('/analysis/<project_id>')
def analysis(project_id):
    return render_template('analysis.html', project_id=project_id)

@web_bp.route('/docs/<project_id>')
def docs(project_id):
    return render_template('docs.html', project_id=project_id)
