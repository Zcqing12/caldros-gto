#!/bin/bash
echo "🤖 Running LLM Auto-Build..."

python tools/llm_codegen.py --config production.json --output ./caldros_gto

echo "✅ Auto-build completed. Generated modules:"
ls -R caldros_gto/
