#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Debug Paper validation
"""
import sys
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

from src.core.database_model import Paper
from src.core.config_loader import get_config_instance

config = get_config_instance()
cats = [c['unique_name'] for c in config.get_active_categories()][:3]

paper = Paper(
    doi="10.1234/test1234",
    title="Test Paper",
    authors="Test Author",
    date="2024-01-21",
    category=f"{cats[0]};{cats[1]}",
    paper_url="https://example.com",
    summary_motivation="M",
    summary_innovation="I", 
    summary_method="M",
    summary_conclusion="C"
)

print(f"Paper category before validation: {paper.category}\n")

valid, errors , _= paper.validate_paper_fields(config, check_required=True, check_non_empty=True)

print(f"Validation result: {valid}")
print(f"Paper category after validation: {paper.category}")
print(f"All errors ({len(errors)}):")
for i, err in enumerate(errors, 1):
    print(f"  {i}. {err}")
