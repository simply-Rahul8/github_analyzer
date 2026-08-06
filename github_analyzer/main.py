
import os
import shutil
import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, Form, Request, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

from src.pipeline.async_pipeline import AsyncAnalysisPipeline, TASKS
from src.logger.logging_config import setup_logging
from src.constants import Config

logger = setup_logging()


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

app = FastAPI(title="GitHub Repository Analyzer")

# Absolute path to the templates directory (works in serverless environments)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ── Jinja2 helper: map file path → Font Awesome icon HTML ────────────────
def _fileicon(path: str) -> str:
    """
    Returns a Font Awesome <i> tag appropriate for the given file path.
    Used in results.html via {{ fileicon(fp) | safe }}.
    """
    fname = path.split('/')[-1].lower()
    ext   = ('.' + fname.rsplit('.', 1)[-1]) if '.' in fname else ''

    if fname.startswith('readme'):                                    return '<i class="fas fa-book"></i>'
    if ext == '.ipynb':                                               return '<i class="fas fa-book-open"></i>'
    if ext in {'.md', '.mdx', '.rst', '.txt'}:                       return '<i class="fas fa-file-alt"></i>'
    if ext in {'.py', '.pyw'}:                                        return '<i class="fab fa-python"></i>'
    if ext in {'.js', '.jsx', '.mjs', '.cjs'}:                        return '<i class="fab fa-js"></i>'
    if ext in {'.ts', '.tsx'}:                                        return '<i class="fab fa-js"></i>'
    if ext in {'.html', '.htm'}:                                      return '<i class="fab fa-html5"></i>'
    if ext in {'.css', '.scss', '.sass', '.less'}:                    return '<i class="fab fa-css3-alt"></i>'
    if ext in {'.vue', '.svelte'}:                                    return '<i class="fas fa-puzzle-piece"></i>'
    if ext == '.go':                                                   return '<i class="fas fa-gopuram"></i>'
    if ext == '.rs':                                                   return '<i class="fas fa-cog"></i>'
    if ext in {'.java', '.kt', '.kts', '.scala', '.groovy'}:          return '<i class="fab fa-java"></i>'
    if ext in {'.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.hxx'}:   return '<i class="fas fa-microchip"></i>'
    if ext == '.cs':                                                   return '<i class="fas fa-hashtag"></i>'
    if ext in {'.rb', '.rake', '.gemspec'}:                           return '<i class="fas fa-gem"></i>'
    if ext == '.php':                                                  return '<i class="fab fa-php"></i>'
    if ext in {'.swift', '.m'}:                                       return '<i class="fab fa-apple"></i>'
    if ext in {'.sh', '.bash', '.zsh', '.fish', '.ps1'}:             return '<i class="fas fa-terminal"></i>'
    if ext in {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.xml'}: return '<i class="fas fa-cog"></i>'
    if ext in {'.tf', '.hcl'}:                                        return '<i class="fas fa-cloud"></i>'
    if ext in {'.sql'}:                                               return '<i class="fas fa-database"></i>'
    if ext in {'.graphql', '.gql', '.proto'}:                         return '<i class="fas fa-project-diagram"></i>'
    if ext in {'.dart'}:                                              return '<i class="fas fa-mobile-alt"></i>'
    if ext in {'.r', '.R'}:                                           return '<i class="fas fa-chart-bar"></i>'
    if fname in {'dockerfile', '.dockerfile'}:                        return '<i class="fab fa-docker"></i>'
    if fname in {'makefile', 'cmakelists.txt', 'justfile'}:          return '<i class="fas fa-hammer"></i>'
    return '<i class="fas fa-file-code"></i>'


templates.env.globals['fileicon'] = _fileicon

async_pipeline = AsyncAnalysisPipeline()

UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------------------------------------------------
# Home
# -----------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render the home page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


# -----------------------------------------------------------------------
# Primary route — single-repo real-time analysis
# -----------------------------------------------------------------------

@app.post("/analyze-single")
async def analyze_single(
    request: Request,
    background_tasks: BackgroundTasks,
    github_url: str = Form(...),
    user_context: str = Form(""),
    criteria: str = Form("")
):
    """
    Start a real-time analysis for a single GitHub repository URL.
    Accepts the URL and user-provided evaluation context from the form.
    """
    try:
        github_url = github_url.strip()
        if not github_url or "github.com" not in github_url:
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": "Please enter a valid GitHub repository URL (e.g., https://github.com/user/repo)."
            })

        task_id = str(uuid.uuid4())
        # prefer explicit 'criteria' field if provided
        ctx = criteria.strip() if criteria and criteria.strip() else user_context
        background_tasks.add_task(
            async_pipeline.run_single_repo_task,
            task_id,
            github_url,
            ctx,
            OUTPUT_DIR
        )
        return RedirectResponse(url=f"/status-page/{task_id}", status_code=303)

    except Exception as e:
        logger.error(f"Single-repo analysis failed: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": f"Error starting analysis: {str(e)}"
        })


# -----------------------------------------------------------------------
# Batch route — Excel file upload (legacy / classroom mode)
# -----------------------------------------------------------------------

@app.post("/analyze")
async def analyze(
    request: Request,
    background_tasks: BackgroundTasks,
    students_file: UploadFile = File(...),
    user_context: str = Form(""),
    criteria: str = Form(""),
    repo_keywords: Optional[str] = Form(None)
):
    """
    Batch analysis: upload an Excel file with student names & GitHub links,
    plus optional user-provided evaluation context.
    (Removed optional `repo_keywords` filtering from the home page.)
    """
    try:
        if not students_file.filename.endswith(('.xlsx', '.xls')):
            return templates.TemplateResponse("index.html", {
                "request": request,
                "error": "Invalid file. Please upload an Excel file (.xlsx or .xls)."
            })

        task_id = str(uuid.uuid4())
        student_path = os.path.join(UPLOAD_DIR, f"{task_id}_{students_file.filename}")

        with open(student_path, "wb") as buffer:
            shutil.copyfileobj(students_file.file, buffer)

        keywords_list = [k.strip() for k in repo_keywords.split(',')] if repo_keywords else None

        ctx = criteria.strip() if criteria and criteria.strip() else user_context
        background_tasks.add_task(
            async_pipeline.run_analysis_task,
            task_id,
            student_path,
            ctx,
            OUTPUT_DIR,
            keywords_list
        )
        return RedirectResponse(url=f"/status-page/{task_id}", status_code=303)

    except Exception as e:
        logger.error(f"Batch upload failed: {e}")
        return templates.TemplateResponse("index.html", {
            "request": request,
            "error": f"Error starting analysis: {str(e)}"
        })


# -----------------------------------------------------------------------
# Status & Results
# -----------------------------------------------------------------------

@app.get("/status-page/{task_id}", response_class=HTMLResponse)
async def status_page(request: Request, task_id: str):
    """Render the processing status page."""
    return templates.TemplateResponse("processing.html", {"request": request, "task_id": task_id})


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    """JSON endpoint for polling task status."""
    task = TASKS.get(task_id)
    if not task:
        return {"state": "NOT_FOUND", "progress": 0, "message": "Task not found"}
    return task


@app.get("/results/{task_id}", response_class=HTMLResponse)
async def results_page(request: Request, task_id: str):
    """Render the final results page."""
    task = TASKS.get(task_id)
    if not task or task.get("state") != "COMPLETED":
        return RedirectResponse(url=f"/status-page/{task_id}")

    results = task.get("results", [])
    total = len(results)
    successful = sum(1 for r in results if r.get('status') == 'Success')
    success_rate = round((successful / total * 100), 1) if total > 0 else 0
    mode = task.get("mode", "batch")

    return templates.TemplateResponse("results.html", {
        "request": request,
        "results": results,
        "total_repos": total,
        "successful": successful,
        "success_rate": success_rate,
        "output_filename": task.get("output_file"),
        "mode": mode,
    })


@app.get("/download/{filename}")
async def download_file(filename: str):
    """Download the generated Excel report."""
    file_path = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
