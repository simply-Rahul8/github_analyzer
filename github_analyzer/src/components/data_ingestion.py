import pandas as pd
import os
import re
from typing import List, Dict, Tuple
from src.logger.logging_config import setup_logging
from src.utils.common import clean_github_url, is_valid_github_url

logger = setup_logging()

class DataIngestion:
    def read_students_file(self, file_path):
        """
        Reads the student Excel file and returns a list of dictionaries.
        Automatically detects columns for student names and GitHub URLs.
        Removes duplicates and handles various column naming conventions.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            df = pd.read_excel(file_path)

            # Remove completely empty rows
            df = df.dropna(how='all')

            # Detect columns
            name_col, github_col = self.detect_columns(df)

            if not name_col or not github_col:
                available_cols = list(df.columns)
                raise ValueError(f"Could not automatically detect required columns. Available columns: {available_cols}. "
                               f"Expected columns containing student names and GitHub URLs.")

            # Extract only the required columns and rename them
            df_clean = df[[name_col, github_col]].copy()
            df_clean.columns = ['name of the student', 'github link']

            # Remove rows with missing values in either column
            df_clean = df_clean.dropna(subset=['name of the student', 'github link'])

            # Convert to string and clean data
            df_clean['name of the student'] = df_clean['name of the student'].astype(str).str.strip()
            df_clean['github link'] = df_clean['github link'].astype(str).str.strip()

            # Remove empty strings
            df_clean = df_clean[
                (df_clean['name of the student'] != '') &
                (df_clean['github link'] != '')
            ]

            # Remove duplicates based on both name and GitHub link
            initial_count = len(df_clean)
            df_clean = df_clean.drop_duplicates(subset=['name of the student', 'github link'], keep='first')
            duplicates_removed = initial_count - len(df_clean)

            if duplicates_removed > 0:
                logger.info(f"Removed {duplicates_removed} duplicate entries")

            # Validate GitHub URLs
            df_clean['github link'] = df_clean['github link'].apply(clean_github_url)

            # Remove invalid GitHub URLs
            valid_github_mask = df_clean['github link'].apply(is_valid_github_url)
            invalid_count = len(df_clean) - valid_github_mask.sum()
            df_clean = df_clean[valid_github_mask]

            if invalid_count > 0:
                logger.info(f"Removed {invalid_count} entries with invalid GitHub URLs")

            final_count = len(df_clean)
            logger.info(f"Successfully processed {final_count} student entries")

            return df_clean.to_dict("records")

        except Exception as e:
            raise Exception(f"Error reading Excel file: {e}")

    def detect_columns(self, df) -> Tuple[str, str]:
        """
        Automatically detects columns containing student names and GitHub URLs.
        Returns (name_column, github_column) or (None, None) if not found.
        """
        df.columns = [str(col).strip().lower() for col in df.columns]

        # Possible name column patterns
        name_patterns = [
            r'.*name.*', r'.*student.*', r'.*user.*', r'.*person.*',
            r'full.?name', r'first.?name', r'last.?name', r'student.?name'
        ]

        # Possible GitHub column patterns
        github_patterns = [
            r'.*github.*', r'.*repo.*', r'.*link.*', r'.*url.*',
            r'.*profile.*', r'.*account.*', r'git.*link'
        ]

        name_col = None
        github_col = None

        # Find name column
        for col in df.columns:
            for pattern in name_patterns:
                if re.search(pattern, col, re.IGNORECASE):
                    name_col = col
                    break
            if name_col:
                break

        # Find GitHub column
        for col in df.columns:
            for pattern in github_patterns:
                if re.search(pattern, col, re.IGNORECASE):
                    github_col = col
                    break
            if github_col:
                break

        # If pattern matching fails, try content-based detection
        if not name_col:
            name_col = self.detect_name_column_by_content(df)
        if not github_col:
            github_col = self.detect_github_column_by_content(df)

        return name_col, github_col

    def detect_name_column_by_content(self, df) -> str:
        """
        Detects name column by analyzing the content of columns.
        """
        for col in df.columns:
            if col in ['name of the student', 'github link']:  # Skip already identified columns
                continue

            sample_values = df[col].dropna().astype(str).head(10)

            # Check if values look like names (contain letters, possibly spaces)
            name_like_count = 0
            for value in sample_values:
                value = value.strip()
                if (len(value) > 1 and len(value) < 50 and
                    re.search(r'[a-zA-Z]', value) and
                    not re.search(r'https?://', value) and
                    not re.search(r'\d{4,}', value)):  # Avoid URLs and long numbers
                    name_like_count += 1

            if name_like_count >= len(sample_values) * 0.7:  # 70% of samples look like names
                return col

        return None

    def detect_github_column_by_content(self, df) -> str:
        """
        Detects GitHub column by analyzing the content of columns.
        """
        for col in df.columns:
            if col in ['name of the student', 'github link']:  # Skip already identified columns
                continue

            sample_values = df[col].dropna().astype(str).head(10)

            # Check if values look like GitHub URLs
            github_like_count = 0
            for value in sample_values:
                value = value.strip()
                if (re.search(r'github\.com', value, re.IGNORECASE) or
                    re.search(r'githubusercontent\.com', value, re.IGNORECASE) or
                    (len(value) > 10 and '/' in value and not value.startswith('http'))):  # username/repo format
                    github_like_count += 1

            if github_like_count >= len(sample_values) * 0.6:  # 60% of samples look like GitHub links
                return col

        return None
