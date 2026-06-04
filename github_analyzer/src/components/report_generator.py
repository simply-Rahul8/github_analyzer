import pandas as pd
import re
from src.logger.logging_config import setup_logging

logger = setup_logging()


class ReportGenerator:
    def parse_llm_response(self, response_text):
        """
        Parses the structured LLM response and combines all sections
        into a single 'feedback' string with Positives, Negatives,
        Improvements, and Overall Rating sections.
        """
        header_pattern = re.compile(
            r"^[\#\*]*\s*(OVERALL RATING|POSITIVES|NEGATIVES|IMPROVEMENTS)[\s\:\*]*",
            re.IGNORECASE
        )
        sections = {
            "overall_rating": "",
            "positives": "",
            "negatives": "",
            "improvements": ""
        }

        current_section = None
        lines = response_text.split('\n')
        for line in lines:
            stripped_line = line.strip()
            match = header_pattern.match(stripped_line)
            if match:
                raw_section = match.group(1).upper()
                # Everything after the header keyword on the same line
                remainder = stripped_line[match.end():].strip().lstrip(':').strip()

                if raw_section == "OVERALL RATING":
                    current_section = "overall_rating"
                    # Try to grab the value right off the header line itself
                    if remainder:
                        inline_rating = re.search(r"(\d+(?:\.\d+)?)(?:\/10)?", remainder)
                        if inline_rating:
                            val = inline_rating.group(1)
                            sections["overall_rating"] = val + "/10"
                elif raw_section == "POSITIVES":
                    current_section = "positives"
                elif raw_section == "NEGATIVES":
                    current_section = "negatives"
                elif raw_section == "IMPROVEMENTS":
                    current_section = "improvements"
                else:
                    current_section = None
                continue

            if current_section and stripped_line:
                if current_section == "overall_rating":
                    # Value on next line (fallback)
                    if not sections["overall_rating"]:
                        rating_match = re.search(r"(\d+(?:\.\d+)?)\/10", stripped_line)
                        if rating_match:
                            sections["overall_rating"] = rating_match.group(1) + "/10"
                        elif re.match(r"^\d+$", stripped_line):
                            sections["overall_rating"] = stripped_line + "/10"
                else:
                    sections[current_section] += stripped_line + "\n"

        for key in sections:
            sections[key] = sections[key].strip()

        # Combine all sections into a single feedback string
        feedback_parts = []

        if sections["positives"]:
            feedback_parts.append(f"POSITIVES:\n{sections['positives']}")

        if sections["negatives"]:
            feedback_parts.append(f"NEGATIVES:\n{sections['negatives']}")

        if sections["improvements"]:
            feedback_parts.append(f"IMPROVEMENTS:\n{sections['improvements']}")

        if sections["overall_rating"]:
            feedback_parts.append(f"OVERALL RATING: {sections['overall_rating']}")

        feedback = "\n\n".join(feedback_parts)

        return {
            "feedback": feedback,
            "overall_rating": sections["overall_rating"]
        }

    def write_evaluation_file(self, results, output_file="evaluation.xlsx"):
        """
        Writes the list of result dictionaries to an Excel file
        with a single 'Feedback' column containing all evaluation sections.
        """
        try:
            column_mapping = {
                "student_name": "Name / Repo",
                "github_link": "GitHub Link",
                "repo_found": "Repo Found",
                "files_analyzed": "Files Analyzed",
                "feedback": "Feedback"
            }

            df = pd.DataFrame(results)

            if df.empty:
                logger.warning("No results to write to Excel.")
                return

            # Normalise: if 'label' exists but not 'student_name', use it
            if "student_name" not in df.columns and "label" in df.columns:
                df["student_name"] = df["label"]

            rename_map = {k: v for k, v in column_mapping.items() if k in df.columns}
            df = df.rename(columns=rename_map)

            desired_columns = [v for v in column_mapping.values()]
            df = df[[col for col in desired_columns if col in df.columns]]

            df.to_excel(output_file, index=False)
            logger.info(f"Successfully wrote results to {output_file}")
        except Exception as e:
            logger.error(f"Error writing to Excel: {e}")
