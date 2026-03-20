# GuanData Custom Chart API Rules

## Source

- Official doc: https://docs.guandata.com/product/bi/428610763133812736
- Official code repo mentioned by the doc: https://github.com/GuandataOSS/visualization-tool
- Page update time shown by the doc: 2026-02-27 15:30:08

## Mode Selection

- Use standard custom chart mode when the solution needs HTML, CSS, third-party libraries, or full chart lifecycle control.
- Use custom chart Lite when the solution can be expressed as an ECharts `option` plus optional event binding through `utils.getChartInstance()`.
- Prefer Lite for ordinary ECharts charts unless the request explicitly needs standard-mode capabilities. Lite avoids the standard card lifecycle issues around library loading and container replacement.

## Standard Custom Chart Contract

### Runtime shape

```js
function renderChart(data, clickFunc, config, utils) {
  /* ------ Custom Code Start ------ */
  /* your code */
  /* ------ Custom Code End ------ */
}

new GDPlugin().init(renderChart)
```

### Hard rules

- Keep the GuanData wrapper and `new GDPlugin().init(renderChart)`.
- Write custom logic inside the documented custom-code section when editing an existing snippet.
- Use native CSS only.
- Load external libraries through HTML script tags or equivalent browser imports.
- Prefer creating long-lived chart instances outside `renderChart`, then updating them inside `renderChart`.
- Do not assume the standard runtime already exposes `window.echarts`. If the chart depends on ECharts, reuse the global when present and otherwise load it explicitly before rendering.
- Do not clear or replace the chart container with `innerHTML = ''` after a chart instance may have been mounted there. Use `chart.clear()` and render an empty-state option instead.
- Re-resolve the container node on rerender or validate that any cached node still matches the live DOM. GuanData card resize or drag operations may replace the container node.
- Prefer `echarts.getInstanceByDom(container)` when reusing an ECharts instance.
- Use `ResizeObserver` on the container when available. `window.resize` alone is not sufficient for card drag-resize.

### Available inputs

- `data`: array of data views. Each view is an array of field objects.
- `clickFunc`: sends linkage and jump payloads.
- `config`: includes `theme`, `colors`, `customOptions`, and `language`.
- `utils`: from 5.6.0 the doc explicitly mentions `utils.refreshData()` in standard mode.

## Lite Contract

### Runtime shape

- The editor evaluates code that builds an ECharts `option`.
- `data`, `config`, `clickFunc`, and `utils` are directly available.
- Do not redeclare those names.

### Available utils

```ts
type IUtils = {
  numberFormat: ({ value: number, format?: IFieldNumberFormat }) => any
  getChartInstance: () => any
}
```

### Hard rules

- Assign to `option = { ... }`.
- Lite code may include field extraction, guards, formatting helpers, and click binding around the final `option = { ... }`. Do not return a full `renderChart` wrapper.
- Use `utils.getChartInstance()` for post-render event binding.
- Remove old listeners before rebinding.
- Do not rely on `localStorage`, `indexedDB`, or other trimmed browser globals.

## Data Shape

`data` is always an array of views:

```ts
type IData = Array<
  Array<{
    name: string
    data: Array<any>
    numberFormat?: object | null
  }>
>
```

### Mapping rules

- `data[viewIndex][fieldIndex]` is the only stable path model.
- `field.name` is the source field name.
- `field.data[index]` is the row value for that field.
- Multiple views are supported. Do not assume `data.length === 1`.

### Common mappings

- Category + metric line/bar: `data[0][0]` as categories, `data[0][1]` as numeric series.
- Pie/rose: `data[0][0].data.map((name, index) => ({ name, value: data[0][1].data[index] }))`
- Multi-series single view: first field is dimension, remaining fields become series.
- Multi-view composition: each `data[n]` is a separately prepared BI view; combine explicitly.

## Config Shape

```js
const { theme, colors, customOptions, language } = config || {}
```

### Meaning

- `theme`: `"LIGHT"` or `"DARK"`.
- `colors`: theme palette selected in the BI card.
- `customOptions`: user-defined config fields for the chart.
- `language`: current system language.

### Use guidance

- Prefer `colors` over custom hard-coded palettes.
- Use `theme` to derive text color, axis color, background contrast, and border color.
- Read `customOptions` with defaults so the chart keeps working before panel config is filled in.
- Respect `language` when formatting or localizing labels.

## Linkage Contract

### Canonical payload

```js
clickFunc({
  clickedItems: [
    {
      idx: [0, 0],
      colName: data[0][0].name,
      value: [selectedValue],
    },
  ],
})
```

### Rules

- `idx` is the source column path, not the rendered series index unless they are truly the same source field.
- `colName` is the source field name.
- `value` is always an array.

### Important inference

- The Lite interaction sample on the official page uses `name` instead of `colName`.
- The same page's type definition and standard-mode sample both use `colName`.
- Generate `colName`, not `name`.

## Number Formatting

### Standard mode

- The doc shows a manual `d3-format` based helper for matching GuanData field formatting.
- Use that path only when the request is standard mode and needs exact BI formatting parity.
- When standard mode exposes `utils.numberFormat`, it is acceptable to reuse it, but do not assume it always exists.

### Lite mode

- Prefer `utils.numberFormat({ value, format: field.numberFormat })`.
- Read the `numberFormat` from the relevant metric field.

## Implementation Checklist

1. Choose standard or Lite mode first.
2. Confirm the source field path for every label, metric, and interaction target.
3. Guard for empty or incomplete `data` before rendering.
4. Apply `theme`, `colors`, and `customOptions`.
5. Reuse chart instances when possible.
6. Remove old click listeners before adding new ones.
7. Build `clickFunc` payloads from source-field paths.
8. In standard mode, confirm how the chart library becomes available and gate rendering on it when necessary.
9. In standard mode, avoid DOM replacement of the chart container and use container-level resize observation when available.

## Common Failure Modes

- Returning a full `renderChart` wrapper inside Lite mode.
- Treating Lite as a bare object literal only and omitting needed field extraction or event binding.
- Using chart-library series indexes as GuanData `idx` values without checking the source field path.
- Recreating chart instances on every render when the library already supports updates.
- Binding duplicate click handlers on every rerun.
- Assuming `window.echarts` is always available in standard mode.
- Clearing the chart container with `innerHTML` after an ECharts instance has bound to it, which can cause blank cards on rerender.
- Listening only to `window.resize` and missing GuanData card drag-resize events.
- Ignoring `customOptions` and hard-coding behavior that should be configurable.
- Emitting SCSS, LESS, or browser APIs that the runtime does not expose.
