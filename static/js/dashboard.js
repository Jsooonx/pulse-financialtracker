/**
 * Pulse Dashboard Logic
 */

function navigateMonth() {
    const month = document.getElementById('month-select').value;
    const year = document.getElementById('year-select').value;
    window.location.href = `/?month=${month}&year=${year}`;
}

function toggleCurrencyDropdown() {
    const wrapper = document.getElementById('currency-select-wrapper');
    if (wrapper) wrapper.classList.toggle('active');
}

function selectCurrency(value) {
    const input = document.getElementById('hidden-currency-input');
    const form = document.getElementById('currency-form-hidden');
    if (input && form) {
        input.value = value;
        form.submit();
    }
}

function formatCurrency(val) {
    const currency = window.PULSE_CONFIG.currentCurrency;
    if (currency === "IDR") {
        return "Rp" + val.toLocaleString('id-ID');
    } else if (currency === "EUR") {
        return "€" + val.toLocaleString('de-DE');
    } else {
        return "$" + val.toLocaleString('en-US');
    }
}

function initCharts() {
    const config = window.PULSE_CONFIG;
    if (!config) return;
    
    // Pie Chart
    const ctx = document.getElementById('expense-chart');
    if (ctx && config.chartLabels) {
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: config.chartLabels,
                datasets: [{
                    data: config.chartAmounts,
                    backgroundColor: config.chartColors,
                    borderWidth: 0,
                    hoverOffset: 8,
                    borderRadius: 4,
                    spacing: 2,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                cutout: '68%',
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: '#174E4F',
                        titleColor: '#F3E5C3',
                        bodyColor: '#d4c9ad',
                        borderColor: 'rgba(243, 229, 195, 0.2)',
                        borderWidth: 1,
                        cornerRadius: 12,
                        padding: 12,
                        titleFont: { family: 'Inter', weight: '600', size: 13 },
                        bodyFont: { family: 'Inter', size: 12 },
                        callbacks: {
                            label: function(context) {
                                const val = context.parsed;
                                const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                const pct = ((val / total) * 100).toFixed(1);
                                return `${formatCurrency(val)} (${pct}%)`;
                            }
                        }
                    }
                },
                animation: {
                    animateScale: true,
                    animateRotate: true,
                    duration: 800,
                    easing: 'easeOutQuart',
                }
            }
        });
    }

    // Trend Chart
    const trendCtx = document.getElementById('trend-chart');
    if (trendCtx && config.trendLabels) {
        new Chart(trendCtx, {
            type: 'line',
            data: {
                labels: config.trendLabels,
                datasets: [
                    {
                        label: 'Income',
                        data: config.trendIncome,
                        borderColor: '#6EE7B7',
                        backgroundColor: 'rgba(110, 231, 183, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    },
                    {
                        label: 'Expense',
                        data: config.trendExpense,
                        borderColor: '#FCA5A5',
                        backgroundColor: 'rgba(252, 165, 165, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            color: '#F3E5C3',
                            font: { family: 'Inter', size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: '#174E4F',
                        titleColor: '#F3E5C3',
                        bodyColor: '#d4c9ad',
                        borderColor: 'rgba(243, 229, 195, 0.2)',
                        borderWidth: 1,
                        cornerRadius: 12,
                        padding: 12,
                        titleFont: { family: 'Inter', weight: '600', size: 13 },
                        bodyFont: { family: 'Inter', size: 12 },
                        callbacks: {
                            label: function(context) {
                                return `${context.dataset.label}: ${formatCurrency(context.parsed.y)}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        grid: { color: 'rgba(243, 229, 195, 0.05)' },
                        ticks: { color: '#9c9480', font: { family: 'Inter' } }
                    },
                    y: {
                        grid: { color: 'rgba(243, 229, 195, 0.05)' },
                        ticks: {
                            color: '#9c9480',
                            font: { family: 'Inter' },
                            callback: function(value) {
                                if (config.currentCurrency === "IDR") {
                                    return value >= 1000000 ? (value/1000000).toFixed(1) + 'M' : value >= 1000 ? (value/1000).toFixed(0) + 'k' : value;
                                }
                                return value >= 1000 ? (value/1000).toFixed(1) + 'k' : value;
                            }
                        }
                    }
                },
                interaction: {
                    intersect: false,
                    mode: 'index',
                },
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', () => {
    // Currency outside click
    document.addEventListener('click', (e) => {
        const wrapper = document.getElementById('currency-select-wrapper');
        if (wrapper && !wrapper.contains(e.target)) {
            wrapper.classList.remove('active');
        }
    });

    initCharts();
});
