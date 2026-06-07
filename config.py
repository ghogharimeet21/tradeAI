# config.py — Model configuration
# Change models here without touching any other file

# Main agent — reasoning, planning, market analysis
MAIN_MODEL = "llama3.2:3b"

# Coding agent — writes new tool functions on demand
# qwen2.5-coder is purpose-built for code generation
CODER_MODEL = "qwen2.5-coder:7b"