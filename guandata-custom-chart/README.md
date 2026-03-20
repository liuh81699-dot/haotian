# GuanData Custom Chart Skill

This directory contains the isolated GuanData custom-chart skill package.

## Contents

- `SKILL.md`: skill definition and usage rules
- `references/api-rules.md`: summarized API constraints and implementation notes
- `scripts/chart_template.py`: starter generator for standard and Lite chart modes
- `agents/openai.yaml`: skill agent metadata

## Usage

Open the skill definition:

```bash
cd /Users/guandata/Desktop/cursor_project/page_compare/guandata-custom-chart
cat SKILL.md
```

Generate a chart starter:

```bash
python3 scripts/chart_template.py --mode lite
python3 scripts/chart_template.py --mode standard
```
