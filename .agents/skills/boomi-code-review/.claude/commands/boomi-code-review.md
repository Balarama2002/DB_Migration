---
description: Perform automated and architectural Boomi code review on component XMLs
---

Conduct a comprehensive Boomi code review on the specified target:

1. Run the static analysis linter:
   `python scripts/boomi_code_review.py $ARGUMENTS --format markdown`

2. Evaluate the components against `references/checklist.md` focusing on:
   - Database service accounts (`SRV_` prefix required)
   - Try/Catch coverage on outbound connectors
   - Credential externalization (no hardcoded tokens/passwords)
   - Connection duplication and mixed connector types
   - Batch isolation vs premature halt risks
   - Diagnostic metadata in error alerts

3. Format the final output matching `references/report_template.md`.
