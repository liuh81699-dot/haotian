---
name: guandata-custom-chart
description: Generate, adapt, and debug GuanData BI custom chart code that must follow the documented renderChart, data, clickFunc, config, and Lite-mode rules. Use when Codex needs to build or modify JavaScript, HTML, or CSS for GuanData dashboard cards; map BI data views into ECharts, Highcharts, or AntV inputs; wire clickFunc linkage payloads; use theme, colors, customOptions, language, or utils correctly; or decide whether a request should use standard custom chart mode or custom chart Lite.
---

# Guandata Custom Chart

## Overview

Use this skill to turn chart requirements into GuanData-compatible custom chart code. Prefer Lite when the request can be solved by returning an ECharts `option`; use standard mode when the chart needs HTML/CSS, third-party libraries, or explicit chart-instance lifecycle control.

## Decide The Mode

- Use Lite when the request is ECharts-only, the user can work inside GuanData's Lite editor, and no custom HTML/CSS container setup is needed.
- Prefer Lite over standard mode for ordinary ECharts bar/line/pie/combo charts. Lite avoids the standard card lifecycle issues around DOM replacement, chart recreation, and library loading.
- Use standard mode when the request needs Highcharts, AntV, multiple CDN imports, custom DOM structure, custom CSS, or refresh logic via `utils.refreshData()`.
- Switch to standard mode when the user needs full control over chart creation and update timing.

## Build The Chart

1. Read [references/api-rules.md](references/api-rules.md) before writing code.
2. Identify the minimum data contract from the request:
   - Which view index is used.
   - Which dimension fields supply labels or categories.
   - Which metric fields supply numeric values.
   - Whether linkage should point back to a dimension field or another source column.
3. Guard for missing fields or empty data before rendering. Render an explicit empty state instead of letting the chart library fail.
4. Map GuanData's `data[viewIndex][fieldIndex]` structure into the target library's series data.
5. Apply `config.theme`, `config.colors`, `config.customOptions`, and `config.language` instead of hard-coding them unless the request explicitly asks otherwise.
6. Add linkage only when the request needs dashboard interaction. Build `clickFunc` payloads from source-field paths, not from chart-library internals.
7. Reuse chart instances where possible. Avoid repeated event binding without first removing prior listeners.
8. In standard mode, assume the card may rerender with a replaced container node or a delayed chart-library load. Write code that tolerates both.

## Standard Mode Rules

- Keep custom JavaScript inside the `renderChart` body or the documented custom-code markers when editing an existing snippet.
- Preserve `new GDPlugin().init(renderChart)`.
- Use the full signature `renderChart(data, clickFunc, config, utils)` on recent versions. Older examples may omit `utils`, but do not drop it if the environment provides it.
- Prefer resolving the chart container inside `renderChart` or validating that any cached DOM node still matches the live container before reusing it.
- Do not clear or replace the main container with `innerHTML = ''` once a chart instance may already be bound to it. Prefer `chart.clear()` plus an ECharts empty-state option.
- When standard mode uses ECharts, do not assume `window.echarts` already exists. Reuse it when present; otherwise load it explicitly and gate rendering on the load promise.
- Prefer `echarts.getInstanceByDom(container)` and recreate the instance only when the container node actually changed.
- Use `ResizeObserver` on the chart container when available. Do not rely on `window.resize` alone because GuanData card dragging may not trigger it.
- Restrict styling to native CSS. Do not emit SCSS or LESS.
- Load external chart libraries through HTML CDN imports only when standard mode is used.
- Use `utils.refreshData()` only when the request explicitly needs a data refresh action and the runtime exposes it.

## Lite Mode Rules

- Return only the JavaScript body that produces `option = { ... }`.
- Do not redefine `data`, `config`, `clickFunc`, `utils`, or `window`.
- Lite mode may include lightweight preprocessing and `utils.getChartInstance()` event binding around the final `option = { ... }`. It is not limited to a bare object literal.
- Use `utils.getChartInstance()` to bind click handlers after `option` is prepared.
- Call `chartInstance.off('click')` before `chartInstance.on('click', ...)` to avoid duplicated listeners after reruns.
- Use `utils.numberFormat({ value, format })` when the request needs the same numeric formatting as the BI field settings.
- Respect the trimmed browser environment. Do not rely on `localStorage`, `indexedDB`, or similar restricted globals.

## Linkage Contract

- Emit linkage payloads in this shape:
```js
clickFunc({
  clickedItems: [
    {
      idx: [0, 0],
      colName: data[0][0].name,
      value: [params.name],
    },
  ],
})
```
- Treat `idx` as the source column path inside GuanData's data structure, not as the rendered series index unless they happen to match.
- Always use `colName`. The Lite section of the official page shows `name` in one example, but the typed contract and standard-mode examples both use `colName`; treat the Lite example as a documentation typo.
- Keep `value` as an array, even for a single selected value.

## Reusable Resources

- Read [references/api-rules.md](references/api-rules.md) for the summarized API contract, caveats, and implementation checklist.
- Run `scripts/chart_template.py --mode standard` to generate a standard custom-chart starter.
- Run `scripts/chart_template.py --mode lite` to generate a Lite starter that already follows the documented event and formatting rules.

## Default Output Shape

- For standard mode, return separate `HTML`, `CSS`, and `JavaScript` blocks when the user asks for a complete card implementation.
- For Lite mode, return only the code that belongs inside the Lite editor unless the user explicitly asks for explanation.
- When the request is ambiguous, state which mode you chose and why in one sentence, then produce code.
