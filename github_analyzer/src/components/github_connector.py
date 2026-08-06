from github import Github, GithubException
import time
import re
from src.constants import Config
from src.logger.logging_config import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# Language-agnostic file extensions — covers every major ecosystem
# ---------------------------------------------------------------------------
ANALYZABLE_EXTENSIONS = {
    # Python
    '.py', '.pyw', '.ipynb',
    # JavaScript / TypeScript
    '.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs',
    # Web
    '.html', '.htm', '.css', '.scss', '.sass', '.less', '.vue', '.svelte',
    # Java / JVM
    '.java', '.kt', '.kts', '.scala', '.groovy',
    # C / C++ / C#
    '.c', '.h', '.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.cs',
    # Go
    '.go',
    # Rust
    '.rs',
    # Ruby
    '.rb', '.rake', '.gemspec',
    # PHP
    '.php',
    # Swift / Objective-C
    '.swift', '.m',
    # Shell / Scripts
    '.sh', '.bash', '.zsh', '.fish', '.ps1',
    # Data / Config / Infra
    '.json', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.env.example',
    '.xml', '.proto',
    # Documentation
    '.md', '.mdx', '.rst', '.txt',
    # SQL / Database
    '.sql',
    # Docker / Build
    'Dockerfile', '.dockerfile',
    # R
    '.r', '.R',
    # Dart / Flutter
    '.dart',
    # Elixir / Erlang
    '.ex', '.exs', '.erl',
    # Terraform / HCL
    '.tf', '.hcl',
    # GraphQL
    '.graphql', '.gql',
}

# Files with no extension to treat as text
ANALYZABLE_NAMES = {
    'dockerfile', 'makefile', 'rakefile', 'gemfile', 'procfile',
    'pipfile', 'justfile', 'cmakelists.txt', 'requirements.txt',
    '.gitignore', '.editorconfig',
}

SKIP_DIRS = {
    'node_modules', '.git', '__pycache__', 'venv', 'env', '.venv',
    'dist', 'build', '.idea', '.vscode', 'coverage', '.pytest_cache',
    'vendor', 'target', 'out', '.next', '.nuxt', 'bin', 'obj',
    'packages', 'Pods', '.gradle', '.mvn',
}

MAX_FILE_SIZE_BYTES = 200_000   # skip files larger than 200 KB
MAX_FILES_TOTAL    = 40         # cap total files read (content fetch)
PER_FILE_CHAR_CAP  = 5_000      # chars extracted per file


class GitHubConnector:
    def __init__(self):
        self.github_token = Config.GITHUB_TOKEN
        self.g = Github(self.github_token, per_page=100) if self.github_token else None

    # ------------------------------------------------------------------
    # Rate-limit guard
    # ------------------------------------------------------------------

    def _check_rate_limit(self):
        """Check remaining API calls and wait if necessary."""
        if not self.g:
            raise ValueError("GITHUB_TOKEN not found in configuration")
        rate_limit = self.g.get_rate_limit()
        remaining = rate_limit.rate.remaining
        reset_time = rate_limit.rate.reset

        if remaining < 10:
            wait_time = (reset_time - time.time()) + 60
            if wait_time > 0:
                logger.warning(
                    f"Rate limit low ({remaining} remaining). Waiting {wait_time:.0f}s..."
                )
                time.sleep(wait_time)

        return remaining

    # ------------------------------------------------------------------
    # Primary: fetch repo from URL
    # ------------------------------------------------------------------

    def get_repo_by_url(self, github_url):
        """
        Fetches a GitHub repository object directly from a full URL.
        Supports: https://github.com/user/repo, github.com/user/repo, or user/repo.
        """
        self._check_rate_limit()
        try:
            url = github_url.strip().rstrip('/')
            for prefix in ('https://', 'http://'):
                if url.startswith(prefix):
                    url = url[len(prefix):]
                    break

            parts = url.split('/')
            if len(parts) < 3 or parts[0].lower() != 'github.com':
                raise ValueError(f"Invalid GitHub repository URL: {github_url}")

            username = parts[1]
            repo_name = parts[2]
            # Strip .git suffix if present (e.g. https://github.com/user/repo.git)
            if repo_name.endswith('.git'):
                repo_name = repo_name[:-4]

            if not username or not repo_name:
                raise ValueError(f"Invalid GitHub repository URL: {github_url}")

            return self.g.get_repo(f"{username}/{repo_name}")
        except ValueError:
            raise
        except GithubException as e:
            logger.error(f"GitHub Error for URL {github_url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching repo for URL {github_url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Rich metadata helper
    # ------------------------------------------------------------------

    def get_repo_metadata(self, repo):
        """
        Returns a rich dict of repository metadata for display and LLM context.
        """
        try:
            topics = repo.get_topics() if repo else []
        except Exception:
            topics = []

        try:
            license_name = repo.license.name if repo.license else "None"
        except Exception:
            license_name = "Unknown"

        try:
            last_updated = repo.updated_at.strftime("%Y-%m-%d") if repo.updated_at else "Unknown"
            created_at   = repo.created_at.strftime("%Y-%m-%d") if repo.created_at else "Unknown"
        except Exception:
            last_updated = created_at = "Unknown"

        return {
            "full_name":     repo.full_name,
            "description":   repo.description or "No description provided",
            "language":      repo.language or "Unknown",
            "stars":         repo.stargazers_count,
            "forks":         repo.forks_count,
            "open_issues":   repo.open_issues_count,
            "topics":        topics,
            "license":       license_name,
            "visibility":    "Private" if repo.private else "Public",
            "default_branch": repo.default_branch,
            "created_at":    created_at,
            "last_updated":  last_updated,
        }

    # ------------------------------------------------------------------
    # Whole-repo file collector — single git-tree API call (no depth limit)
    # ------------------------------------------------------------------

    def get_all_repo_files(self, repo, max_chars=60_000):
        """
        Fetches content from the entire repository using a single recursive
        git-tree API call — no depth limit.

        File priority order:
            README > source code > notebooks > config/docs

        Returns:
            tuple: (content_text: str, files_read: int, file_paths: list)
        """
        self._check_rate_limit()

        # ── 1. Fetch the full file tree (1 API call) ────────────────────
        try:
            tree = repo.get_git_tree(repo.default_branch, recursive=True)
        except GithubException:
            # Fallback: try HEAD sha
            try:
                sha = repo.get_commits()[0].sha
                tree = repo.get_git_tree(sha, recursive=True)
            except Exception as e:
                logger.error(f"Could not fetch git tree for {repo.full_name}: {e}")
                return "", 0, []

        # ── 2. Filter and bucket every blob in the tree ─────────────────
        readme_items   = []
        notebook_items = []
        source_items   = []
        config_items   = []

        other_items = []
        for element in tree.tree:
            if element.type != "blob":
                continue

            path       = element.path
            path_lower = path.lower()
            filename   = path.split('/')[-1]
            fname_lower = filename.lower()

            # Skip files inside blacklisted directories
            parts = path_lower.split('/')
            if any(p in SKIP_DIRS for p in parts[:-1]):
                continue

            # Skip oversized files
            size = element.size or 0
            if size > MAX_FILE_SIZE_BYTES:
                continue

            # Determine extension
            if '.' in filename:
                ext = '.' + filename.rsplit('.', 1)[-1].lower()
            else:
                ext = ''

            # Check if analyzable
            analyzable = (
                ext in ANALYZABLE_EXTENSIONS
                or fname_lower in ANALYZABLE_NAMES
            )
            if not analyzable:
                # Collect files with no extension for lightweight header checks
                if ext == '':
                    other_items.append(element)
                continue

            # Bucket by priority
            if fname_lower.startswith('readme'):
                readme_items.append(element)
            elif ext == '.ipynb':
                notebook_items.append(element)
            elif ext in {
                '.py', '.pyw', '.js', '.jsx', '.ts', '.tsx', '.mjs',
                '.go', '.rs', '.java', '.kt', '.scala', '.rb', '.php',
                '.c', '.cpp', '.h', '.hpp', '.cs', '.swift', '.dart',
                '.ex', '.exs', '.r', '.R', '.sh', '.ps1', '.vue', '.svelte',
                '.html', '.css', '.scss',
            }:
                source_items.append(element)
            else:
                config_items.append(element)

        # ── 3. Lightweight header checks for files without extensions
        # Only a limited number of header checks are performed to avoid
        # excessive API calls. If a file contains a shebang or interpreter
        # hints (python/node/bash), treat it as a script candidate.
        script_candidates = []
        header_check_limit = 50
        header_checks = 0
        for element in other_items:
            if header_checks >= header_check_limit:
                break
            try:
                content_file = repo.get_contents(element.path)
                raw_header = content_file.decoded_content.decode('utf-8', errors='replace')[:400].lower()
                # Detect shebang or common interpreter mentions
                if re.search(r"^\s*#!", raw_header) or (
                    'python' in raw_header[:200] or 'node' in raw_header[:200] or 'bash' in raw_header[:200]
                ):
                    script_candidates.append(element)
                header_checks += 1
            except Exception:
                # ignore read failures for header checks
                continue

        # ── 4. Read content in priority order, up to MAX_FILES_TOTAL ────
        # Insert detected scripts after source files so they are inspected.
        priority_queue = readme_items + notebook_items + source_items + script_candidates + config_items

        collected    = []
        total_chars  = 0
        files_read   = 0
        file_paths   = []

        for element in priority_queue:
            if files_read >= MAX_FILES_TOTAL:
                logger.info(f"Reached {MAX_FILES_TOTAL}-file cap — stopping.")
                break
            if total_chars >= max_chars:
                break

            try:
                # Fetch blob content via the contents API
                content_file = repo.get_contents(element.path)
                raw = content_file.decoded_content.decode('utf-8', errors='replace')
                snippet = raw[:PER_FILE_CHAR_CAP]

                sep   = '=' * 60
                label = _guess_label(element.path)
                entry = f"\n{sep}\n[{label}] {element.path}\n{sep}\n{snippet}\n"

                collected.append(entry)
                total_chars += len(entry)
                files_read  += 1
                file_paths.append(element.path)

            except Exception as e:
                logger.warning(f"Could not read {element.path}: {e}")

        logger.info(
            f"Collected {files_read} files ({total_chars} chars) "
            f"from '{repo.full_name}' (tree had {len(priority_queue)} candidates)"
        )
        return ''.join(collected), files_read, file_paths

    # ------------------------------------------------------------------
    # Legacy method — batch Excel mode
    # ------------------------------------------------------------------

    def get_latest_repo_by_keywords(self, username, keywords=None):
        """Returns the latest (or keyword-matching) repo for a GitHub username."""
        self._check_rate_limit()
        try:
            user  = self.g.get_user(username)
            repos = user.get_repos(sort="created", direction="desc")

            if not keywords or len(keywords) == 0:
                for repo in repos:
                    if not repo.archived and not repo.fork:
                        return repo
                return repos[0] if repos else None

            for repo in repos:
                repo_text = (repo.name + " " + (repo.description or "")).lower()
                if any(keyword.lower() in repo_text for keyword in keywords):
                    return repo
            return None
        except GithubException as e:
            logger.error(f"GitHub Error for user {username}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching repos for {username}: {e}")
            return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guess_label(path: str) -> str:
    """Returns a display label based on the file extension."""
    fname = path.split('/')[-1].lower()
    if fname.startswith('readme'):
        return 'README'
    ext = ('.' + fname.rsplit('.', 1)[-1]) if '.' in fname else ''
    if ext == '.ipynb':
        return 'NOTEBOOK'
    if ext in {'.md', '.mdx', '.rst', '.txt'}:
        return 'DOCS'
    if ext in {'.json', '.yaml', '.yml', '.toml', '.ini', '.cfg',
               '.xml', '.tf', '.hcl', '.proto', '.graphql', '.gql'}:
        return 'CONFIG'
    if fname in ANALYZABLE_NAMES:
        return 'BUILD'
    if ext == '.sql':
        return 'SQL'
    if ext in {'.sh', '.bash', '.zsh', '.ps1'}:
        return 'SCRIPT'
    return 'SOURCE'
