class GitHubAnalyzerError(Exception):
    """Base exception for GitHub Analyzer."""
    pass

class RepoNotFoundError(GitHubAnalyzerError):
    """Raised when no suitable repository is found."""
    pass

class NotebookNotFoundError(GitHubAnalyzerError):
    """Raised when no notebook is found in the repository."""
    pass

class LLMProcessingError(GitHubAnalyzerError):
    """Raised when there is an error in LLM processing."""
    pass

class ConfigError(GitHubAnalyzerError):
    """Raised when there is a configuration error."""
    pass
