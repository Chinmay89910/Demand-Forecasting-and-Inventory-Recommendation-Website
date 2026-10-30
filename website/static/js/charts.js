// RestockIQ: Interactive Chart.js Visualizations

function renderForecastChart(canvasId, chartData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const historyDates = chartData.historyDates || [];
  const historyValues = chartData.historyValues || [];
  const forecastDates = chartData.forecastDates || [];
  const forecastValues = chartData.forecastValues || [];
  const lowerBounds = chartData.lowerBounds || [];
  const upperBounds = chartData.upperBounds || [];

  const allLabels = [...historyDates, ...forecastDates];
  
  // Align history array to match total timeline length
  const alignedHistory = [...historyValues, ...new Array(forecastDates.length).fill(null)];
  
  // Align forecast line (bridge from last historical point for continuity)
  const lastHistoryVal = historyValues[historyValues.length - 1] || null;
  const alignedForecast = [...new Array(historyDates.length - 1).fill(null), lastHistoryVal, ...forecastValues];
  
  const alignedLower = [...new Array(historyDates.length - 1).fill(null), lastHistoryVal, ...lowerBounds];
  const alignedUpper = [...new Array(historyDates.length - 1).fill(null), lastHistoryVal, ...upperBounds];

  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: allLabels,
      datasets: [
        {
          label: 'Historical Actual Sales',
          data: alignedHistory,
          type: 'bar',
          backgroundColor: 'rgba(27, 67, 50, 0.25)',
          borderColor: '#1B4332',
          borderWidth: 1.5,
          borderRadius: 6,
          order: 3,
        },
        {
          label: '7-Day Demand Forecast (GBDT + Calendar)',
          data: alignedForecast,
          type: 'line',
          borderColor: '#2D6A4F',
          backgroundColor: '#2D6A4F',
          borderWidth: 3,
          pointBackgroundColor: '#FFB702',
          pointBorderColor: '#1B4332',
          pointRadius: 5,
          pointHoverRadius: 7,
          tension: 0.35,
          order: 1,
        },
        {
          label: 'Forecast Upper Bound (90% CI)',
          data: alignedUpper,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: 'rgba(45, 106, 79, 0.12)',
          pointRadius: 0,
          fill: '+1',
          tension: 0.35,
          order: 2,
        },
        {
          label: 'Forecast Lower Bound (90% CI)',
          data: alignedLower,
          type: 'line',
          borderColor: 'transparent',
          backgroundColor: 'transparent',
          pointRadius: 0,
          fill: false,
          tension: 0.35,
          order: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          position: 'top',
          labels: {
            font: { family: 'Inter', size: 12, weight: '500' },
            boxWidth: 14,
            usePointStyle: true,
          },
        },
        tooltip: {
          backgroundColor: '#1B4332',
          titleFont: { family: 'Montserrat', size: 13, weight: 'bold' },
          bodyFont: { family: 'Inter', size: 12 },
          padding: 10,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              const val = context.raw;
              if (val === null || val === undefined) return null;
              return `${context.dataset.label}: ${val} units`;
            }
          }
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { font: { family: 'Inter', size: 11 } },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(229, 224, 216, 0.6)' },
          ticks: { font: { family: 'Inter', size: 11 } },
          title: {
            display: true,
            text: 'Units Sold / Predicted',
            font: { family: 'Inter', size: 11, weight: '600' },
          },
        },
      },
    },
  });
}

function drawUniversalRoundedRect(c, x, y, width, height, radius) {
  c.beginPath();
  c.moveTo(x + radius, y);
  c.lineTo(x + width - radius, y);
  c.quadraticCurveTo(x + width, y, x + width, y + radius);
  c.lineTo(x + width, y + height - radius);
  c.quadraticCurveTo(x + width, y + height, x + width - radius, y + height);
  c.lineTo(x + radius, y + height);
  c.quadraticCurveTo(x, y + height, x, y + height - radius);
  c.lineTo(x, y + radius);
  c.quadraticCurveTo(x, y, x + radius, y);
  c.closePath();
}

function renderActualVsPredictedChart(canvasId, chartData) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return null;

  const labels = chartData.labels || [];
  const actualSales = chartData.actual_sales || [];
  const predictedSales = chartData.predicted_sales || [];
  const lowerBounds = chartData.lower_bounds || [];
  const upperBounds = chartData.upper_bounds || [];
  const todayIdx = chartData.today_index !== undefined ? chartData.today_index : 8;

  // Vertical dashed divider plugin
  const dividerPlugin = {
    id: 'forecastDividerPlugin',
    afterDraw(chart) {
      try {
        const meta = chart.getDatasetMeta(0);
        if (!meta || !meta.data || !meta.data[todayIdx]) return;
        const x = meta.data[todayIdx].x;
        const top = chart.chartArea.top;
        const bottom = chart.chartArea.bottom;
        const c = chart.ctx;

        c.save();
        // Dashed vertical line
        c.beginPath();
        c.setLineDash([4, 4]);
        c.strokeStyle = '#94A3B8';
        c.lineWidth = 1.5;
        c.moveTo(x, top + 26);
        c.lineTo(x, bottom);
        c.stroke();

        // Divider pills/labels at top
        // "← Historical" pill
        const histText = '← Historical';
        c.font = '600 11px Inter, system-ui, sans-serif';
        const histWidth = c.measureText(histText).width + 16;
        drawUniversalRoundedRect(c, x - histWidth - 6, top + 4, histWidth, 20, 4);
        c.fillStyle = '#EFF6FF';
        c.fill();
        c.strokeStyle = '#BFDBFE';
        c.lineWidth = 1;
        c.stroke();
        c.fillStyle = '#2563EB';
        c.fillText(histText, x - histWidth + 2, top + 18);

        // "Forecast →" pill
        const foreText = 'Forecast →';
        const foreWidth = c.measureText(foreText).width + 16;
        drawUniversalRoundedRect(c, x + 6, top + 4, foreWidth, 20, 4);
        c.fillStyle = '#F0FDF4';
        c.fill();
        c.strokeStyle = '#BBF7D0';
        c.lineWidth = 1;
        c.stroke();
        c.fillStyle = '#16A34A';
        c.fillText(foreText, x + 14, top + 18);

        c.restore();
      } catch (err) {
        console.warn('Divider plugin draw notice:', err);
      }
    }
  };

  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [
        {
          label: 'Actual Sales (Past)',
          data: actualSales,
          borderColor: '#2563EB',
          backgroundColor: '#2563EB',
          pointBackgroundColor: '#2563EB',
          pointBorderColor: '#FFFFFF',
          pointBorderWidth: 2,
          pointRadius: 4.5,
          pointHoverRadius: 7,
          borderWidth: 2.5,
          tension: 0.25,
          order: 1,
        },
        {
          label: 'Predicted Demand',
          data: predictedSales,
          borderColor: '#16A34A',
          backgroundColor: '#16A34A',
          pointBackgroundColor: '#16A34A',
          pointBorderColor: '#FFFFFF',
          pointBorderWidth: 2,
          pointRadius: 4.5,
          pointHoverRadius: 7,
          borderWidth: 2.5,
          tension: 0.25,
          order: 2,
        },
        {
          label: 'Uncertainty Range (Upper)',
          data: upperBounds,
          borderColor: 'transparent',
          backgroundColor: 'rgba(34, 197, 94, 0.14)',
          pointRadius: 0,
          fill: '+1',
          tension: 0.25,
          order: 3,
        },
        {
          label: 'Uncertainty Range (Lower)',
          data: lowerBounds,
          borderColor: 'transparent',
          backgroundColor: 'transparent',
          pointRadius: 0,
          fill: false,
          tension: 0.25,
          order: 4,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          display: false, // HTML custom legend used in card header
        },
        tooltip: {
          backgroundColor: '#0F172A',
          titleFont: { family: 'Montserrat', size: 12, weight: 'bold' },
          bodyFont: { family: 'Inter', size: 12 },
          padding: 10,
          cornerRadius: 8,
          filter: function(item) {
            return item.raw !== null && item.datasetIndex < 2;
          },
          callbacks: {
            label: function(context) {
              const val = context.raw;
              if (val === null || val === undefined) return null;
              return `${context.dataset.label}: ${val} units`;
            }
          }
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            font: { family: 'Inter', size: 10.5 },
            color: '#64748B',
            maxRotation: 0,
            autoSkip: false,
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(226, 232, 240, 0.8)' },
          ticks: {
            font: { family: 'Inter', size: 11 },
            color: '#64748B',
            stepSize: 20,
          },
          title: {
            display: true,
            text: 'Units Sold',
            color: '#475569',
            font: { family: 'Inter', size: 11, weight: '600' },
          },
        },
      },
    },
    plugins: [dividerPlugin],
  });
}

