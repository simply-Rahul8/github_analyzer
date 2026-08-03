from flask import Flask, render_template, request, flash, redirect, url_for, send_file
import os
from pathlib import Path
from werkzeug.utils import secure_filename
from datetime import datetime
import tempfile
from dotenv import load_dotenv
import io
import sys

# Load environment variables

def _load_app_env() -> None:
    env_candidates = [
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env",
    ]
    for env_path in env_candidates:
        if env_path.exists():
            load_dotenv(env_path, override=True)
            return
    load_dotenv(override=True)


_load_app_env()

# Import from src
from src.constants import Config
from src.components.data_ingestion import DataIngestion
from src.components.report_generator import ReportGenerator
from src.pipeline.analysis_pipeline import AnalysisPipeline
from src.logger.logging_config import setup_logging

# Configure logging
logger = setup_logging()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'github-analyzer-secret-key-2024'
app.config['UPLOAD_FOLDER'] = tempfile.gettempdir()
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'txt'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if files are uploaded
        if 'students_file' not in request.files or 'questions_file' not in request.files:
            flash('Both students Excel file and questions text file are required', 'error')
            return redirect(request.url)

        students_file = request.files['students_file']
        questions_file = request.files['questions_file']

        if students_file.filename == '' or questions_file.filename == '':
            flash('Both files must be selected', 'error')
            return redirect(request.url)

        if not (allowed_file(students_file.filename) and allowed_file(questions_file.filename)):
            flash('Invalid file types. Please upload Excel (.xlsx/.xls) and text (.txt) files', 'error')
            return redirect(request.url)

        try:
            # Save uploaded files
            students_filename = secure_filename(students_file.filename)
            questions_filename = secure_filename(questions_file.filename)

            students_path = os.path.join(app.config['UPLOAD_FOLDER'], students_filename)
            questions_path = os.path.join(app.config['UPLOAD_FOLDER'], questions_filename)

            students_file.save(students_path)
            questions_file.save(questions_path)

            # Read questions content
            with open(questions_path, 'r', encoding='utf-8') as f:
                questions_content = f.read()


            # Update configuration from form
            repo_keywords = request.form.get('repo_keywords', '').strip()
            if repo_keywords:
                Config.REPO_KEYWORDS = [k.strip() for k in repo_keywords.split(',') if k.strip()]
            else:
                Config.REPO_KEYWORDS = []  # Empty list means analyze any repository

            # Validate configuration
            Config.validate()
            
            # Initialize components
            data_ingestion = DataIngestion()
            report_generator = ReportGenerator()
            pipeline = AnalysisPipeline()

            # Read students with duplicate removal and column detection
            # Capture print statements/logs if necessary, but we are using logger now.
            # We can capture sys.stdout if DataIngestion prints to stdout, but it uses logger.
            
            # For backward compatibility with the UI displaying "processing info", 
            # we might want to capture logs or just keep it simple.
            # The original code captured prints from read_students_file. 
            # Since DataIngestion uses logger which also prints to stdout (StreamHandler), capture should work.
            
            old_stdout = sys.stdout
            sys.stdout = captured_output = io.StringIO()

            try:
                students = data_ingestion.read_students_file(students_path)
            finally:
                sys.stdout = old_stdout

            processing_info = captured_output.getvalue()

            # Process students with progress updates
            results = []
            for i, student in enumerate(students):
                result = pipeline.process_student(student, questions_content)
                results.append(result)

            # Generate output
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"evaluation_{timestamp}.xlsx"
            output_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)

            report_generator.write_evaluation_file(results, output_path)

            # Calculate summary stats
            total_students = len(results)
            successful = sum(1 for r in results if r.get('status') == 'Success')
            success_rate = (successful / total_students * 100) if total_students > 0 else 0

            return render_template('results.html',
                                 results=results,
                                 total_students=total_students,
                                 successful=successful,
                                 success_rate=round(success_rate, 1),
                                 output_filename=output_filename,
                                 processing_info=processing_info)

        except Exception as e:
            flash(f'Error processing files: {str(e)}', 'error')
            return redirect(request.url)

    return render_template('index.html')

@app.route('/download/<filename>')
def download_file(filename):
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    return send_file(file_path, as_attachment=True, download_name=filename)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
