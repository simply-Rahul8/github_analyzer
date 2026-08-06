from typing import Dict, List, Tuple


def compute_deterministic_score(
    repo_text: str,
    file_paths: List[str],
    repo_metadata: Dict[str, object],
    repo_accessible: bool = True,
) -> Tuple[int, List[Tuple[str, int, str]]]:
    """Compute a deterministic score for a student GitHub repository.

    The score is intentionally lightweight and student-focused. It rewards
    basic repository hygiene, documentation, meaningful code presence, and
    a reasonable project structure rather than professional-level features.
    """
    if not repo_accessible:
        return 0, [
            (
                "Repository Accessible",
                0,
                "The repository could not be accessed or is blocked."
            )
        ]

    normalized_paths = [path.lower() for path in file_paths or []]
    normalized_text = (repo_text or "").strip().lower()

    def _has_readme() -> bool:
        return any(
            path.endswith("readme")
            or path.endswith("readme.md")
            or path.endswith("readme.txt")
            or path.endswith("readme.rst")
            or "/readme" in path
            or "readme" == path
            for path in normalized_paths
        )

    def _has_doc_files() -> bool:
        return any(
            path.endswith(".md")
            or path.endswith(".rst")
            or path.endswith(".txt")
            for path in normalized_paths
        )

    def _has_code_files() -> bool:
        return any(
            path.endswith(ext)
            for ext in [".py", ".js", ".ts", ".java", ".go", ".rb", ".cs", ".cpp", ".c", ".rs", ".swift", ".kt", ".kts", ".php"]
            for path in normalized_paths
        )

    def _has_notebook_files() -> bool:
        return any(path.endswith(".ipynb") for path in normalized_paths)

    def _has_documentation_section() -> bool:
        if _has_readme():
            return True
        return any(
            path.startswith("docs/") or "/docs/" in path for path in normalized_paths
        )

    description = str(repo_metadata.get("description") or "").strip()
    language = str(repo_metadata.get("language") or "").strip()
    topics = repo_metadata.get("topics") or []
    license_name = str(repo_metadata.get("license") or "").strip()
    stars = int(repo_metadata.get("stars") or 0)
    forks = int(repo_metadata.get("forks") or 0)
    created_at = str(repo_metadata.get("created_at") or "").strip()
    last_updated = str(repo_metadata.get("last_updated") or "").strip()

    score = 0
    breakdown = []

    checks = [
        (
            "Repository Accessible",
            bool(repo_accessible),
            "The repository is accessible and can be analyzed."
        ),
        (
            "README / Documentation",
            _has_readme() or _has_documentation_section(),
            "The repository includes a README or documentation folder."
        ),
        (
            "Project Description",
            bool(description),
            "The repository has a non-empty description."
        ),
        (
            "Code Files Present",
            _has_code_files() or _has_notebook_files(),
            "The repository contains at least one recognizable code or notebook file."
        ),
        (
            "Meaningful Repo Structure",
            len(file_paths or []) >= 3,
            "The repository has multiple files, suggesting a project rather than a single script."
        ),
        (
            "Documentation Signals",
            _has_doc_files(),
            "The repository includes markdown, text, or reStructuredText files supporting documentation."
        ),
        (
            "Language Metadata",
            bool(language),
            "The repository reports a primary language."
        ),
        (
            "Topics or License",
            bool(topics) or bool(license_name),
            "The repository has topic tags or a license, which improves discoverability and clarity."
        ),
        (
            "Repository Activity",
            stars + forks > 0,
            "The repository shows activity through stars or forks."
        ),
        (
            "Substantive Content",
            len(normalized_text) >= 1200,
            "The repository contains a substantial amount of collected content for evaluation."
        ),
    ]

    for name, passed, reason in checks:
        points = 1 if passed else 0
        score += points
        breakdown.append((name, points, reason))

    # Normalize to a 1-10 score when a project is present but weakly signaled
    if score == 0 and (normalized_text or file_paths):
        score = 1
        if breakdown:
            breakdown[0] = (
                breakdown[0][0],
                1,
                "The repository is accessible; additional signals are limited."
            )

    return score, breakdown


def determine_rating_category(score: int) -> str:
    if score >= 10:
        return "Exceptional student project"
    if score >= 8:
        return "Strong student project"
    if score >= 6:
        return "Good student project"
    if score >= 4:
        return "Basic attempt"
    if score >= 1:
        return "Needs significant improvement"
    return "Repository inaccessible or unavailable"


def rating_scale_text() -> str:
    return (
        "1-3: Project barely exists, no real code or effort visible\n"
        "4-5: Basic attempt with significant issues in core functionality\n"
        "6-7: Decent student project, works mostly, shows effort and learning\n"
        "8-9: Strong student project with clean code, good README, and solid functionality\n"
        "10: Exceptional — goes above and beyond for a student project"
    )
