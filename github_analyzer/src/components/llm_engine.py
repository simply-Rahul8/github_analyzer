import time
from groq import Groq
from src.constants import Config, SYSTEM_PROMPT, COMPRESSION_PROMPT
from src.logger.logging_config import setup_logging

logger = setup_logging()


class LLMEngine:
    def __init__(self):
        self.api_key = Config.GROQ_API_KEY
        self.client  = Groq(api_key=self.api_key) if self.api_key else None

    def analyze_repo(self, repo_content, user_context=None, summary=None):
        """
        Two-step evaluation pipeline:
          1. Compress raw repo content into a focused technical summary (fast model)
          2. Evaluate that summary against user context (capable model)
        """
        if summary is None:
            summary = self.compress_repo_content(repo_content)
        return self.evaluate_summary(summary, user_context)

    def validate_requirement(self, summary, requirement_text):
        """
        Validates whether the repository summary satisfies the provided business requirement.
        Returns a dict with requirement_met, requirement_matches, and requirement_summary.
        """
        if not self.client:
            raise ValueError("GROQ_API_KEY not found in configuration")
        if not requirement_text or not requirement_text.strip():
            return {
                "requirement_present": False,
                "requirement_met": None,
                "requirement_matches": [],
                "requirement_summary": "",
            }

        time.sleep(Config.DELAY_BETWEEN_REQUESTS)
        prompt = (
            "You are a helpful technical evaluator.\n"
            "A business requirement is provided, and you must determine whether the repository content satisfies it.\n"
            "Answer in EXACTLY this format with no extra text:\n"
            "REQUIREMENT_MET: YES or NO\n"
            "EVIDENCE: Briefly describe the repository content that supports your answer.\n"
            "SUMMARY: One concise sentence explaining why the requirement is satisfied or not.\n\n"
            "Repository summary:\n" + summary + "\n\n"
            "Business requirement:\n" + requirement_text.strip() + "\n"
        )

        retries = 3
        response_text = ""
        for attempt in range(retries):
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": "You are a precise evaluator who answers with structured output."},
                        {"role": "user", "content": prompt},
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.0,
                )
                response_text = chat_completion.choices[0].message.content.strip()
                break
            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    wait_time = (attempt + 1) * 30
                    logger.warning(
                        f"Requirement validation rate limit hit (Attempt {attempt+1}/{retries}). Sleeping {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Requirement validation failed: {e}")
                    response_text = ""
                    break

        requirement_met = None
        evidence = ""
        summary_text = ""
        if response_text:
            for line in response_text.splitlines():
                if line.strip().upper().startswith("REQUIREMENT_MET:"):
                    value = line.split(":", 1)[1].strip().upper()
                    if value == "YES":
                        requirement_met = True
                    elif value == "NO":
                        requirement_met = False
                elif line.strip().upper().startswith("EVIDENCE:"):
                    evidence = line.split(":", 1)[1].strip()
                elif line.strip().upper().startswith("SUMMARY:"):
                    summary_text = line.split(":", 1)[1].strip()

        if requirement_met is None:
            if "yes" in response_text.lower() and "no" not in response_text.lower():
                requirement_met = True
            elif "no" in response_text.lower():
                requirement_met = False

        if summary_text == "" and evidence:
            summary_text = evidence

        if summary_text == "" and response_text:
            summary_text = response_text.replace("\n", " ")[:300]

        return {
            "requirement_present": bool(requirement_text and requirement_text.strip()),
            "requirement_met": requirement_met,
            "requirement_matches": [],
            "requirement_summary": summary_text,
            "requirement_evidence": evidence,
        }
    
    def compress_repo_content(self, repo_content):
        """
        Compresses repository content into a focused technical summary
        using a fast model. Falls back to truncated raw content on failure.
        """
        if not self.client:
            raise ValueError("GROQ_API_KEY not found in configuration")
        time.sleep(4)  # Throttle

        retries = 3
        for attempt in range(retries):
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are an experienced technical mentor. "
                                "Produce concise, factual summaries of student/hackathon GitHub repositories."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"{COMPRESSION_PROMPT}\n\n"
                                f"Repository content:\n\n{repo_content}"
                            ),
                        }
                    ],
                    model="llama-3.1-8b-instant",
                    temperature=0.3,
                    max_tokens=800,      # raised from 500 for richer summaries
                )
                return chat_completion.choices[0].message.content

            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    wait_time = (attempt + 1) * 30
                    logger.warning(
                        f"Compression rate limit hit (Attempt {attempt+1}/{retries}). "
                        f"Sleeping {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    logger.warning(f"Compression failed, using raw content fallback: {e}")
                    return repo_content[:4000]

    def evaluate_summary(self, summary, user_context=None):
        """
        Evaluates a compressed repo summary against the user's criteria.
        Returns structured POSITIVES / NEGATIVES / IMPROVEMENTS feedback.
        """
        if not self.client:
            raise ValueError("GROQ_API_KEY not found in configuration")
        time.sleep(Config.DELAY_BETWEEN_REQUESTS)

        ctx = (
            user_context if user_context and user_context.strip()
            else (
                "Evaluate this repository as a student hackathon or college project. "
                "Focus on whether the core idea works, code readability, basic folder organization, "
                "and whether the README explains the project. Do NOT penalize for missing tests, "
                "CI/CD, deployment setup, or any professional/industry features."
            )
        )

        system_prompt = SYSTEM_PROMPT.format(user_context=ctx)

        retries = 3
        for attempt in range(retries):
            try:
                chat_completion = self.client.chat.completions.create(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": f"Here is the repository summary:\n\n{summary}",
                        }
                    ],
                    model="llama-3.3-70b-versatile",
                    temperature=0.1,
                )
                return chat_completion.choices[0].message.content

            except Exception as e:
                if "429" in str(e) and attempt < retries - 1:
                    wait_time = (attempt + 1) * 30
                    logger.warning(
                        f"Evaluation rate limit hit (Attempt {attempt+1}/{retries}). "
                        f"Sleeping {wait_time}s..."
                    )
                    time.sleep(wait_time)
                else:
                    raise Exception(f"Error calling Groq API: {e}")
