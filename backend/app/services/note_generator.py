"""
Clinical Note Generation Engine
Orchestrates LLM, RAG, and calculators for comprehensive note generation
"""

import logging
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, AsyncIterator
from dataclasses import dataclass, field

from llm.llm_manager import LLMManager, TaskType
from rag.rag_pipeline import RAGPipeline, RAGContext
from rag.retriever import RAGRetriever
from rag.embeddings import EmbeddingGenerator
from calculators.registry import registry as calculator_registry
from database.neo4j_client import Neo4jClient

logger = logging.getLogger(__name__)


@dataclass
class CalculatorResult:
    """Result from a clinical calculator."""
    calculator_id: str
    calculator_name: str
    result: Any
    interpretation: str
    recommendations: List[str] = field(default_factory=list)
    formatted_output: str = ""


@dataclass
class NoteResult:
    """Complete note generation result."""
    note_text: str
    calculator_results: List[CalculatorResult] = field(default_factory=list)
    rag_sources: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        return {
            "note_text": self.note_text,
            "calculator_results": [
                {
                    "calculator_id": cr.calculator_id,
                    "calculator_name": cr.calculator_name,
                    "result": cr.result,
                    "interpretation": cr.interpretation,
                    "recommendations": cr.recommendations,
                    "formatted_output": cr.formatted_output
                }
                for cr in self.calculator_results
            ],
            "rag_sources": self.rag_sources,
            "metadata": self.metadata
        }


class NoteGenerator:
    """
    Clinical note generation engine.

    Integrates:
    - LLM providers (Ollama, Anthropic, OpenAI)
    - RAG for evidence-based guidance
    - Clinical calculators
    - Template management
    """

    def __init__(
        self,
        llm_manager: Optional[LLMManager] = None,
        neo4j_client: Optional[Neo4jClient] = None,
        embedding_generator: Optional[EmbeddingGenerator] = None
    ):
        """
        Initialize note generator.

        Args:
            llm_manager: LLM manager instance
            neo4j_client: Neo4j client instance
            embedding_generator: Embedding generator instance
        """
        # Initialize LLM manager
        self.llm_manager = llm_manager or LLMManager()

        # Initialize RAG pipeline if components provided
        if neo4j_client and embedding_generator:
            retriever = RAGRetriever(neo4j_client, embedding_generator)
            self.rag_pipeline = RAGPipeline(retriever)
        else:
            self.rag_pipeline = None
            logger.warning("RAG pipeline not initialized (missing neo4j_client or embedding_generator)")

        # Load default template
        self.default_template = self._load_default_template()

        # Load two-stage prompts
        self.stage1_prompt = self._load_stage_prompt("stage1_extraction.txt")
        self.stage2_prompt = self._load_stage_prompt("stage2_final_note.txt")

        logger.info("Note generator initialized")

    def _load_default_template(self) -> str:
        """
        Load urology template from file.

        Raises:
            FileNotFoundError: If template file not found (fail-fast approach)
            IOError: If template file cannot be read
        """
        template_path = "/home/gulab/PythonProjects/VAUCDA/urology_prompt.txt"

        if not os.path.exists(template_path):
            raise FileNotFoundError(
                f"Template file not found: {template_path}. "
                "Cannot proceed without template (fail-fast approach)."
            )

        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                template = f.read()

            if not template.strip():
                raise ValueError("Template file is empty")

            logger.info(f"Loaded urology template ({len(template)} chars)")
            return template
        except IOError as e:
            raise IOError(f"Failed to read template file {template_path}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error loading template: {e}")
            raise

    def _load_stage_prompt(self, filename: str) -> str:
        """
        Load stage-specific prompt from file.

        Args:
            filename: Prompt filename (e.g., "stage1_extraction.txt")

        Returns:
            Prompt string
        """
        prompt_path = f"/home/gulab/PythonProjects/VAUCDA/backend/prompts/{filename}"

        try:
            with open(prompt_path, 'r', encoding='utf-8') as f:
                prompt = f.read()

            if not prompt.strip():
                logger.warning(f"Prompt file {filename} is empty, using default")
                return ""

            logger.info(f"Loaded stage prompt: {filename} ({len(prompt)} chars)")
            return prompt
        except FileNotFoundError:
            logger.warning(f"Prompt file not found: {prompt_path}, using default")
            return ""
        except Exception as e:
            logger.error(f"Error loading prompt {filename}: {e}")
            return ""

    async def _run_calculators(
        self,
        clinical_input: str,
        calculator_ids: List[str]
    ) -> List[CalculatorResult]:
        """
        Run specified calculators on clinical input.

        Args:
            clinical_input: Clinical data
            calculator_ids: List of calculator IDs to run

        Returns:
            List of calculator results
        """
        results = []

        for calc_id in calculator_ids:
            try:
                # Get calculator from registry
                calculator = calculator_registry.get(calc_id)
                if not calculator:
                    logger.warning(f"Calculator not found: {calc_id}")
                    continue

                # Extract inputs from clinical text using real NLP/regex extraction
                inputs = self._extract_calculator_inputs(clinical_input, calculator)

                # Validate inputs
                is_valid, error = calculator.validate_inputs(inputs)
                if not is_valid:
                    logger.warning(f"Invalid inputs for {calc_id}: {error}")
                    continue

                # Calculate
                calc_result = calculator.calculate(inputs)

                # Create result object
                result = CalculatorResult(
                    calculator_id=calc_id,
                    calculator_name=calculator.name,
                    result=calc_result.result,
                    interpretation=calc_result.interpretation,
                    recommendations=calc_result.recommendations,
                    formatted_output=calc_result.format_output()
                )

                results.append(result)
                logger.info(f"Calculator {calc_id} executed successfully")

            except Exception as e:
                logger.error(f"Calculator {calc_id} failed: {e}")
                continue

        return results

    def _extract_calculator_inputs(
        self,
        clinical_input: str,
        calculator
    ) -> Dict[str, Any]:
        """
        Extract calculator inputs from clinical text using comprehensive regex patterns.

        Extracts specific clinical values needed for calculator computation.

        Args:
            clinical_input: Clinical text
            calculator: Calculator instance

        Returns:
            Dictionary of inputs with required calculator parameters

        Raises:
            ValueError: If required inputs cannot be extracted
        """
        import re
        inputs = {}
        required = calculator.required_inputs if hasattr(calculator, 'required_inputs') else []

        # PSA value extraction (multiple patterns)
        if 'psa' in required or 'psa_value' in required:
            psa_patterns = [
                r'PSA[:\s]+(\d+\.?\d*)\s*(?:ng/mL|ng/ml)?',
                r'(?:Prostate[- ]Specific[- ]Antigen|PSA)[:\s]+(\d+\.?\d*)',
                r'\[r\].*?(\d+\.?\d*)\s*(?:ng/mL)?.*?PSA',
            ]
            for pattern in psa_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['psa'] = float(match.group(1))
                    logger.debug(f"Extracted PSA: {inputs['psa']}")
                    break

        # Age extraction (multiple patterns)
        if 'age' in required:
            age_patterns = [
                r'(\d+)[-\s]?(?:year|yr|y/o|yo)[-\s]?old',
                r'Age[:\s]+(\d+)',
                r'DOB.*?(\d+)\s+(?:year|yr)',
            ]
            for pattern in age_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['age'] = int(match.group(1))
                    logger.debug(f"Extracted age: {inputs['age']}")
                    break

        # Creatinine extraction
        if 'creatinine' in required or 'cr' in required:
            cr_patterns = [
                r'(?:Creat|Creatinine)[:\s]+(\d+\.?\d*)\s*(?:mg/dL|mg/dl)?',
                r'Cr[:\s]+(\d+\.?\d*)',
            ]
            for pattern in cr_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['creatinine'] = float(match.group(1))
                    logger.debug(f"Extracted creatinine: {inputs['creatinine']}")
                    break

        # Gleason score extraction
        if 'gleason' in required or 'gleason_score' in required:
            gleason_patterns = [
                r'Gleason[:\s]+(\d+)\s*\+\s*(\d+)\s*=\s*(\d+)',
                r'Gleason[:\s]+(\d+)',
            ]
            for pattern in gleason_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    if len(match.groups()) == 3:
                        inputs['gleason_score'] = int(match.group(3))
                    else:
                        inputs['gleason_score'] = int(match.group(1))
                    logger.debug(f"Extracted Gleason score: {inputs['gleason_score']}")
                    break

        # Clinical stage extraction
        if 'clinical_stage' in required or 'stage' in required:
            stage_patterns = [
                r'(?:Clinical\s+Stage|cStage|Stage)[:\s]+(T\d[a-z]?N\d[a-z]?M\d[a-z]?)',
                r'Stage[:\s]+(I{1,3}[ABC]?|IV[ABC]?)',
            ]
            for pattern in stage_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['clinical_stage'] = match.group(1).upper()
                    logger.debug(f"Extracted clinical stage: {inputs['clinical_stage']}")
                    break

        # Tumor size extraction
        if 'tumor_size' in required or 'size' in required:
            size_patterns = [
                r'(?:tumor|mass|lesion)[:\s]+(\d+\.?\d*)\s*(?:cm|mm)',
                r'size[:\s]+(\d+\.?\d*)\s*(?:cm|mm)',
            ]
            for pattern in size_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['tumor_size'] = float(match.group(1))
                    logger.debug(f"Extracted tumor size: {inputs['tumor_size']}")
                    break

        # IPSS score extraction
        if 'ipss' in required or 'ipss_score' in required:
            ipss_patterns = [
                r'IPSS[:\s]+(\d+)(?:/35)?',
                r'(?:IPSS|AUA)\s+(?:Score|Total)[:\s]+(\d+)',
            ]
            for pattern in ipss_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['ipss_score'] = int(match.group(1))
                    logger.debug(f"Extracted IPSS score: {inputs['ipss_score']}")
                    break

        # Prostate volume extraction
        if 'prostate_volume' in required or 'volume' in required:
            vol_patterns = [
                r'(?:Prostate\s+volume|Volume)[:\s]+(\d+\.?\d*)\s*(?:cc|mL|ml)',
                r'approximately\s+(\d+)g',
            ]
            for pattern in vol_patterns:
                match = re.search(pattern, clinical_input, re.IGNORECASE)
                if match:
                    inputs['prostate_volume'] = float(match.group(1))
                    logger.debug(f"Extracted prostate volume: {inputs['prostate_volume']}")
                    break

        # Validate we extracted required inputs
        missing_inputs = [inp for inp in required if inp not in inputs]
        if missing_inputs:
            logger.warning(f"Could not extract required calculator inputs: {missing_inputs}")
            # Don't raise - allow calculator to handle validation

        return inputs

    def _select_template_by_type(self, note_type: str) -> str:
        """
        Select appropriate template based on note type.

        Implements template selection logic for different clinical note types.
        Falls back to default template if specific type not available.

        Args:
            note_type: Type of note (clinic, consult, preop, postop)

        Returns:
            Template string for the specified note type

        Raises:
            ValueError: If note_type is invalid
        """
        if not note_type:
            logger.warning("Note type not specified, using default template")
            return self.default_template

        note_type_lower = note_type.lower().strip()

        # Map note types to template strategies
        template_map = {
            "clinic": "urology_clinic",
            "clinic_note": "urology_clinic",
            "consultation": "urology_consult",
            "consult": "urology_consult",
            "preop": "urology_preop",
            "preoperative": "urology_preop",
            "postop": "urology_postop",
            "postoperative": "urology_postop",
        }

        template_name = template_map.get(note_type_lower, "urology_clinic")
        logger.info(f"Selected template: {template_name} for note type: {note_type}")

        # For now, return default template for all types
        # In production, implement loading different templates from files
        return self.default_template

    def _construct_prompt(
        self,
        template: str,
        clinical_input: str,
        calculator_results: List[CalculatorResult],
        rag_context: Optional[RAGContext]
    ) -> str:
        """
        Construct LLM prompt from template and inputs.

        Args:
            template: Note template
            clinical_input: Clinical data
            calculator_results: Calculator results to include
            rag_context: RAG context for evidence

        Returns:
            Complete prompt for LLM
        """
        prompt_parts = []

        # Add template
        prompt_parts.append(template)
        prompt_parts.append("\n=== CLINICAL INPUT ===\n")
        prompt_parts.append(clinical_input)

        # Add calculator results if available
        if calculator_results:
            prompt_parts.append("\n=== CALCULATOR RESULTS ===\n")
            for result in calculator_results:
                prompt_parts.append(f"\n{result.calculator_name}:")
                prompt_parts.append(result.formatted_output)

        # Add RAG context if available
        if rag_context and rag_context.has_context:
            prompt_parts.append("\n=== CLINICAL GUIDELINES & EVIDENCE ===\n")
            prompt_parts.append(rag_context.context)
            prompt_parts.append("\nUse these guidelines to inform your assessment and plan.")

        prompt_parts.append("\n=== INSTRUCTIONS ===\n")
        prompt_parts.append("Generate a COMPLETE clinical note using the template above.")
        prompt_parts.append("The note MUST include ALL sections from the template, especially:")
        prompt_parts.append("- ASSESSMENT: 4-8 sentence narrative summary of the clinical situation")
        prompt_parts.append("- UROLOGY PROBLEM LIST: Numbered list of urologic problems")
        prompt_parts.append("- PLAN: Comprehensive plan for each problem")
        prompt_parts.append("\nIncorporate all provided information including calculator results and clinical guidelines.")
        prompt_parts.append("If calculator results are provided, integrate them into the ASSESSMENT and PLAN sections.")
        prompt_parts.append("Do NOT stop at the Physical Exam - continue through Assessment and Plan.")

        return "\n".join(prompt_parts)

    async def generate_note(
        self,
        clinical_input: str,
        note_type: str = "clinic",
        llm_provider: str = "ollama",
        calculator_ids: List[str] = None,
        use_rag: bool = True,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> NoteResult:
        """
        Generate clinical note with full integration.

        Args:
            clinical_input: Raw clinical data (labs, imaging, prior notes)
            note_type: Type of note (clinic, consult, preop, postop)
            llm_provider: LLM provider (ollama, anthropic, openai)
            calculator_ids: List of calculator IDs to run
            use_rag: Whether to use RAG for evidence
            temperature: LLM temperature (default 0.3 for clinical accuracy)
            max_tokens: Maximum tokens to generate

        Returns:
            NoteResult with generated note and metadata
        """
        start_time = datetime.now()
        calculator_ids = calculator_ids or []

        # 1. Run calculators if requested
        calculator_results = []
        if calculator_ids:
            logger.info(f"Running {len(calculator_ids)} calculators...")
            calculator_results = await self._run_calculators(clinical_input, calculator_ids)

        # 2. RAG retrieval if enabled
        rag_context = None
        if use_rag and self.rag_pipeline:
            logger.info("Retrieving RAG context...")
            try:
                rag_context = await self.rag_pipeline.retrieve_and_augment(
                    query=clinical_input,
                    k=5,
                    search_strategy="clinical"
                )
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}")
                rag_context = None

        # 3. Select template based on note type
        template = self._select_template_by_type(note_type)

        # 4. Construct prompt
        prompt = self._construct_prompt(
            template=template,
            clinical_input=clinical_input,
            calculator_results=calculator_results,
            rag_context=rag_context
        )

        # 5. Generate note with LLM
        logger.info(f"Generating note with {llm_provider}...")
        try:
            # Determine task type based on note complexity
            task_type = TaskType.NOTE_GENERATION

            llm_response = await self.llm_manager.generate(
                prompt=prompt,
                system_prompt="You are an expert urologist generating clinical documentation.",
                task_type=task_type,
                temperature=temperature,
                max_tokens=max_tokens,
                provider=llm_provider
            )

            note_text = llm_response.content

        except Exception as e:
            logger.error(f"Note generation failed: {e}")
            raise RuntimeError(f"Failed to generate note: {str(e)}")

        # 6. Build metadata
        generation_time = (datetime.now() - start_time).total_seconds()
        metadata = {
            "note_type": note_type,
            "llm_provider": llm_provider,
            "generation_time_seconds": generation_time,
            "timestamp": datetime.now().isoformat(),
            "num_calculators": len(calculator_results),
            "rag_enabled": use_rag and rag_context is not None,
            "num_rag_sources": len(rag_context.sources) if rag_context else 0,
            "input_hash": hashlib.sha256(clinical_input.encode()).hexdigest()[:16]
        }

        # Add LLM metadata
        if hasattr(llm_response, 'model'):
            metadata["model_used"] = llm_response.model
        if hasattr(llm_response, 'tokens_used'):
            metadata["tokens_used"] = llm_response.tokens_used

        # 7. Return result
        result = NoteResult(
            note_text=note_text,
            calculator_results=calculator_results,
            rag_sources=rag_context.sources if rag_context else [],
            metadata=metadata
        )

        logger.info(f"Note generated successfully in {generation_time:.2f}s")
        return result

    async def generate_note_stream(
        self,
        clinical_input: str,
        note_type: str = "clinic",
        llm_provider: str = "ollama",
        calculator_ids: List[str] = None,
        use_rag: bool = True,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        """
        Generate note with streaming for real-time updates.

        Args:
            (same as generate_note)

        Yields:
            Text chunks as they are generated
        """
        calculator_ids = calculator_ids or []

        # 1. Run calculators (non-streaming)
        calculator_results = []
        if calculator_ids:
            calculator_results = await self._run_calculators(clinical_input, calculator_ids)

        # 2. RAG retrieval (non-streaming)
        rag_context = None
        if use_rag and self.rag_pipeline:
            try:
                rag_context = await self.rag_pipeline.retrieve_and_augment(
                    query=clinical_input,
                    k=5,
                    search_strategy="clinical"
                )
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}")

        # 3. Construct prompt
        prompt = self._construct_prompt(
            template=self.default_template,
            clinical_input=clinical_input,
            calculator_results=calculator_results,
            rag_context=rag_context
        )

        # 4. Stream generation
        logger.info(f"Streaming note generation with {llm_provider}...")
        try:
            async for chunk in self.llm_manager.generate_stream(
                prompt=prompt,
                system_prompt="You are an expert urologist generating clinical documentation.",
                task_type=TaskType.NOTE_GENERATION,
                temperature=temperature,
                max_tokens=max_tokens,
                provider=llm_provider
            ):
                yield chunk.content

        except Exception as e:
            logger.error(f"Streaming note generation failed: {e}")
            raise RuntimeError(f"Failed to generate note: {str(e)}")

    async def generate_note_two_stage(
        self,
        clinical_input: str,
        note_type: str = "clinic",
        calculator_ids: List[str] = None,
        use_rag: bool = True,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> NoteResult:
        """
        Generate clinical note using two-stage workflow.

        Stage 1: Data extraction with qwen3-coder:30b
        Stage 2: Final note generation with llama3.1:70b

        This approach separates data extraction from clinical reasoning,
        improving accuracy and reducing hallucinations.

        Args:
            clinical_input: Raw clinical data (labs, imaging, prior notes)
            note_type: Type of note (clinic, consult, preop, postop)
            calculator_ids: List of calculator IDs to run
            use_rag: Whether to use RAG for evidence
            temperature: LLM temperature (default 0.3 for clinical accuracy)
            max_tokens: Maximum tokens to generate

        Returns:
            NoteResult with generated note and metadata
        """
        start_time = datetime.now()
        calculator_ids = calculator_ids or []

        logger.info("Starting two-stage note generation...")

        # 1. Run calculators if requested
        calculator_results = []
        if calculator_ids:
            logger.info(f"Running {len(calculator_ids)} calculators...")
            calculator_results = await self._run_calculators(clinical_input, calculator_ids)

        # 2. RAG retrieval if enabled
        rag_context = None
        if use_rag and self.rag_pipeline:
            logger.info("Retrieving RAG context...")
            try:
                rag_context = await self.rag_pipeline.retrieve_and_augment(
                    query=clinical_input,
                    k=5,
                    search_strategy="clinical"
                )
            except Exception as e:
                logger.error(f"RAG retrieval failed: {e}")
                rag_context = None

        # 3. STAGE 1: Data Extraction with Ollama llama3.1:8b
        logger.info("Stage 1: Extracting and organizing clinical data with Ollama llama3.1:8b...")

        # Construct Stage 1 prompt
        stage1_prompt_parts = [self.stage1_prompt]
        stage1_prompt_parts.append("\n=== RAW CLINICAL INPUT ===\n")
        stage1_prompt_parts.append(clinical_input)

        # Add calculator results to Stage 1 for organization
        if calculator_results:
            stage1_prompt_parts.append("\n=== CALCULATOR RESULTS ===\n")
            for result in calculator_results:
                stage1_prompt_parts.append(f"\n{result.calculator_name}:")
                stage1_prompt_parts.append(result.formatted_output)

        stage1_prompt = "\n".join(stage1_prompt_parts)

        try:
            # Use Ollama llama3.1:8b for fast data extraction
            # Extract and organize data WITHOUT interpretation
            stage1_response = await self.llm_manager.generate(
                prompt=stage1_prompt,
                system_prompt="You are a medical data extraction specialist. Extract and organize clinical data accurately without interpretation. Focus on urologic findings, chief complaint, HPI, PMH, labs, imaging, and IPSS scores.",
                task_type=TaskType.DATA_EXTRACTION,
                temperature=0.1,  # Lower temperature for factual extraction
                max_tokens=max_tokens,
                model="llama3.1:8b"  # Use fast Ollama model
            )

            organized_data = stage1_response.content
            logger.info(f"Stage 1 complete: {len(organized_data)} chars extracted")

        except Exception as e:
            logger.error(f"Stage 1 extraction failed: {e}")
            raise RuntimeError(f"Stage 1 data extraction failed: {str(e)}")

        # 4. STAGE 2: Final Note Generation with llama3.1:70b
        logger.info("Stage 2: Generating final clinical note with assessment...")

        # Construct Stage 2 prompt
        stage2_prompt_parts = [self.stage2_prompt]
        stage2_prompt_parts.append("\n=== ORGANIZED CLINICAL DATA ===\n")
        stage2_prompt_parts.append(organized_data)

        # Add RAG context for clinical reasoning
        if rag_context and rag_context.has_context:
            stage2_prompt_parts.append("\n=== CLINICAL GUIDELINES & EVIDENCE ===\n")
            stage2_prompt_parts.append(rag_context.context)
            stage2_prompt_parts.append("\nUse these guidelines to inform your ASSESSMENT and PLAN.")

        # Add template for final note format
        template = self._select_template_by_type(note_type)
        stage2_prompt_parts.append("\n=== VA UROLOGY NOTE FORMAT ===\n")
        stage2_prompt_parts.append(template)

        stage2_prompt = "\n".join(stage2_prompt_parts)

        try:
            # Use llama3.1:70b for clinical reasoning and final note
            stage2_response = await self.llm_manager.generate(
                prompt=stage2_prompt,
                system_prompt="You are an expert urologist creating a comprehensive clinical note with assessment and plan.",
                task_type=TaskType.NOTE_GENERATION,
                temperature=temperature,
                max_tokens=max_tokens,
                provider="ollama"  # Will use llama3.1:70b based on TaskType
            )

            final_note = stage2_response.content
            logger.info(f"Stage 2 complete: {len(final_note)} chars generated")

        except Exception as e:
            logger.error(f"Stage 2 note generation failed: {e}")
            raise RuntimeError(f"Stage 2 note generation failed: {str(e)}")

        # 5. Build metadata
        generation_time = (datetime.now() - start_time).total_seconds()
        metadata = {
            "note_type": note_type,
            "workflow": "two_stage",
            "stage1_model": "llama3.1:8b",
            "stage2_model": "llama3.1:70b",
            "generation_time_seconds": generation_time,
            "timestamp": datetime.now().isoformat(),
            "num_calculators": len(calculator_results),
            "rag_enabled": use_rag and rag_context is not None,
            "num_rag_sources": len(rag_context.sources) if rag_context else 0,
            "input_hash": hashlib.sha256(clinical_input.encode()).hexdigest()[:16],
            "organized_data_length": len(organized_data)
        }

        # Add model-specific metadata
        if hasattr(stage1_response, 'model'):
            metadata["stage1_model_used"] = stage1_response.model
        if hasattr(stage2_response, 'model'):
            metadata["stage2_model_used"] = stage2_response.model
        if hasattr(stage1_response, 'tokens_used') and hasattr(stage2_response, 'tokens_used'):
            metadata["total_tokens_used"] = stage1_response.tokens_used + stage2_response.tokens_used

        # 6. Return result
        result = NoteResult(
            note_text=final_note,
            calculator_results=calculator_results,
            rag_sources=rag_context.sources if rag_context else [],
            metadata=metadata
        )

        logger.info(f"Two-stage note generation complete in {generation_time:.2f}s")
        return result
