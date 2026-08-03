from src.components.github_connector import GitHubConnector
from src.components.repo_processor import RepoProcessor
from src.components.llm_engine import LLMEngine
from src.components.report_generator import ReportGenerator
from src.constants import Config
from src.logger.logging_config import setup_logging
from src.scoring import compute_deterministic_score, determine_rating_category, rating_scale_text

logger = setup_logging()


class AnalysisPipeline:
    def __init__(self):
        self.github_connector = GitHubConnector()
        self.repo_processor   = RepoProcessor()
        self.llm_engine       = LLMEngine()
        self.report_generator = ReportGenerator()

    def process_repo(self, github_url, user_context=None, label=None, progress_cb=None):
        """
        Process a single GitHub repository URL end-to-end:
          1. Fetch the repo object
          2. Collect all repo files → structured text + rich metadata
          3. Run LLM analysis (compress → evaluate)
          4. Parse and return structured result dict

        Args:
            github_url:   Full GitHub repository URL
            user_context: User-provided evaluation criteria / questions
            label:        Optional display name (e.g. student name) for batch mode
            progress_cb:  Optional callable(message: str) for real-time status updates
        """
        def _update(msg):
            if progress_cb:
                progress_cb(msg)
            logger.info(msg)

        logger.info(f"Processing repo: {github_url}")

        result = {
            "label":          label or github_url,
            "github_link":    github_url,
            "repo_found":     "No",
            "files_analyzed": 0,
            "files_list":     [],
            "repo_metadata":  {},
            "overall_rating": "",
            "feedback":       "",
            "status":         "Failed"
        }

        try:
            # 1. Fetch repo object
            _update("Connecting to GitHub and fetching repository...")
            repo = self.github_connector.get_repo_by_url(github_url)
            if not repo:
                result["status"] = "Repo Not Found"
                logger.warning(f"Could not fetch repo for URL: {github_url}")
                return result

            result["repo_found"] = repo.full_name

            # 2. Build repo content summary (git tree + file reads + metadata)
            _update(f"Fetching git tree for '{repo.full_name}'...")
            repo_text, files_read, file_paths, metadata = self.repo_processor.build_repo_summary(
                self.github_connector, repo
            )
            result["files_analyzed"] = files_read
            result["files_list"]     = file_paths
            result["repo_metadata"]  = metadata

            _update(f"Read {files_read} files. Running AI compression...")

            if not repo_text:
                result["status"] = "No Analyzable Content"
                logger.warning(f"No content collected from {repo.full_name}")
                return result

            # 3. Run LLM analysis
            _update(f"Running AI evaluation for '{repo.full_name}'...")
            analysis = self.llm_engine.analyze_repo(repo_text, user_context)

            # 4. Parse result
            _update("Parsing AI response and building report...")
            parsed = self.report_generator.parse_llm_response(analysis)

            # Compute deterministic rubric score (authoritative)
            deterministic_score, score_breakdown = compute_deterministic_score(
                repo_text=repo_text,
                file_paths=file_paths,
                repo_metadata=metadata,
                repo_accessible=True,
            )

            # Preserve any LLM-provided rating for transparency, but always
            # override the final overall rating with the deterministic score.
            parsed["llm_overall_rating"] = parsed.get("overall_rating") or ""
            parsed["score_breakdown"] = score_breakdown
            parsed["deterministic_score"] = deterministic_score
            parsed["overall_rating"] = f"{deterministic_score}/10"
            parsed["rating_category"] = determine_rating_category(deterministic_score)
            parsed["rating_bands"] = rating_scale_text()

            result.update(parsed)
            result["status"] = "Success"
            logger.info(f"Successfully analyzed {repo.full_name}")

        except Exception as e:
            logger.error(f"Error processing {github_url}: {e}")
            result["status"] = f"Error: {str(e)}"

        return result

    def process_student(self, student, user_context=None):
        """
        Backward-compatible wrapper for batch (Excel) mode.
        Maps old student dict format to process_repo().
        """
        name       = student.get("name of the student", "Unknown")
        github_url = student.get("github link", "")

        logger.info(f"Processing student: {name}, URL: {github_url}")

        result = self.process_repo(github_url, user_context, label=name)

        # Map label → student_name for backward compat with report generator
        result["student_name"] = result.pop("label", name)
        return result
