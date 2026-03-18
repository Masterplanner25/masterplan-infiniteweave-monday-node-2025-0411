"""
ARM Core Analysis Engine

The reasoning heart of A.I.N.D.Y.'s Autonomous Reasoning Module.
Powered by OpenAI GPT-4o.

Capabilities:
- run_analysis()  : Deep code/logic analysis with architectural insights
- generate_code() : Code generation and refactoring

Every operation is:
- Security validated before execution
- Logged to PostgreSQL (analysis_results / code_generations)
- Tagged with an Infinity Algorithm Task Priority score
- Fully traceable and auditable
"""
import json
import time
import uuid

from openai import OpenAI
from sqlalchemy.orm import Session

from modules.deepseek.security_deepseek import SecurityValidator
from modules.deepseek.file_processor_deepseek import FileProcessor
from modules.deepseek.config_manager_deepseek import ConfigManager
from db.models.arm_models import AnalysisResult, CodeGeneration
from config import settings


# ── System prompts ────────────────────────────────────────────────────────────

ANALYSIS_SYSTEM_PROMPT = """You are ARM — the Autonomous Reasoning Module of A.I.N.D.Y.,
an AI-powered productivity system built on the Infinity Algorithm.

Your role is to analyze code and logic with the precision of a senior architect.
For every analysis you produce:

1. ARCHITECTURE ASSESSMENT — structural patterns, separation of concerns, design quality
2. PERFORMANCE INSIGHTS — bottlenecks, inefficiencies, optimization opportunities
3. INTEGRITY AUDIT — bugs, edge cases, error handling gaps
4. IMPROVEMENT ROADMAP — prioritized, actionable recommendations

Be specific. Reference file structure, function names, and line ranges where relevant.
Every insight must be actionable.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
{
  "summary": "2-3 sentence executive summary",
  "architecture_score": <1-10>,
  "performance_score": <1-10>,
  "integrity_score": <1-10>,
  "findings": [
    {
      "category": "architecture|performance|integrity|improvement",
      "severity": "critical|high|medium|low",
      "title": "short title",
      "description": "detailed description",
      "recommendation": "specific action to take"
    }
  ],
  "overall_recommendation": "primary next action"
}"""

GENERATION_SYSTEM_PROMPT = """You are ARM — the code generation engine of A.I.N.D.Y.'s
Autonomous Reasoning Module.

Your role is to generate, refactor, or improve code with precision and intent.
Every generation includes:

1. GENERATED CODE — clean, well-commented, production-ready
2. EXPLANATION — what changed and why
3. QUALITY NOTES — known limitations, edge cases, next steps

Return ONLY valid JSON (no markdown fences) with exactly these keys:
{
  "generated_code": "the complete code output",
  "language": "python|javascript|etc",
  "explanation": "what was done and why",
  "quality_notes": "limitations, edge cases, suggestions",
  "confidence": <1-10>
}"""


class DeepSeekCodeAnalyzer:
    """
    ARM reasoning engine — analysis and code generation via OpenAI GPT-4o.

    Initialised once per server process (singleton in arm_router.py).
    Thread-safe: each call creates its own DB records and does not mutate
    shared state beyond the singleton's config reference.
    """

    def __init__(self, config_path: str = None):
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_all()
        self.validator = SecurityValidator(self.config)
        self.file_processor = FileProcessor(self.config)
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)

    # ── Internal OpenAI call ─────────────────────────────────────────────────

    def _call_openai(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str = None,
        temperature: float = None,
    ) -> tuple:
        """
        Call the OpenAI chat completions API with retry logic.

        Returns (response_text: str, input_tokens: int, output_tokens: int).
        Raises the last exception if all retries are exhausted.
        """
        model = model or self.config.get("model", "gpt-4o")
        temperature = temperature if temperature is not None else self.config.get("temperature", 0.2)
        retry_limit = self.config.get("retry_limit", 3)
        retry_delay = self.config.get("retry_delay_seconds", 2)
        max_tokens = self.config.get("max_output_tokens", 2000)

        last_exc = None
        for attempt in range(retry_limit):
            try:
                response = self.client.chat.completions.create(
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                content = response.choices[0].message.content
                usage = response.usage
                return content, usage.prompt_tokens, usage.completion_tokens
            except Exception as exc:
                last_exc = exc
                if attempt < retry_limit - 1:
                    time.sleep(retry_delay)
        raise last_exc

    # ── Analysis ─────────────────────────────────────────────────────────────

    def run_analysis(
        self,
        file_path: str,
        user_id: str,
        db: Session,
        complexity: float = None,
        urgency: float = None,
        additional_context: str = "",
    ) -> dict:
        """
        Analyze a code file and return structured architectural insights.

        Pipeline:
        1. Security validation (path, content, size)
        2. File reading and chunking
        3. Task Priority calculation (Infinity Algorithm)
        4. OpenAI GPT-4o analysis
        5. Persist to analysis_results table
        6. Return enriched result dict
        """
        start_time = time.time()
        session_id = uuid.uuid4()
        task_priority = self.config_manager.calculate_task_priority(
            complexity=complexity, urgency=urgency
        )

        try:
            # Step 1 — Security validation
            path, content = self.validator.full_file_validation(file_path)

            # Step 2 — Chunk if needed
            chunks = self.file_processor.chunk_content(content)

            # Step 3 — Build prompt
            context_section = (
                f"\nAdditional context: {additional_context}\n"
                if additional_context else ""
            )
            truncation_note = (
                f"\n(File truncated — showing chunk 1 of {len(chunks)})"
                if len(chunks) > 1 else ""
            )
            user_prompt = (
                f"Analyze this {path.suffix} file:\n\n"
                f"File: {path.name}\n"
                f"{context_section}"
                f"```{path.suffix.lstrip('.')}\n"
                f"{chunks[0]}\n"
                f"```"
                f"{truncation_note}"
            )

            # Step 4 — Call OpenAI
            result_text, input_tokens, output_tokens = self._call_openai(
                system_prompt=ANALYSIS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.config.get("analysis_model", "gpt-4o"),
                temperature=self.config.get("temperature", 0.2),
            )

            # Step 5 — Parse JSON response
            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {"summary": result_text, "findings": []}

            execution_seconds = time.time() - start_time

            # Step 6 — Persist to DB
            db_record = AnalysisResult(
                id=uuid.uuid4(),
                session_id=session_id,
                user_id=user_id,
                file_path=str(path),
                file_type=path.suffix,
                analysis_type="analyze",
                prompt_used=user_prompt[:2000],
                model_used=self.config.get("analysis_model", "gpt-4o"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                execution_seconds=execution_seconds,
                result_summary=result.get("summary", ""),
                result_full=result_text,
                task_priority=task_priority,
                status="success",
            )
            db.add(db_record)
            db.commit()

            # Step 7 — Return enriched result
            result["session_id"] = str(session_id)
            result["analysis_id"] = str(db_record.id)
            result["file"] = path.name
            result["execution_seconds"] = round(execution_seconds, 3)
            result["input_tokens"] = input_tokens
            result["output_tokens"] = output_tokens
            result["task_priority"] = round(task_priority, 2)
            result["execution_speed"] = round(
                (input_tokens + output_tokens) / max(execution_seconds, 0.001), 1
            )
            return result

        except Exception as exc:
            execution_seconds = time.time() - start_time
            # Log failed attempt so audit trail is complete
            try:
                db.add(
                    AnalysisResult(
                        id=uuid.uuid4(),
                        session_id=session_id,
                        user_id=user_id,
                        file_path=file_path,
                        file_type="unknown",
                        analysis_type="analyze",
                        model_used=self.config.get("analysis_model", "gpt-4o"),
                        input_tokens=0,
                        output_tokens=0,
                        execution_seconds=execution_seconds,
                        task_priority=task_priority,
                        status="failed",
                        error_message=str(exc),
                    )
                )
                db.commit()
            except Exception:
                pass
            raise

    # ── Generation ───────────────────────────────────────────────────────────

    def generate_code(
        self,
        prompt: str,
        user_id: str,
        db: Session,
        original_code: str = "",
        language: str = "python",
        generation_type: str = "generate",
        analysis_id: str = None,
        complexity: float = None,
        urgency: float = None,
    ) -> dict:
        """
        Generate or refactor code based on a natural-language prompt.

        Pipeline:
        1. Security validation of any provided code
        2. Task Priority calculation (Infinity Algorithm)
        3. OpenAI GPT-4o generation
        4. Persist to code_generations table
        5. Return structured result
        """
        start_time = time.time()
        session_id = uuid.uuid4()
        task_priority = self.config_manager.calculate_task_priority(
            complexity=complexity, urgency=urgency
        )

        try:
            # Validate any provided code before sending to OpenAI
            if original_code:
                self.validator.validate_code_input(original_code)

            # Build generation prompt
            code_section = (
                f"\n\nExisting code to refactor:\n```{language}\n{original_code}\n```"
                if original_code else ""
            )
            user_prompt = (
                f"Language: {language}\n"
                f"Task: {prompt}"
                f"{code_section}"
            )

            # Call OpenAI
            result_text, input_tokens, output_tokens = self._call_openai(
                system_prompt=GENERATION_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                model=self.config.get("generation_model", "gpt-4o"),
                temperature=self.config.get("generation_temperature", 0.4),
            )

            try:
                result = json.loads(result_text)
            except json.JSONDecodeError:
                result = {
                    "generated_code": result_text,
                    "language": language,
                    "explanation": "",
                    "quality_notes": "",
                    "confidence": 5,
                }

            execution_seconds = time.time() - start_time

            # Parse analysis_id to UUID if provided
            analysis_uuid = None
            if analysis_id:
                try:
                    analysis_uuid = uuid.UUID(analysis_id)
                except ValueError:
                    pass

            # Persist to DB
            db_record = CodeGeneration(
                id=uuid.uuid4(),
                session_id=session_id,
                user_id=user_id,
                analysis_id=analysis_uuid,
                generation_type=generation_type,
                original_code=original_code[:10_000] if original_code else "",
                generated_code=result.get("generated_code", ""),
                language=result.get("language", language),
                model_used=self.config.get("generation_model", "gpt-4o"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                execution_seconds=execution_seconds,
                quality_notes=result.get("quality_notes", ""),
            )
            db.add(db_record)
            db.commit()

            result["session_id"] = str(session_id)
            result["generation_id"] = str(db_record.id)
            result["execution_seconds"] = round(execution_seconds, 3)
            result["input_tokens"] = input_tokens
            result["output_tokens"] = output_tokens
            result["task_priority"] = round(task_priority, 2)
            return result

        except Exception:
            raise
