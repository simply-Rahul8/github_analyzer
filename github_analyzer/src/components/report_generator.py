import pandas as pd
import re
from src.logger.logging_config import setup_logging
from src.scoring import determine_rating_category, rating_scale_text

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

    def _format_breakdown_text(self, breakdown):
        """Turn the deterministic rubric into a readable plain-text block."""
        if not breakdown:
            return ""
        # New rubric uses 1 point per category
        return "\n".join(
            f"- {name}: {points}/1 - {reason}" for name, points, reason in breakdown
        )

    def _compose_feedback_with_breakdown(self, row):
        """Build feedback text that includes the deterministic score breakdown."""
        feedback = row.get("Feedback", "") or row.get("feedback", "") or ""
        breakdown = row.get("score_breakdown") or []

        if not breakdown:
            return feedback

        breakdown_text = "\n\nSCORING BREAKDOWN:\n" + self._format_breakdown_text(breakdown)
        return f"{feedback}\n{breakdown_text}".strip()

    def write_evaluation_file(self, results, output_file="evaluation.xlsx"):
        """
        Writes the list of result dictionaries to an Excel file with only the requested minimal fields.
        """
        try:
            export_rows = []
            for idx, result in enumerate(results, start=1):
                if not isinstance(result, dict):
                    continue

                normalized = dict(result)
                github_url = normalized.get("github_link") or normalized.get("GitHub Link") or normalized.get("github_url") or ""
                repo_name = normalized.get("student_name") or normalized.get("name of the student") or normalized.get("label") or ""
                if not repo_name and github_url:
                    repo_name = github_url.rstrip("/").split("/")[-1]

                selection = normalized.get("selection") or ""
                shortlisted = "Yes" if selection == "Shortlisted" else "No"

                repo_category = normalized.get("repo_category") or normalized.get("category") or normalized.get("repository_category") or ""

                export_rows.append({
                    "Serial number": idx,
                    "GitHub repo": repo_name,
                    "GitHub URL": github_url,
                    "Shortlisted": shortlisted,
                    "Repository Category": repo_category,
                })

            if not export_rows:
                logger.warning("No results to write to Excel.")
                return

            df = pd.DataFrame(export_rows)
            df.to_excel(output_file, index=False)
            logger.info(f"Successfully wrote results to {output_file}")
        except Exception as e:
            logger.error(f"Error writing to Excel: {e}")
