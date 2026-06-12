import './style.css';

const statusEl = document.getElementById('connection-status');
const logList = document.getElementById('log-list');
const positionsCountEl = document.getElementById('positions-count');
let websocketConnected = false;
const loginUrlEl = document.getElementById('zerodha-login-url');
const redirectUrlEl = document.getElementById('zerodha-redirect-url');
const authStatusEl = document.getElementById('zerodha-auth-status');
    // Admin token removed

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
                
                if (data.candidates && data.candidates.length > 0) {
                    const friendlyCands = data.candidates.map(c => {
                        const parts = c.split(' ');
                        const sym = parts[0];
                        const dir = parts[1] || '';
                        const strat = parts[2] || '';
                        const formattedStrat = strat ? strat.replace('-v1', '') : '';
                        return `looking for ${dir} setup on ${sym} (via ${formattedStrat})`;
                    });
                    
                    // Deduplicate if needed, though they now have different strategies
                    const uniqueCands = [...new Set(friendlyCands)];
                    const timeStr = new Date(data.timestamp).toLocaleTimeString();
                    addLog(`[${timeStr}] AI Engine is ${uniqueCands.join(' | ')}`, 'info');
                } else {
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
    const li = document.createElement('li');
    li.className = `log-entry log-${type}`;
    // Add icon based on type
    let icon = '⚡️';
    if (type === 'tick') icon = '🔍';
    if (type === 'error') icon = '⚠️';
    
    li.innerHTML = `<span class="log-icon">${icon}</span> <span class="log-text">${message}</span>`;
    logList.prepend(li);
    
    // Keep max 50 logs
    if (logList.children.length > 50) {
        logList.lastChild.remove();
    }
}

// Boot
connectWebSocket();
setInterval(refreshRuntimeHealth, 5000);
