#!/usr/bin/env python3
"""
Test script to verify merged model GPU performance (without PEFT adapters).
"""

import os
import sys
import time
import torch
import logging
from pathlib import Path
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
MERGED_MODEL_PATH = "/home/gulab/PythonProjects/VAUCDA/fine_tuning/outputs_peft/merged_model"
DEVICE = "cuda:4"
LOAD_IN_4BIT = True
TORCH_DTYPE = torch.bfloat16

def check_gpu_memory():
    """Check and log GPU memory status."""
    if torch.cuda.is_available():
        gpu_id = int(DEVICE.split(":")[-1])
        allocated = torch.cuda.memory_allocated(gpu_id) / 1024**3
        reserved = torch.cuda.memory_reserved(gpu_id) / 1024**3
        logger.info(f"GPU {gpu_id} - Allocated: {allocated:.2f}GB, Reserved: {reserved:.2f}GB")
    else:
        logger.warning("CUDA not available!")

def load_model():
    """Load merged model directly."""
    logger.info("=" * 80)
    logger.info("Merged Model GPU Test (No PEFT Adapters)")
    logger.info("=" * 80)
    logger.info(f"Model Path: {MERGED_MODEL_PATH}")
    logger.info(f"Target Device: {DEVICE}")
    logger.info(f"4-bit Quantization: {LOAD_IN_4BIT}")
    logger.info("=" * 80)

    # Check GPU before loading
    logger.info("\n[1/4] GPU Status Before Loading:")
    check_gpu_memory()

    # Load tokenizer
    logger.info("\n[2/4] Loading Tokenizer...")
    start_time = time.time()
    tokenizer = AutoTokenizer.from_pretrained(
        MERGED_MODEL_PATH,
        trust_remote_code=True,
        use_fast=True
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
        tokenizer.pad_token_id = tokenizer.eos_token_id
    logger.info(f"✓ Tokenizer loaded in {time.time() - start_time:.2f}s")

    # Load model
    logger.info("\n[3/4] Loading Merged Model...")
    start_time = time.time()

    if LOAD_IN_4BIT:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_use_double_quant=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=TORCH_DTYPE
        )

        model = AutoModelForCausalLM.from_pretrained(
            MERGED_MODEL_PATH,
            quantization_config=bnb_config,
            device_map=DEVICE,
            trust_remote_code=True,
            torch_dtype=TORCH_DTYPE,
            low_cpu_mem_usage=True
        )
    else:
        model = AutoModelForCausalLM.from_pretrained(
            MERGED_MODEL_PATH,
            device_map=DEVICE,
            trust_remote_code=True,
            torch_dtype=TORCH_DTYPE,
            low_cpu_mem_usage=True
        )

    model.eval()
    logger.info(f"✓ Model loaded in {time.time() - start_time:.2f}s")
    logger.info(f"Model device: {model.device}")
    check_gpu_memory()

    return model, tokenizer

def test_inference(model, tokenizer):
    """Test inference speed."""
    logger.info("\n[4/4] Testing Inference Speed...")

    # Format test prompt
    test_prompt = """<|begin_of_text|><|start_header_id|>system<|end_header_id|>

You are a medical data extraction specialist. Extract key clinical information from the following patient data.<|eot_id|><|start_header_id|>user<|end_header_id|>

Patient: 65M with urinary frequency and nocturia x 3 months. IPSS score 18. PSA 2.4. DRE: enlarged prostate.<|eot_id|><|start_header_id|>assistant<|end_header_id|>

"""

    # Tokenize
    logger.info("Tokenizing input...")
    inputs = tokenizer(test_prompt, return_tensors="pt", truncation=True, max_length=4096)

    # Move to device
    if model.device.type == "cuda":
        inputs = {k: v.to(model.device) for k, v in inputs.items()}
        logger.info(f"✓ Inputs moved to {model.device}")
    else:
        logger.warning(f"⚠ Model is on {model.device}, not CUDA!")

    # Generate
    logger.info("Running inference...")
    start_time = time.time()

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=256,
            temperature=0.1,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id
        )

    inference_time = time.time() - start_time

    # Decode
    generated_text = tokenizer.decode(
        outputs[0][inputs['input_ids'].shape[1]:],
        skip_special_tokens=True
    )

    logger.info("=" * 80)
    logger.info("INFERENCE RESULTS")
    logger.info("=" * 80)
    logger.info(f"Inference Time: {inference_time:.2f}s")
    logger.info(f"Tokens Generated: {outputs.shape[1] - inputs['input_ids'].shape[1]}")
    logger.info(f"Tokens/Second: {(outputs.shape[1] - inputs['input_ids'].shape[1]) / inference_time:.2f}")
    logger.info("=" * 80)
    logger.info("Generated Text:")
    logger.info("-" * 80)
    logger.info(generated_text[:500] + "..." if len(generated_text) > 500 else generated_text)
    logger.info("=" * 80)

    check_gpu_memory()

    return inference_time

def main():
    """Main test function."""
    try:
        # Load model
        model, tokenizer = load_model()

        # Test inference
        inference_time = test_inference(model, tokenizer)

        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY - MERGED MODEL (No PEFT)")
        logger.info("=" * 80)
        if inference_time < 10:
            logger.info(f"✓ EXCELLENT: Inference time {inference_time:.2f}s is fast")
        elif inference_time < 30:
            logger.info(f"✓ GOOD: Inference time {inference_time:.2f}s is acceptable")
        elif inference_time < 60:
            logger.info(f"⚠ SLOW: Inference time {inference_time:.2f}s is slow but usable")
        else:
            logger.error(f"✗ FAIL: Inference time {inference_time:.2f}s is too slow")

        if model.device.type == "cuda":
            logger.info(f"✓ Model is on GPU: {model.device}")
        else:
            logger.error(f"✗ Model is on CPU: {model.device}")

        logger.info("=" * 80)

    except Exception as e:
        logger.error(f"Test failed: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
