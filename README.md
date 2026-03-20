# Workspace Overview

This repository contains two isolated projects at the top level.

## Projects

### `bi-page-compare/`

BI dual-environment page and card comparison tool.

- Web UI for manual runs, template management, history, and scheduling
- Python CLI for config-based comparisons
- Deployment scripts for port-only and reverse-proxy modes

Entry points:

- `/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare/README.md`
- `/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare/web_app.py`
- `/Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare/main.py`

### `guandata-custom-chart/`

GuanData custom-chart skill package and references.

- Skill definition and usage rules
- API notes and reusable chart template generator

Entry points:

- `/Users/guandata/Desktop/cursor_project/page_compare/guandata-custom-chart/README.md`
- `/Users/guandata/Desktop/cursor_project/page_compare/guandata-custom-chart/SKILL.md`

## Quick Start

Run the BI page compare service:

```bash
cd /Users/guandata/Desktop/cursor_project/page_compare/bi-page-compare
python3 web_app.py --host 127.0.0.1 --port 8787
```

Open the custom-chart skill package:

```bash
cd /Users/guandata/Desktop/cursor_project/page_compare/guandata-custom-chart
```
