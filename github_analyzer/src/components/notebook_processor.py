import nbformat
import requests
from src.constants import Config
from src.logger.logging_config import setup_logging

logger = setup_logging()

class NotebookProcessor:
    def __init__(self):
        self.important_keywords = Config.IMPORTANT_KEYWORDS
        self.max_chars = Config.MAX_NOTEBOOK_CHARS

    def _is_important(self, cell_text):
        return any(keyword in cell_text.lower() for keyword in self.important_keywords)

    def parse_notebook_from_url(self, url):
        """
        Downloads a notebook from a URL and converts it to a filtered text string.
        Uses smart filtering and token budget strategy.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()
            
            nb = nbformat.reads(response.text, as_version=4)
            
            current_size = 0
            text = ""
            
            for cell in nb.cells:
                if cell.cell_type == "markdown":
                    # Keep markdown short
                    if len(cell.source) < 500:
                        cell_text = f"[MARKDOWN]\n{cell.source}\n\n"
                        if current_size + len(cell_text) > self.max_chars:
                            break
                        text += cell_text
                        current_size += len(cell_text)
                        
                elif cell.cell_type == "code":
                    # Skip very long cells
                    if len(cell.source) > 1500:
                        continue
                    
                    # Keep only important DS cells
                    if self._is_important(cell.source):
                        cell_text = f"[CODE]\n{cell.source}\n\n"
                        if current_size + len(cell_text) > self.max_chars:
                            break
                        text += cell_text
                        current_size += len(cell_text)
                    
            return text
        except Exception as e:
            logger.error(f"Error parsing notebook: {e}")
            raise Exception(f"Error parsing notebook: {e}")
