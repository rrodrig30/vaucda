"""
Adaptive GPU Configuration for LLM Inference

Automatically detects GPU capabilities and selects optimal processing strategy:
- H100 96GB: Large batch processing (all sections at once)
- Multi-GPU (4x RTX): Distributed processing across GPUs
- Single GPU (24GB): Medium batch processing
- CPU/Limited: Sequential processing fallback

This ensures code works seamlessly from dev (4x RTX) to production (H100).
"""

import torch
import logging
from typing import Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ProcessingStrategy(Enum):
    """GPU processing strategies based on hardware capabilities."""
    LARGE_BATCH = "large_batch"  # H100: Process all 27 sections at once
    MULTI_GPU = "multi_gpu"       # 4x RTX: Distribute across GPUs
    MEDIUM_BATCH = "medium_batch" # Single GPU: Process 4-8 sections per batch
    SEQUENTIAL = "sequential"      # CPU/Limited: One section at a time


@dataclass
class GPUConfig:
    """GPU configuration and optimal processing parameters."""

    num_gpus: int
    gpu_memory_gb: float
    strategy: ProcessingStrategy
    batch_size: int
    num_model_instances: int
    device_ids: list

    @property
    def description(self):
        """Human-readable description of configuration."""
        if self.strategy == ProcessingStrategy.LARGE_BATCH:
            return f"H100-class GPU ({self.gpu_memory_gb:.0f}GB) - Large batch processing"
        elif self.strategy == ProcessingStrategy.MULTI_GPU:
            return f"{self.num_gpus}x GPUs - Multi-GPU distribution"
        elif self.strategy == ProcessingStrategy.MEDIUM_BATCH:
            return f"Single GPU ({self.gpu_memory_gb:.0f}GB) - Medium batch processing"
        else:
            return "CPU/Limited - Sequential processing"


def detect_gpu_config() -> GPUConfig:
    """
    Detect GPU hardware and determine optimal processing configuration.

    Returns:
        GPUConfig with optimal strategy and parameters

    Strategy Selection:
    - GPU >= 80GB VRAM: LARGE_BATCH (H100/A100 80GB)
    - 4+ GPUs: MULTI_GPU (distributed processing)
    - 1 GPU with 20-40GB: MEDIUM_BATCH (RTX 3090/4090/A100 40GB)
    - CPU or limited GPU: SEQUENTIAL
    """

    # Check if CUDA is available
    if not torch.cuda.is_available():
        logger.warning("No CUDA GPUs detected. Using CPU sequential processing.")
        return GPUConfig(
            num_gpus=0,
            gpu_memory_gb=0.0,
            strategy=ProcessingStrategy.SEQUENTIAL,
            batch_size=1,
            num_model_instances=1,
            device_ids=["cpu"]
        )

    # Get GPU information
    num_gpus = torch.cuda.device_count()

    # Get primary GPU memory (GB)
    gpu_memory_bytes = torch.cuda.get_device_properties(0).total_memory
    gpu_memory_gb = gpu_memory_bytes / (1024 ** 3)

    logger.info(f"Detected {num_gpus} GPU(s), Primary GPU: {gpu_memory_gb:.1f}GB VRAM")

    # Strategy 1: H100-class (80GB+) - Large batch processing
    if gpu_memory_gb >= 80:
        logger.info("H100/A100-class GPU detected - Using LARGE_BATCH strategy")
        return GPUConfig(
            num_gpus=num_gpus,
            gpu_memory_gb=gpu_memory_gb,
            strategy=ProcessingStrategy.LARGE_BATCH,
            batch_size=27,  # Process all sections at once
            num_model_instances=4,  # Load 4 instances for concurrent users
            device_ids=[0]
        )

    # Strategy 2: Multi-GPU (4+ GPUs) - Distributed processing
    elif num_gpus >= 4:
        logger.info(f"Multi-GPU system detected ({num_gpus} GPUs) - Using MULTI_GPU strategy")
        return GPUConfig(
            num_gpus=num_gpus,
            gpu_memory_gb=gpu_memory_gb,
            strategy=ProcessingStrategy.MULTI_GPU,
            batch_size=8,  # 8 sections per GPU
            num_model_instances=num_gpus,  # One model per GPU
            device_ids=list(range(num_gpus))
        )

    # Strategy 3: Single GPU (20-40GB) - Medium batch processing
    elif num_gpus == 1 and gpu_memory_gb >= 20:
        logger.info(f"Single GPU ({gpu_memory_gb:.0f}GB) - Using MEDIUM_BATCH strategy")

        # Calculate optimal batch size based on available VRAM
        # LLM processing uses ~9GB, leave headroom for batch processing
        if gpu_memory_gb >= 40:
            batch_size = 8  # A100 40GB
        elif gpu_memory_gb >= 24:
            batch_size = 6  # RTX 3090/4090
        else:
            batch_size = 4  # RTX 3080

        return GPUConfig(
            num_gpus=1,
            gpu_memory_gb=gpu_memory_gb,
            strategy=ProcessingStrategy.MEDIUM_BATCH,
            batch_size=batch_size,
            num_model_instances=1,
            device_ids=[0]
        )

    # Strategy 4: Limited GPU or CPU - Sequential processing
    else:
        logger.warning(f"Limited GPU resources ({gpu_memory_gb:.0f}GB) - Using SEQUENTIAL strategy")
        return GPUConfig(
            num_gpus=num_gpus,
            gpu_memory_gb=gpu_memory_gb,
            strategy=ProcessingStrategy.SEQUENTIAL,
            batch_size=1,
            num_model_instances=1,
            device_ids=[0] if num_gpus > 0 else ["cpu"]
        )


def get_optimal_batch_size(num_sections: int, config: GPUConfig) -> int:
    """
    Calculate optimal batch size for given number of sections.

    Args:
        num_sections: Total number of sections to process
        config: GPU configuration

    Returns:
        Optimal batch size (capped at num_sections)
    """
    if config.strategy == ProcessingStrategy.SEQUENTIAL:
        return 1

    # Don't batch more sections than we have
    return min(config.batch_size, num_sections)


def estimate_processing_time(
    num_sections: int,
    config: GPUConfig,
    seconds_per_section: float = 60.0
) -> Tuple[float, str]:
    """
    Estimate processing time based on hardware configuration.

    Args:
        num_sections: Number of sections to process
        config: GPU configuration
        seconds_per_section: Time per section in sequential mode

    Returns:
        Tuple of (estimated_seconds, human_readable_time)
    """
    if config.strategy == ProcessingStrategy.LARGE_BATCH:
        # H100: All sections in single batch, ~3-4x faster than RTX
        estimated_seconds = (num_sections * seconds_per_section) / (config.batch_size * 3.5)

    elif config.strategy == ProcessingStrategy.MULTI_GPU:
        # Multi-GPU: Parallel processing across GPUs
        sections_per_gpu = num_sections / config.num_gpus
        batches_per_gpu = sections_per_gpu / config.batch_size
        estimated_seconds = batches_per_gpu * (seconds_per_section / 2)  # Batching ~2x faster

    elif config.strategy == ProcessingStrategy.MEDIUM_BATCH:
        # Single GPU batching: ~5-8x speedup from batching
        num_batches = (num_sections + config.batch_size - 1) // config.batch_size
        estimated_seconds = num_batches * (seconds_per_section / 6)  # Batching ~6x faster

    else:
        # Sequential: No speedup
        estimated_seconds = num_sections * seconds_per_section

    # Convert to human-readable format
    if estimated_seconds < 60:
        time_str = f"{estimated_seconds:.0f} seconds"
    elif estimated_seconds < 3600:
        time_str = f"{estimated_seconds / 60:.1f} minutes"
    else:
        time_str = f"{estimated_seconds / 3600:.1f} hours"

    return estimated_seconds, time_str


def log_gpu_configuration(config: GPUConfig):
    """Log GPU configuration details."""
    logger.info("=" * 80)
    logger.info("GPU CONFIGURATION")
    logger.info("=" * 80)
    logger.info(f"Strategy: {config.strategy.value}")
    logger.info(f"Description: {config.description}")
    logger.info(f"GPUs: {config.num_gpus}")
    logger.info(f"VRAM: {config.gpu_memory_gb:.1f}GB")
    logger.info(f"Batch Size: {config.batch_size}")
    logger.info(f"Model Instances: {config.num_model_instances}")
    logger.info(f"Device IDs: {config.device_ids}")
    logger.info("=" * 80)


# Global configuration (EAGER initialization to detect GPUs BEFORE model loading)
# This is critical: accelerate library restricts GPU visibility after model loading
# We MUST detect all GPUs before any HuggingFace models are loaded
_GLOBAL_GPU_CONFIG: Optional[GPUConfig] = None


def get_gpu_config() -> GPUConfig:
    """
    Get or initialize global GPU configuration.

    CRITICAL: This MUST be called BEFORE loading any HuggingFace models,
    as the accelerate library will restrict GPU visibility after model loading.

    Returns:
        GPUConfig instance
    """
    global _GLOBAL_GPU_CONFIG

    if _GLOBAL_GPU_CONFIG is None:
        _GLOBAL_GPU_CONFIG = detect_gpu_config()
        log_gpu_configuration(_GLOBAL_GPU_CONFIG)

    return _GLOBAL_GPU_CONFIG


# CRITICAL FIX: Detect GPUs immediately on module import
# This ensures GPU detection happens BEFORE any model loading
# which would restrict visibility via accelerate library
_GLOBAL_GPU_CONFIG = detect_gpu_config()
log_gpu_configuration(_GLOBAL_GPU_CONFIG)
