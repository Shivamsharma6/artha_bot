import './style.css';

const statusEl = document.getElementById('connection-status');
const logList = document.getElementById('log-list');
const positionsCountEl = document.getElementById('positions-count');
let websocketConnected = false;
const loginUrlEl = document.getElementById('zerodha-login-url');
const redirectUrlEl = document.getElementById('zerodha-redirect-url');
const authStatusEl = document.getElementById('zerodha-auth-status');
const closedTradesListEl = document.getElementById('closed-trades-list');
const watchlistListEl = document.getElementById('watchlist-list');
const riskProgressFillEl = document.getElementById('risk-progress-fill');
const riskValueTextEl = document.getElementById('risk-value-text');

let systemLogs = [];
let currentLogFilter = 'all';
let pnlHistory = [];
let pnlChart = null;

// Initialize Chart
function initChart() {
    const ctx = document.getElementById('pnl-chart').getContext('2d');
    pnlChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Day P&L',
                data: [],
                borderColor: '#00e676',
                backgroundColor: 'rgba(0, 230, 118, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { display: false },
                y: { 
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });
}
initChart();

// Setup Log Filters
document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
        document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        currentLogFilter = e.target.dataset.filter;
        renderLogs();
    });
});

document.getElementById('load-zerodha-login').addEventListener('click', async () => {
    authStatusEl.textContent = 'Loading official login URL...';
    const response = await fetch('/api/auth/zerodha', { cache: 'no-store' });
    const payload = await response.json();
    if (!response.ok) {
        authStatusEl.textContent = payload.detail || 'Unable to load login URL';
        return;
    }
    loginUrlEl.href = payload.login_url;
    loginUrlEl.textContent = payload.login_url;
    loginUrlEl.classList.remove('hidden');
    authStatusEl.textContent = 'Open the URL, finish Zerodha login, then paste the redirected URL below.';
});

document.getElementById('exchange-zerodha-token').addEventListener('click', async () => {
    authStatusEl.textContent = 'Validating session...';
    const response = await fetch('/api/auth/zerodha/exchange', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ redirect_url: redirectUrlEl.value }),
    });
    const payload = await response.json();
    redirectUrlEl.value = '';
    if (!response.ok) {
        authStatusEl.textContent = payload.detail || 'Session validation failed';
        return;
    }
    authStatusEl.textContent = `Session validated for ${payload.user_id}. Auto-restarting the ArthaBot container...`;
    setTimeout(() => {
        window.location.reload();
    }, 3000);
});

async function refreshRuntimeHealth() {
    if (!websocketConnected) return;
    try {
        const response = await fetch('/api/health', { cache: 'no-store' });
        const health = await response.json();
        const authSection = document.querySelector('.broker-auth');
        if (health.trading_ready) {
            statusEl.textContent = 'Connected (PAPER)';
            statusEl.className = 'status connected';
            if (authSection) authSection.style.display = 'none';
        } else {
            statusEl.textContent = 'Connected (PAPER, degraded)';
            statusEl.className = 'status disconnected';
            if (authSection) authSection.style.display = 'block';
        }
    } catch (error) {
        statusEl.textContent = 'Connected (health unavailable)';
        statusEl.className = 'status disconnected';
    }
}

function connectWebSocket() {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${wsProtocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        websocketConnected = true;
        statusEl.textContent = 'Connected (PAPER)';
        statusEl.className = 'status connected';
        addLog('System: Connected to ArthaBot WebSocket', 'info');
        refreshRuntimeHealth();
    };

    ws.onclose = () => {
        websocketConnected = false;
        statusEl.textContent = 'Disconnected';
        statusEl.className = 'status disconnected';
        addLog('System: Disconnected. Reconnecting...', 'error');
        setTimeout(connectWebSocket, 2000); // Reconnect
    };

    ws.onerror = (err) => {
        console.error('WebSocket Error:', err);
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'MARKET_TICK') {
                // Update simple metrics
                if (data.open_positions !== undefined) {
                    positionsCountEl.textContent = data.open_positions;
                }
                if (data.pnl !== undefined) {
                    const pnlEl = document.getElementById('pnl-value');
                    pnlEl.textContent = `₹${data.pnl.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                    pnlEl.style.color = data.pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
                }
                if (data.win_rate !== undefined) {
                    const winRateEl = document.getElementById('win-rate-value');
                    winRateEl.textContent = `${data.win_rate.toFixed(1)}%`;
                }
                if (data.total_trades !== undefined) {
                    const tradesEl = document.getElementById('total-trades-value');
                    tradesEl.textContent = data.total_trades;
                }
                if (data.capital !== undefined && data.pnl !== undefined) {
                    const capitalEl = document.getElementById('capital-value');
                    const net = data.capital + data.pnl;
                    capitalEl.textContent = `₹${net.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                }
                
                // Update Risk Bar
                if (data.daily_loss_limit && data.daily_loss_limit > 0) {
                    const realizedLoss = data.pnl < 0 ? Math.abs(data.pnl) : 0;
                    let pct = (realizedLoss / data.daily_loss_limit) * 100;
                    if (pct > 100) pct = 100;
                    riskValueTextEl.textContent = `${pct.toFixed(1)}%`;
                    riskProgressFillEl.style.width = `${pct}%`;
                    if (pct < 50) {
                        riskProgressFillEl.style.background = 'var(--accent-green)';
                    } else if (pct < 80) {
                        riskProgressFillEl.style.background = '#ffeb3b';
                    } else {
                        riskProgressFillEl.style.background = 'var(--accent-red)';
                    }
                }

                // Update Chart
                if (data.pnl !== undefined && pnlChart) {
                    const timeStr = new Date(data.timestamp).toLocaleTimeString();
                    pnlHistory.push({ time: timeStr, pnl: data.pnl });
                    if (pnlHistory.length > 50) pnlHistory.shift();
                    
                    pnlChart.data.labels = pnlHistory.map(d => d.time);
                    pnlChart.data.datasets[0].data = pnlHistory.map(d => d.pnl);
                    pnlChart.data.datasets[0].borderColor = data.pnl >= 0 ? '#00e676' : '#ff3d00';
                    pnlChart.data.datasets[0].backgroundColor = data.pnl >= 0 ? 'rgba(0, 230, 118, 0.1)' : 'rgba(255, 61, 0, 0.1)';
                    pnlChart.update();
                }

                if (data.mode) {
                    const modeBadge = document.getElementById('system-mode');
                    modeBadge.textContent = data.mode;
                    modeBadge.className = `mode-badge ${data.mode.toLowerCase()}`;
                }
                
                if (data.positions_list) {
                    const listEl = document.getElementById('positions-list');
                    if (data.positions_list.length === 0) {
                        listEl.innerHTML = '<div class="placeholder-text">No active positions currently running</div>';
                    } else {
                        listEl.innerHTML = data.positions_list.map(p => {
                            const isProfit = p.pnl >= 0;
                            const pnlFormatted = `₹${Math.abs(p.pnl).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                            const pnlLabel = isProfit ? `+${pnlFormatted}` : `-${pnlFormatted}`;
                            return `
                            <div class="position-card">
                                <div class="position-info">
                                    <span class="position-symbol">${p.symbol}</span>
                                    <span class="position-exchange">NSE</span>
                                </div>
                                <div class="position-pnl" style="color: ${isProfit ? '#4caf50' : '#f44336'}">
                                    ${pnlLabel}
                                </div>
                            </div>`;
                        }).join('');
                    }
                }
                
                // Render Closed Trades
                if (data.trades) {
                    const closedTrades = data.trades.filter(t => t.accepted);
                    if (closedTrades.length === 0) {
                        closedTradesListEl.innerHTML = '<div class="placeholder-text">No closed trades</div>';
                    } else {
                        closedTradesListEl.innerHTML = closedTrades.map(t => {
                            const netPnl = parseFloat(t.gross_pnl) - parseFloat(t.total_costs);
                            const isProfit = netPnl >= 0;
                            const pnlFormatted = `₹${Math.abs(netPnl).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                            const pnlLabel = isProfit ? `+${pnlFormatted}` : `-${pnlFormatted}`;
                            return `
                            <div class="position-card" style="padding: 0.75rem; border-color: rgba(255,255,255,0.02)">
                                <div class="position-info">
                                    <span class="position-symbol" style="font-size: 1rem;">${t.symbol}</span>
                                    <span style="font-size: 0.65rem; color: var(--text-muted)">Costs: ₹${parseFloat(t.total_costs).toFixed(2)}</span>
                                </div>
                                <div class="position-pnl" style="font-size: 1rem; color: ${isProfit ? '#4caf50' : '#f44336'}">
                                    ${pnlLabel}
                                </div>
                            </div>`;
                        }).join('');
                    }
                }

                if (data.candidates && data.candidates.length > 0) {
                    watchlistListEl.innerHTML = data.candidates.map(c => {
                        const parts = c.split(' ');
                        const sym = parts[0];
                        const dir = parts[1] || '';
                        const strat = parts[2] || '';
                        const formattedStrat = strat ? strat.replace('-v1', '') : '';
                        return `
                        <div class="watchlist-item">
                            <span class="watchlist-symbol">${sym}</span>
                            <span class="watchlist-dir ${dir.toLowerCase()}">${dir}</span>
                            <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 0.25rem;">Strategy: ${formattedStrat}</div>
                        </div>`;
                    }).join('');
                    
                    const friendlyCands = data.candidates.map(c => {
                        const parts = c.split(' ');
                        const sym = parts[0];
                        const dir = parts[1] || '';
                        const strat = parts[2] || '';
                        const formattedStrat = strat ? strat.replace('-v1', '') : '';
                        return `looking for ${dir} setup on ${sym} (via ${formattedStrat})`;
                    });
                    
                    const uniqueCands = [...new Set(friendlyCands)];
                    const timeStr = new Date(data.timestamp).toLocaleTimeString();
                    addLog(`[${timeStr}] AI Engine is ${uniqueCands.join(' | ')}`, 'info');
                } else {
                    watchlistListEl.innerHTML = '<div class="placeholder-text">Scanning for candidates...</div>';
                    const timeStr = new Date(data.timestamp).toLocaleTimeString();
                    addLog(`[${timeStr}] Scanning market for high-probability setups...`, 'tick');
                }
            }
        } catch (e) {
            console.error("Failed to parse message:", e);
        }
    };
}

function addLog(message, type = 'info') {
    // Add to state
    systemLogs.unshift({ message, type, id: Date.now() + Math.random() });
    
    // Keep max 100 logs
    if (systemLogs.length > 100) {
        systemLogs.pop();
    }
    
    renderLogs();
}

function renderLogs() {
    logList.innerHTML = '';
    
    const filteredLogs = systemLogs.filter(log => {
        if (currentLogFilter === 'all') return true;
        return log.type === currentLogFilter;
    });

    filteredLogs.forEach(log => {
        const li = document.createElement('li');
        li.className = `log-entry log-${log.type}`;
        
        let icon = '⚡️';
        if (log.type === 'tick') icon = '🔍';
        if (log.type === 'error') icon = '⚠️';
        
        li.innerHTML = `<span class="log-icon">${icon}</span> <span class="log-text">${log.message}</span>`;
        logList.appendChild(li);
    });
}

// Boot
connectWebSocket();
setInterval(refreshRuntimeHealth, 5000);
