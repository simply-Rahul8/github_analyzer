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
            try:
                repo = self.github_connector.get_repo_by_url(github_url)
            except ValueError as e:
                result["status"] = str(e)
                deterministic_score, score_breakdown = compute_deterministic_score(
                    repo_text="",
                    file_paths=[],
                    repo_metadata={},
                    repo_accessible=False,
                )
                result.update({
                    "deterministic_score": None,
                    "score_breakdown": score_breakdown,
                    "overall_rating": "Invalid",
                    "rating_category": "Invalid",
                    "rating_bands": rating_scale_text(),
                    "selection": "Invalid",
                })
                logger.warning(f"Invalid GitHub URL for {github_url}: {e}")
                return result

            if not repo:
                deterministic_score, score_breakdown = compute_deterministic_score(
                    repo_text="",
                    file_paths=[],
                    repo_metadata={},
                    repo_accessible=False,
                )
                result.update({
                    "status": "Repo Not Found",
                    "deterministic_score": None,
                    "score_breakdown": score_breakdown,
                    "overall_rating": "Invalid",
                    "rating_category": "Invalid",
                    "rating_bands": rating_scale_text(),
                    "selection": "Invalid",
                })
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
                # No analyzable content should be treated as inaccessible for
                # deterministic scoring so the final score is 0 and not
                # influenced by superficial metadata. For display we mark
                # the overall rating as 'Invalid' rather than numeric 0.
                deterministic_score, score_breakdown = compute_deterministic_score(
                    repo_text=repo_text,
                    file_paths=file_paths,
                    repo_metadata=metadata,
                    repo_accessible=False,
                )
                result.update({
                    "status": "No Analyzable Content",
                    "deterministic_score": None,
                    "score_breakdown": score_breakdown,
                    "overall_rating": "Invalid",
                    "rating_category": "Invalid",
                    "rating_bands": rating_scale_text(),
                    "selection": "Invalid",
                })
                logger.warning(f"No content collected from {repo.full_name}")
                return result

            # 3. Run LLM analysis
            # Business-requirement pre-check (e.g., "inspect this repo for the HTML code for the login page")
            requirement_info = {
                "requirement_present": False,
                "requirement_key": None,
                "requirement_met": None,
                "requirement_matches": [],
            }

            try:
                if user_context and isinstance(user_context, str):
                    lc = user_context.lower()
                    # Simple trigger for login-page HTML inspection
                    if "login" in lc and ("html" in lc or "page" in lc or "login page" in lc or "sign in" in lc or "signin" in lc):
                        requirement_info["requirement_present"] = True
                        requirement_info["requirement_key"] = "login_page_html"

                        import re

                        matches = []
                        # look for candidate html files in file_paths
                        for path in file_paths:
                            if path.lower().endswith(('.html', '.htm')) or 'login' in path.lower():
                                # extract snippet from repo_text for this path
                                pattern = re.compile(r"\n={60}\n\[.*?\] " + re.escape(path) + r"\n={60}\n(.*?)(?=\n={60}\n\[|\Z)", re.S)
                                m = pattern.search(repo_text)
                                snippet = m.group(1) if m else ''
                                s = snippet.lower()
                                # naive heuristics: password input, form action with login, id/class containing login, or 'sign in' text
                                if re.search(r"input[^>]+type=[\'\"]?password", s) or re.search(r"<form[^>]*(login|signin|sign-in|action=|/login)", s) or 'sign in' in s or 'login' in s:
                                    matches.append(path)

                        requirement_info["requirement_met"] = len(matches) > 0
                        requirement_info["requirement_matches"] = matches
            except Exception:
                # don't fail the pipeline if requirement detection errors
                requirement_info["requirement_present"] = False

            _update(f"Running AI evaluation for '{repo.full_name}'...")
            summary = self.llm_engine.compress_repo_content(repo_text)
            requirement_validation = self.llm_engine.validate_requirement(summary, user_context)
            analysis = self.llm_engine.analyze_repo(repo_text, user_context, summary=summary)

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
            # Final overall rating must follow deterministic score. For normal
            # repos we present the numeric score; if the repo lacks analyzable
            # content we display an explicit 'Invalid' marker instead.
            parsed_overall = f"{deterministic_score}/10" if deterministic_score is not None else "Invalid"
            parsed["overall_rating"] = parsed_overall
            parsed["rating_category"] = determine_rating_category(deterministic_score) if deterministic_score is not None else "Invalid"
            parsed["rating_bands"] = rating_scale_text()

            # Attach requirement info (if any) to parsed results
            parsed["requirement_text"] = user_context.strip() if user_context and isinstance(user_context, str) else ""
            parsed["requirement_present"] = requirement_validation.get("requirement_present", False)
            parsed["requirement_met"] = requirement_validation.get("requirement_met")
            parsed["requirement_matches"] = requirement_validation.get("requirement_matches") or []
            parsed["requirement_evidence"] = requirement_validation.get("requirement_evidence") or ""
            parsed["requirement_summary"] = requirement_validation.get("requirement_summary") or ""

            if parsed.get("requirement_text"):
                if parsed.get("requirement_present"):
                    if parsed.get("requirement_met") is True:
                        parsed["requirement_status"] = "Satisfied"
                    elif parsed.get("requirement_met") is False:
                        parsed["requirement_status"] = "Not satisfied"
                    else:
                        parsed["requirement_status"] = "Provided"
                else:
                    parsed["requirement_status"] = "Provided"
            else:
                parsed["requirement_status"] = ""

            if parsed.get("requirement_text") and parsed.get("requirement_met") is False:
                parsed_break = parsed.get("score_breakdown") or []
                parsed_break.append(("Business Requirement", 0, "Repository did not satisfy the provided business requirement."))
                parsed["score_breakdown"] = parsed_break
                parsed["selection"] = "Rejected"
                prev_feedback = parsed.get("feedback") or ""
                note = "NEGATIVE: Business requirement not satisfied."
                parsed["feedback"] = note + "\n\n" + prev_feedback

            # Selection label next to the student's name
            if isinstance(deterministic_score, (int, float)):
                try:
                    score_val = float(deterministic_score)
                    parsed["selection"] = "Shortlisted" if score_val > 6 else "Rejected"
                except Exception:
                    parsed["selection"] = "No Rating"
            else:
                parsed["selection"] = "Invalid"

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
