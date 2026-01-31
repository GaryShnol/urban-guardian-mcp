#!/bin/bash
# Quick demo of all enhanced features

echo "╔════════════════════════════════════════════════════════════╗"
echo "║      Urban Guardian - Enhanced Features Demo               ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

echo "🚀 Generating comprehensive report..."
echo ""

uv run python3 -c "
from server import _generate_guardian_report_impl
report = _generate_guardian_report_impl(
    31.7852558, 34.6468311,
    address='העצמאות 10, אשדוד',
    language='he',
    comprehensive=True
)
print(report['comprehensive_report'])
"

echo ""
echo "╚════════════════════════════════════════════════════════════╝"
echo "Demo complete! ✅"
