import nbformat
from src.constants import Config
from src.logger.logging_config import setup_logging

logger = setup_logging()


class RepoProcessor:
    """
    Builds a structured text representation of an entire GitHub repository.
    Language-agnostic — handles any stack via GitHubConnector.get_all_repo_files().
    """

    def __init__(self):
        self.max_chars = Config.MAX_REPO_CHARS

    def parse_notebook_content(self, raw_content):
        """
        Parses raw .ipynb file content (string) into readable text.
        Extracts markdown and code cells up to a per-notebook character limit.
        """
        try:
            nb = nbformat.reads(raw_content, as_version=4)
            text = ""
            char_budget = 4000  # per-notebook budget

            for cell in nb.cells:
                if len(text) >= char_budget:
                    break
                if cell.cell_type == "markdown" and len(cell.source) < 600:
                    snippet = f"[MARKDOWN]\n{cell.source}\n\n"
                    text += snippet
                elif cell.cell_type == "code" and len(cell.source) < 2000:
                    snippet = f"[CODE]\n{cell.source}\n\n"
                    text += snippet

            return text[:char_budget]
        except Exception as e:
            logger.warning(f"Could not parse notebook content: {e}")
            return raw_content[:2000]

    def build_repo_summary(self, github_connector, repo):
        """
        Fetches all analyzable files from a repo and builds a structured
        summary string for the LLM, prepended with rich repository metadata.

        Returns:
            tuple: (repo_text: str, files_read: int, file_paths: list, metadata: dict)
        """
        # 1. Fetch rich metadata (single cached object, no extra API calls for basics)
        metadata = github_connector.get_repo_metadata(repo)

        # 2. Collect file content (single git-tree API call + per-file content fetches)
        raw_content, files_read, file_paths = github_connector.get_all_repo_files(
            repo, max_chars=self.max_chars
        )

        if not raw_content:
            logger.warning(f"No content collected from repo '{repo.name}'")
            return "", 0, [], metadata

        # 3. Build rich header for LLM context
        topics_str  = ", ".join(metadata["topics"]) if metadata["topics"] else "None"
        header = (
            f"REPOSITORY: {metadata['full_name']}\n"
            f"Description: {metadata['description']}\n"
            f"Language: {metadata['language']} | Stars: {metadata['stars']} | "
            f"Forks: {metadata['forks']} | Open Issues: {metadata['open_issues']}\n"
            f"License: {metadata['license']} | Visibility: {metadata['visibility']}\n"
            f"Topics: {topics_str}\n"
            f"Default Branch: {metadata['default_branch']}\n"
            f"Created: {metadata['created_at']} | Last Updated: {metadata['last_updated']}\n"
            f"{'=' * 60}\n"
        )

        logger.info(
            f"Built summary for '{repo.full_name}': "
            f"{files_read} files, {len(header) + len(raw_content)} chars"
        )
        return header + raw_content, files_read, file_paths, metadata
