#!/usr/bin/env python3
"""Print GuanData-compatible starter templates for standard and Lite charts."""

import argparse
import sys


STANDARD_TEMPLATE = """let chart = null
let resizeObserver = null
let echartsReady = null

function loadEcharts() {
  if (window.echarts) {
    return Promise.resolve(window.echarts)
  }

  if (echartsReady) {
    return echartsReady
  }

  echartsReady = new Promise((resolve, reject) => {
    const existingScript = document.querySelector('script[data-gd-echarts="1"]')

    if (existingScript) {
      const startedAt = Date.now()
      const timer = setInterval(() => {
        if (window.echarts) {
          clearInterval(timer)
          resolve(window.echarts)
          return
        }
        if (Date.now() - startedAt > 10000) {
          clearInterval(timer)
          reject(new Error('ECharts load timeout'))
        }
      }, 50)
      return
    }

    const script = document.createElement('script')
    script.src = 'https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js'
    script.async = true
    script.setAttribute('data-gd-echarts', '1')
    script.onload = () => {
      if (window.echarts) {
        resolve(window.echarts)
      } else {
        reject(new Error('ECharts loaded but unavailable'))
      }
    }
    script.onerror = () => reject(new Error('Failed to load ECharts'))
    document.head.appendChild(script)
  })

  return echartsReady
}

function ensureChart(container) {
  const existingChart = window.echarts.getInstanceByDom(container)

  if (existingChart) {
    chart = existingChart
  } else if (!chart) {
    chart = window.echarts.init(container)
  } else if (chart.getDom && chart.getDom() !== container) {
    chart.dispose()
    chart = window.echarts.init(container)
  }

  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }

  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      if (chart) {
        chart.resize()
      }
    })
    resizeObserver.observe(container)
  }

  return chart
}

function buildEmptyOption(message) {
  return {
    title: {
      text: message,
      left: 'center',
      top: 'middle',
    },
  }
}

function buildClickedItems(data, viewIndex, fieldIndex, rawValue) {
  const field = data?.[viewIndex]?.[fieldIndex]
  if (!field) {
    return []
  }
  return [
    {
      idx: [viewIndex, fieldIndex],
      colName: field.name,
      value: [String(rawValue)],
    },
  ]
}

function renderChart(data, clickFunc, config, utils) {
  loadEcharts()
    .then(() => {
      const container = document.getElementById('container')
      if (!container) {
        return
      }

      const categoryField = data?.[0]?.[0]
      const metricField = data?.[0]?.[1]
      const { theme = 'LIGHT', colors = [], customOptions = {} } = config || {}
      const isDarkTheme = theme === 'DARK'
      const chartInstance = ensureChart(container)

      if (!categoryField || !metricField) {
        chartInstance.clear()
        chartInstance.setOption(buildEmptyOption('Missing required fields'), true)
        return
      }

      const option = {
        color: colors,
        grid: {
          top: 24,
          right: 16,
          bottom: 40,
          left: 56,
          containLabel: true,
        },
        tooltip: {
          trigger: 'axis',
        },
        xAxis: {
          type: 'category',
          data: categoryField.data,
          axisLabel: {
            color: isDarkTheme ? '#D1D8E3' : '#343D50',
          },
        },
        yAxis: {
          type: 'value',
          axisLabel: {
            color: isDarkTheme ? '#D1D8E3' : '#343D50',
          },
        },
        series: [
          {
            type: customOptions.seriesType || 'bar',
            data: metricField.data,
            smooth: customOptions.seriesType === 'line',
          },
        ],
      }

      chartInstance.off('click')
      chartInstance.clear()
      chartInstance.setOption(option, true)
      chartInstance.on('click', (params) => {
        if (!clickFunc) {
          return
        }
        clickFunc({
          clickedItems: buildClickedItems(data, 0, 0, params.name),
        })
      })
      chartInstance.resize()
    })
    .catch(() => {
      const container = document.getElementById('container')
      if (!container) {
        return
      }
      container.innerHTML = '<div style="padding:16px;text-align:center;">Chart library failed to load</div>'
    })
}

new GDPlugin().init(renderChart)
"""


LITE_TEMPLATE = """const categoryField = data?.[0]?.[0]
const metricField = data?.[0]?.[1]
const { theme = 'LIGHT', colors = [], customOptions = {} } = config || {}

if (!categoryField || !metricField) {
  option = {
    title: {
      text: 'Missing required fields',
      left: 'center',
      top: 'middle',
    },
  }
} else {
  option = {
    color: colors,
    grid: {
      top: 24,
      right: 16,
      bottom: 40,
      left: 56,
      containLabel: true,
    },
    tooltip: {
      trigger: 'axis',
    },
    xAxis: {
      type: 'category',
      data: categoryField.data,
      axisLabel: {
        color: theme === 'DARK' ? '#D1D8E3' : '#343D50',
      },
    },
    yAxis: {
      type: 'value',
      axisLabel: {
        color: theme === 'DARK' ? '#D1D8E3' : '#343D50',
        formatter: (value) => {
          if (metricField.numberFormat) {
            return utils.numberFormat({ value, format: metricField.numberFormat })
          }
          return value
        },
      },
    },
    series: [
      {
        type: customOptions.seriesType || 'bar',
        data: metricField.data,
        smooth: customOptions.seriesType === 'line',
      },
    ],
  }

  const chartInstance = utils.getChartInstance()
  if (chartInstance) {
    chartInstance.off('click')
    chartInstance.on('click', (params) => {
      if (!clickFunc) {
        return
      }
      clickFunc({
        clickedItems: [
          {
            idx: [0, 0],
            colName: categoryField.name,
            value: [String(params.name)],
          },
        ],
      })
    })
  }
}
"""


def main() -> int:
  parser = argparse.ArgumentParser(
      description="Print a GuanData chart starter template."
  )
  parser.add_argument(
      "--mode",
      choices=("standard", "lite"),
      required=True,
      help="Template mode to print.",
  )
  args = parser.parse_args()

  if args.mode == "standard":
    sys.stdout.write(STANDARD_TEMPLATE)
  else:
    sys.stdout.write(LITE_TEMPLATE)
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
