
# GitHub Repository Analyzer

An enterprise-grade, AI-powered codebase analyzer for evaluating GitHub repositories. Analyze single or multiple repositories, get instant feedback, and export results—all from a modern web interface.

## Features

- **Real-Time Analysis:** Analyze any GitHub repository instantly via the web UI.
- **Batch Evaluation:** Upload Excel files to evaluate multiple repositories at once (great for classrooms, hackathons, etc.).
- **Deep Language Support:** Recognizes 40+ programming languages and file types.
- **AI-Powered Feedback:** Uses Groq LLM for intelligent, actionable code reviews and metrics.
- **Excel Export:** Download detailed evaluation reports for all analyzed repositories.
- **Modern UI:** Responsive, user-friendly interface built with Jinja2 templates and Font Awesome icons.

## Tech Stack

- **Backend:** FastAPI, Python, PyGithub, Groq SDK
- **Frontend:** Jinja2 Templates, HTML, CSS

---

## Local Development

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd github_analyzer
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables:**
   Create a `.env` file in the project root with:
   ```env
   GITHUB_TOKEN=your_github_personal_access_token
   GROQ_API_KEY=your_groq_api_key
   ```

4. **Run the app locally:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

5. **Open your browser:**
   Visit [http://localhost:8000](http://localhost:8000)

---

## Deployment (Render.com)

This project is ready for deployment on [Render](https://render.com):

1. **Push your code to GitHub.**
2. **Create a new Web Service** on Render and connect your repo.
3. **Set build/start commands:**
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Add environment variables:**
   - `GITHUB_TOKEN` (your GitHub personal access token)
   - `GROQ_API_KEY` (your Groq API key)
5. **Clear build cache** if you update requirements.txt (important for dependency changes).
6. **Deploy!**

---

## File/Folder Structure

- `main.py` — FastAPI entrypoint and route definitions
- `src/` — Core logic (pipelines, components, logging, constants, etc.)
- `templates/` — Jinja2 HTML templates (`index.html`, `processing.html`, `results.html`)
- `uploads/` — Uploaded Excel files
- `outputs/` — Generated Excel reports
- `requirements.txt` — Python dependencies

---

## Notes

- Make sure your `.env` file is present both locally and in your deployment environment.
- If you see errors related to Jinja2 or template rendering, ensure your Render build cache is cleared and dependencies are up to date.

---

## License

MIT License. See [LICENSE](../LICENSE) for details.
