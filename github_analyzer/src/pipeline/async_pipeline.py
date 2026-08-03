
import logging
import time
import os
from typing import Dict, List, Optional
from datetime import datetime

from src.pipeline.analysis_pipeline import AnalysisPipeline
from src.components.report_generator import ReportGenerator
from src.components.data_ingestion import DataIngestion
from src.logger.logging_config import setup_logging

logger = setup_logging()

# In-memory task store
# Key: task_id (str)
# Value: Dict with state, progress, message, results, output_file, error, mode
TASKS: Dict[str, Dict] = {}


class AsyncAnalysisPipeline:
    def __init__(self):
        self.pipeline         = AnalysisPipeline()
        self.data_ingestion   = DataIngestion()
        self.report_generator = ReportGenerator()

    # ------------------------------------------------------------------
    # Single-repo real-time analysis
    # ------------------------------------------------------------------

    def run_single_repo_task(
        self, task_id: str, github_url: str, user_context: str, output_folder: str
    ):
        """
        Analyzes a single GitHub repository URL with granular progress updates.
        """
        logger.info(f"Starting single-repo task {task_id} for {github_url}")
        TASKS[task_id] = {
            "state":       "PROCESSING",
            "progress":    0,
            "message":     "Initializing...",
            "results":     None,
            "output_file": None,
            "error":       None,
            "mode":        "single",
        }

        def _progress(message: str, pct: int = None):
            TASKS[task_id]["message"] = message
            if pct is not None:
                TASKS[task_id]["progress"] = pct

        try:
            _progress("Connecting to GitHub...", 5)

            # --- Run analysis with live progress callback ---
            def progress_cb(msg: str):
                # Map message keywords to progress percentages
                if "Fetching git tree" in msg:
                    _progress(msg, 20)
                elif "Read " in msg and "files" in msg:
                    _progress(msg, 40)
                elif "AI compression" in msg:
                    _progress(msg, 55)
                elif "AI evaluation" in msg:
                    _progress(msg, 70)
                elif "Parsing" in msg:
                    _progress(msg, 85)
                else:
                    _progress(msg)

            result = self.pipeline.process_repo(
                github_url, user_context, label=github_url, progress_cb=progress_cb
            )

            _progress("Generating Excel report...", 90)

            # For single-repo mode, also produce a downloadable Excel
            timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"analysis_{timestamp}.xlsx"
            output_path     = os.path.join(output_folder, output_filename)

            # Wrap in student-compatible dict for report generator
            excel_result = {**result, "student_name": result.get("label", github_url)}
            self.report_generator.write_evaluation_file([excel_result], output_path)

            TASKS[task_id].update({
                "state":       "COMPLETED",
                "progress":    100,
                "message":     f"Analysis complete! Scanned {result.get('files_analyzed', 0)} files.",
                "output_file": output_filename,
                "results":     [result],
            })

            logger.info(f"Single-repo task {task_id} completed.")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            TASKS[task_id].update({
                "state":   "FAILED",
                "error":   str(e),
                "message": f"Error: {str(e)}",
            })

    # ------------------------------------------------------------------
    # Batch Excel analysis (legacy / classroom mode)
    # ------------------------------------------------------------------

    def run_analysis_task(
        self,
        task_id: str,
        students_path: str,
        user_context: str,
        output_folder: str,
        repo_keywords: Optional[List[str]] = None,
    ):
        """
        Runs the full batch analysis pipeline.
        Reads an Excel file of students and analyzes each repo.
        """
        logger.info(f"Starting batch task {task_id}")
        TASKS[task_id] = {
            "state":       "PROCESSING",
            "progress":    0,
            "message":     "Initializing...",
            "results":     None,
            "output_file": None,
            "error":       None,
            "mode":        "batch",
        }

        try:
            if repo_keywords is not None:
                from src.constants import Config
                Config.REPO_KEYWORDS = repo_keywords

            TASKS[task_id]["message"]  = "Reading student data..."
            TASKS[task_id]["progress"] = 5

            try:
                students = self.data_ingestion.read_students_file(students_path)
            except Exception as e:
                raise Exception(f"Failed to read students file: {str(e)}")

            total_students = len(students)
            if total_students == 0:
                raise Exception("No students found in the uploaded file.")

            TASKS[task_id]["message"]  = f"Found {total_students} repos. Starting analysis..."
            TASKS[task_id]["progress"] = 10

            results = []
            for i, student in enumerate(students):
                base_progress = 10 + (i / max(total_students, 1)) * 80
                student_name  = student.get("name of the student", "Unknown")

                TASKS[task_id]["progress"] = base_progress
                TASKS[task_id]["message"]  = (
                    f"Analyzing {i+1}/{total_students}: {student_name}"
                )

                try:
                    result = self.pipeline.process_student(student, user_context)
                    results.append(result)
                except Exception as e:
                    logger.error(f"Error processing student {i}: {e}")
                    results.append({
                        "student_name":   student_name,
                        "github_link":    student.get("github link", ""),
                        "status":         "Failed",
                        "feedback":       str(e),
                        "repo_found":     "No",
                        "files_analyzed": 0,
                    })

            TASKS[task_id]["message"]  = "Generating Excel report..."
            TASKS[task_id]["progress"] = 95

            timestamp       = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"evaluation_{timestamp}.xlsx"
            output_path     = os.path.join(output_folder, output_filename)
            self.report_generator.write_evaluation_file(results, output_path)

            TASKS[task_id].update({
                "state":       "COMPLETED",
                "progress":    100,
                "message":     f"Analysis Complete! {total_students} repos processed.",
                "output_file": output_filename,
                "results":     results,
            })

            logger.info(f"Batch task {task_id} completed successfully.")

        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            TASKS[task_id].update({
                "state":   "FAILED",
                "error":   str(e),
                "message": f"Error: {str(e)}",
            })
