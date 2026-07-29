"""
Batch Processing Service for Clinical Documents

Processes a folder of clinical documents through Stage 1 → Stage 2 pipeline.
- Files with "CON" as a standalone word in name → urology_consult
- All other files → urology_clinic
- Retries configurable via BATCH_MAX_RETRIES env var (default 3)
- Complete session purge between patients (HIPAA)
- Creates individual .vaucda files and total.vaucda concatenation
"""

import asyncio
import gc
import logging
import re
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from app.config import settings
from app.schemas.notes import BatchFileResult, BatchFileStatus
from app.services.ollama_health import (
    assert_ollama_healthy,
    check_ollama_gpu_health,
    check_ollama_health_for_workload,
    OllamaWedgedError,
)

logger = logging.getLogger(__name__)


def validate_folder_path(folder_path: str) -> Path:
    """
    Validate that a folder path is safe and within allowed directories.

    Raises:
        ValueError: If the path is invalid, unsafe, or not in allowed dirs.
    """
    try:
        resolved = Path(folder_path).resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid folder path: {e}")

    if not resolved.is_dir():
        raise ValueError("Path is not a directory")

    # Check against allowed directories (if configured)
    allowed_dirs = settings.batch_allowed_dirs_list
    if allowed_dirs:
        allowed = False
        for allowed_dir in allowed_dirs:
            try:
                allowed_resolved = Path(allowed_dir).resolve()
                if resolved == allowed_resolved or allowed_resolved in resolved.parents:
                    allowed = True
                    break
            except (OSError, RuntimeError):
                continue

        if not allowed:
            raise ValueError(
                "Folder path is not within any allowed batch processing directory. "
                "Configure BATCH_ALLOWED_DIRS in .env to allow this path."
            )

    return resolved


def detect_note_type(filename: str) -> str:
    """
    Detect note type from filename.

    Uses word-boundary matching to find "CON" as a standalone token,
    avoiding false positives from words like CONDITION, ONCOLOGY, etc.
    """
    upper_name = Path(filename).stem.upper()
    # Match CON as a standalone word (bounded by non-alphanumeric or start/end)
    if re.search(r'(?<![A-Z])CON(?![A-Z])', upper_name):
        return "urology_consult"
    return "urology_clinic"


def get_processable_files(folder_path: str) -> List[Path]:
    """
    Get list of processable text files in folder, sorted numerically/alphabetically.

    Only .txt files are supported for direct batch processing.
    PDF files require OCR and should be uploaded individually via the upload endpoint.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Folder does not exist: {folder_path}")

    # Collect text files only - PDFs require OCR and are not supported in batch mode
    files = []
    for f in folder.iterdir():
        if f.is_file() and f.suffix.lower() == '.txt':
            files.append(f)

    # Sort files: try numeric extraction first, fall back to alphabetical
    def sort_key(filepath: Path) -> Tuple:
        name = filepath.stem
        # Extract leading number if present
        match = re.match(r'^(\d+)', name)
        if match:
            return (0, int(match.group(1)), name)
        return (1, 0, name)

    files.sort(key=sort_key)
    return files


async def process_single_file(
    file_path: Path,
    note_type: str,
    stage1_func: Callable,
    stage2_func: Callable,
    visit_date: Optional[str] = None,
) -> str:
    """
    Process a single clinical document through Stage 1 → Stage 2.

    Args:
        file_path: Path to the input file
        note_type: 'urology_clinic' or 'urology_consult'
        stage1_func: Async function for Stage 1 processing
        stage2_func: Async function for Stage 2 processing
        visit_date: Optional visit date (MM/DD/YYYY) for IPSS and age calculation

    Returns:
        Final note text (Stage 2 output)
    """
    try:
        content = file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        content = file_path.read_text(encoding='utf-8', errors='replace')
        logger.warning(f"File {file_path.name} contains non-UTF-8 characters (replaced)")

    if not content.strip():
        raise ValueError(f"File is empty: {file_path.name}")

    # Prepend visit date so extractors (IPSS, age calculation) can use it
    if visit_date:
        content = f"VISIT DATE: {visit_date}\n\n{content}"

    logger.info(f"Processing file: {file_path.name} ({len(content)} chars, type: {note_type})")

    # Stage 1: Generate preliminary note
    preliminary_note = await stage1_func(
        clinical_input=content,
        note_type=note_type,
    )

    if not preliminary_note or not preliminary_note.strip():
        raise ValueError("Stage 1 returned empty preliminary note")

    logger.info(f"Stage 1 complete for {file_path.name}: {len(preliminary_note)} chars")

    # Stage 2: Generate final note with Assessment & Plan
    final_note = await stage2_func(
        preliminary_note=preliminary_note,
        clinical_input=content,
        note_type=note_type,
    )

    if not final_note or not final_note.strip():
        raise ValueError("Stage 2 returned empty final note")

    logger.info(f"Stage 2 complete for {file_path.name}: {len(final_note)} chars")

    return final_note


async def run_batch_processing(
    folder_path: str,
    stage1_func: Callable,
    stage2_func: Callable,
    purge_func: Callable,
    visit_date: Optional[str] = None,
    active_model: Optional[str] = None,
) -> Tuple[List[BatchFileResult], str, float]:
    """
    Process all files in a folder through Stage 1 → Stage 2.

    Args:
        folder_path: Path to folder containing clinical documents
        stage1_func: Async callable for Stage 1
        stage2_func: Async callable for Stage 2
        purge_func: Callable to purge all patient data between files
        visit_date: Optional visit date (MM/DD/YYYY) for IPSS and age calculation
        active_model: The Ollama model name this batch will call (typically
            the user's stage2_llm_model). Used by the pre-flight health
            check to relax the local-VRAM guard when the workload is
            cloud-proxied (``*-cloud``) and the cloud route is verified
            responsive — so a separate process's local-model wedge can't
            block a vaucda batch whose synthesis is entirely cloud-routed.
            When None, the strict local-VRAM check is used.

    Returns:
        Tuple of (results list, path to total.vaucda, total time in seconds)
    """
    start_time = time.time()
    max_retries = settings.BATCH_MAX_RETRIES
    file_timeout = settings.BATCH_FILE_TIMEOUT
    max_files = settings.BATCH_MAX_FILES
    separator = settings.BATCH_FILE_SEPARATOR

    # Get processable files
    files = get_processable_files(folder_path)
    if not files:
        raise ValueError(f"No processable .txt files found in: {folder_path}")

    if len(files) > max_files:
        raise ValueError(
            f"Folder contains {len(files)} files, exceeding the maximum of {max_files}. "
            "Adjust BATCH_MAX_FILES in .env if needed."
        )

    logger.info(f"Batch processing: {len(files)} files found in {folder_path}")

    # Pre-flight: refuse to start the batch when Ollama / GPU is already
    # wedged. The most common failure mode we've seen is another process
    # on the shared GPU (e.g. UT-MS1-SIM, Grant-Assist) loading a model
    # with its full 131K context, which exceeds VRAM and wedges the
    # runner so subsequent Ollama LOCAL requests block indefinitely.
    # Cloud-proxied requests usually still flow through unaffected, so
    # when active_model is a cloud model we use the workload-aware
    # variant which probes the cloud route and lets the batch proceed
    # if the cloud is responsive — local-VRAM wedge be damned.
    pre_health = check_ollama_health_for_workload(active_model=active_model)
    if not pre_health.healthy:
        raise RuntimeError(
            f"Refusing to start batch: Ollama is not healthy. "
            f"{pre_health.reason}"
        )
    logger.info(
        "Ollama health check passed (loaded VRAM: %d MB / %s MB GPU; "
        "active_model=%r; note: %s)",
        pre_health.loaded_vram_mb,
        pre_health.total_vram_mb if pre_health.total_vram_mb is not None else "?",
        active_model,
        pre_health.reason or "no warnings",
    )

    results: List[BatchFileResult] = []
    output_folder = Path(folder_path)

    for idx, file_path in enumerate(files):
        note_type = detect_note_type(file_path.name)
        output_filename = file_path.stem + ".vaucda"
        output_path = output_folder / output_filename

        result = BatchFileResult(
            filename=file_path.name,
            output_filename=output_filename,
            note_type=note_type,
            status=BatchFileStatus.PROCESSING,
            attempts=0,
        )

        # Pre-flight per file: a wedge can happen MID-BATCH if another
        # process loads an oversized model between files. Check before
        # each file so we fail this file fast with an actionable error
        # rather than burning 20-min × max_retries on a wedged Ollama.
        # Same workload-aware relaxation as the batch-start check.
        per_file_health = check_ollama_health_for_workload(active_model=active_model)
        if not per_file_health.healthy:
            result.status = BatchFileStatus.FAILED
            result.error_message = (
                f"Skipped: Ollama wedged before this file could be processed. "
                f"{per_file_health.reason}"
            )
            logger.error(
                "[%d/%d] %s SKIPPED — Ollama unhealthy: %s",
                idx + 1, len(files), file_path.name, per_file_health.reason,
            )
            results.append(result)
            continue

        # Retry loop
        success = False
        for attempt in range(1, max_retries + 1):
            result.attempts = attempt

            try:
                # CRITICAL: Purge ALL patient data before processing each file
                purge_func()
                gc.collect()

                logger.info(
                    f"[{idx + 1}/{len(files)}] Processing {file_path.name} "
                    f"(attempt {attempt}/{max_retries}, type: {note_type})"
                )

                file_start = time.time()

                # Process with timeout to prevent indefinite blocking
                final_note = await asyncio.wait_for(
                    process_single_file(
                        file_path=file_path,
                        note_type=note_type,
                        stage1_func=stage1_func,
                        stage2_func=stage2_func,
                        visit_date=visit_date,
                    ),
                    timeout=file_timeout,
                )

                # Write output file
                output_path.write_text(final_note, encoding='utf-8')

                result.status = BatchFileStatus.COMPLETED
                result.generation_time_seconds = round(time.time() - file_start, 2)
                result.error_message = None
                success = True

                logger.info(
                    f"[{idx + 1}/{len(files)}] {file_path.name} -> {output_filename} "
                    f"({result.generation_time_seconds}s)"
                )

                break  # Success, no more retries

            except asyncio.TimeoutError:
                error_msg = f"File processing timed out after {file_timeout}s"
                logger.error(
                    f"[{idx + 1}/{len(files)}] {file_path.name} attempt {attempt}: {error_msg}"
                )
                result.error_message = error_msg
                purge_func()
                # Fail-fast on timeout: retrying a stuck/oversized note just burns
                # another full timeout window (30 min across 3 attempts). Mark it
                # failed and move on so the batch is never frozen by one bad note.
                break

            except Exception as e:
                error_msg = f"Processing error: {type(e).__name__}"
                logger.error(
                    f"[{idx + 1}/{len(files)}] {file_path.name} attempt {attempt} failed: {e}"
                )
                # Sanitize error message - don't leak PHI
                result.error_message = error_msg
                purge_func()

            if attempt < max_retries:
                logger.info(f"Retrying {file_path.name} (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(1)

        if not success:
            result.status = BatchFileStatus.FAILED
            logger.error(
                f"[{idx + 1}/{len(files)}] {file_path.name} FAILED after {max_retries} attempts"
            )

        # CRITICAL: Final purge after each file to ensure zero cross-contamination
        purge_func()
        gc.collect()

        results.append(result)

    # Create total.vaucda concatenation file
    total_path = output_folder / "total.vaucda"
    _create_total_file(results, output_folder, total_path, separator)

    total_time = round(time.time() - start_time, 2)

    processed = sum(1 for r in results if r.status == BatchFileStatus.COMPLETED)
    failed = sum(1 for r in results if r.status == BatchFileStatus.FAILED)

    logger.info(
        f"Batch processing complete: {processed}/{len(files)} succeeded, "
        f"{failed} failed, {total_time}s total"
    )

    return results, str(total_path), total_time


def _create_total_file(
    results: List[BatchFileResult],
    output_folder: Path,
    total_path: Path,
    separator: str,
) -> None:
    """Create total.vaucda by concatenating all successful outputs in order."""
    parts = []

    for result in results:
        if result.status != BatchFileStatus.COMPLETED:
            continue

        output_path = output_folder / result.output_filename
        if output_path.exists():
            content = output_path.read_text(encoding='utf-8')
            parts.append(content)

    if parts:
        total_content = f"\n{separator}\n".join(parts)
        total_path.write_text(total_content, encoding='utf-8')
        logger.info(f"Created total.vaucda: {len(parts)} notes, {len(total_content)} chars")
    else:
        total_path.write_text("No notes were successfully generated.", encoding='utf-8')
        logger.warning("total.vaucda is empty - no files were successfully processed")
