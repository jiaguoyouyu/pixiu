# Pixiu v2.2D Partnership Catalyst Report Generator — IMPLEMENTATION PLAN

## Ordered Steps

1. Inspect current Catalyst Radar skill.
2. Create input template.
3. Create report template.
4. Add generator script.
5. Add verifier script.
6. Run generator on sample/template input.
7. Verify required report sections.
8. Run production verifier regression.
9. Check Git hygiene.
10. Commit only source/docs/templates/scripts, not generated outputs.
11. Snapshot only after all required verification passes.

## Expected Files to Add

- scripts/generate_partnership_catalyst_report.py
- scripts/verify_partnership_catalyst_report.sh
- templates/major_partnership_catalyst_input_template.md
- templates/major_partnership_catalyst_report_template.md
- docs/partnership_catalyst_report_generator.md
- docs/v2_2D_partnership_catalyst_report_generator_spec.md
- docs/v2_2D_partnership_catalyst_report_generator_plan.md

## Generated / Ignored Output

- outputs/partnership_catalyst_reports/*.md

## Verifiers

New:

- ./scripts/verify_partnership_catalyst_report.sh

Regression:

- ./scripts/verify_daily_production_research.sh

## Safety Checks

- No API key leakage.
- No brokerage/order automation.
- No login/scraping automation.
- No unsupported options inference.
- No generated reports tracked by Git.

## Stop Condition

Stop after final PASS report and wait for user instruction before starting v2.2E.
