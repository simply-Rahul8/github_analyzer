import re
import pandas as pd

def clean_github_url(url: str) -> str:
    """
    Cleans and standardizes GitHub URLs.
    """
    if not url or pd.isna(url):
        return ""

    url = str(url).strip()

    # Handle various GitHub URL formats
    if url.startswith('http'):
        # Full URL
        pass
    elif url.startswith('github.com/'):
        url = 'https://' + url
    elif '/' in url and len(url.split('/')) == 2:
        # username/repo format
        url = f'https://github.com/{url}'
    elif not url.startswith('http') and len(url) > 0:
        # Assume it's a username
        url = f'https://github.com/{url}'

    # Remove trailing slashes and common suffixes
    url = url.rstrip('/')
    url = re.sub(r'/tree/.*$', '', url)  # Remove branch/tree paths
    url = re.sub(r'/blob/.*$', '', url)  # Remove file paths

    return url

def is_valid_github_url(url: str) -> bool:
    """
    Validates if a string is a valid GitHub URL or username.
    """
    if not url or pd.isna(url):
        return False

    url = str(url).strip()

    # Check for valid GitHub URL patterns
    github_patterns = [
        r'^https?://github\.com/[a-zA-Z0-9_-]+/?$',
        r'^https?://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+/?$',
        r'^[a-zA-Z0-9_-]+$',  # Just username
        r'^[a-zA-Z0-9_-]+/[a-zA-Z0-9._-]+$',  # username/repo
    ]

    return any(re.match(pattern, url) for pattern in github_patterns)

def extract_user_and_repo(github_url):
    """
    Extracts (username, repo_name) from a GitHub URL or string.
    Returns (username, repo_name) or (username, None) if only username is present.
    Handles:
      - https://github.com/username
      - https://github.com/username/repo
      - username
      - username/repo
    """
    if not github_url or pd.isna(github_url):
        return (None, None)
    url = str(github_url).strip().rstrip('/')
    # Remove protocol if present
    url = re.sub(r'^https?://', '', url)
    # Remove github.com if present
    url = re.sub(r'^github\.com/', '', url, flags=re.IGNORECASE)
    parts = url.split('/')
    if len(parts) == 1:
        return (parts[0], None)
    elif len(parts) >= 2:
        return (parts[0], parts[1])
    return (None, None)

def extract_username(github_url):
    """
    Extracts the username from a GitHub URL or string.
    Handles both user and repo URLs.
    Example: https://github.com/john123 -> john123
             https://github.com/john123/repo -> john123
    """
    username, _ = extract_user_and_repo(github_url)
    return username
