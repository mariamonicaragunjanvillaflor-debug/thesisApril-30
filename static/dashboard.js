// ----------------------------
// Breaker Monitoring Dashboard JS (FIXED VERSION)
// ----------------------------

const BACKEND_URL = "";

// ----------------------------
// ALERT STYLES
// ----------------------------
const alertStyle = document.createElement("style");
alertStyle.textContent = `
@keyframes slideIn {
    from { transform: translateX(100%); opacity: 0; }
    to { transform: translateX(0); opacity: 1; }
}
`;
document.head.appendChild(alertStyle);

// ----------------------------
// DATA STORAGE
// ----------------------------
let tempHistory = [];
let currentHistory = [];
let historyData = [];
const MAX_HISTORY = 20;

let isFetching = false;

// ----------------------------
// CANVAS GRAPH SETUP
// ----------------------------
let tempCanvas, currentCanvas;
let tempCtx, currentCtx;

function initGraphs() {
    tempCanvas = document.getElementById("tempGraph");
    currentCanvas = document.getElementById("currentGraph");

    if (!tempCanvas || !currentCanvas) return;

    tempCtx = tempCanvas.getContext("2d");
    currentCtx = currentCanvas.getContext("2d");

    const resizeCanvas = () => {
        const width = tempCanvas.parentElement.clientWidth;
        tempCanvas.width = width;
        currentCanvas.width = width;
        tempCanvas.height = 50;
        currentCanvas.height = 50;
        drawGraphs();
    };

    resizeCanvas();
    window.addEventListener("resize", resizeCanvas);
}

function drawGraph(ctx, data, color, maxValue) {
    if (!ctx || data.length < 2) return;

    const width = ctx.canvas.width;
    const height = ctx.canvas.height;

    ctx.clearRect(0, 0, width, height);

    const step = width / (data.length - 1);

    ctx.beginPath();
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;

    data.forEach((val, i) => {
        const x = i * step;
        const y = height - (val / maxValue) * height;

        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });

    ctx.stroke();
}

function drawGraphs() {
    drawGraph(tempCtx, tempHistory, "#0ea5e9", 100);
    drawGraph(currentCtx, currentHistory, "#facc15", 50);
}

// ----------------------------
// HISTORY STORAGE
// ----------------------------
function addToHistory(data) {
    historyData.unshift({
        time: new Date().toLocaleTimeString(),
        temperature: data.temperature,
        current: data.current,
        breakerState: data.breakerState
    });

    if (historyData.length > 10) historyData.pop();

    renderHistoryTable();
}

function renderHistoryTable() {
    const logBody = document.getElementById("log-body");
    if (!logBody) return;

    logBody.innerHTML = "";

    if (historyData.length === 0) {
        logBody.innerHTML = `<tr><td colspan="4" style="text-align:center;">Waiting for data...</td></tr>`;
        return;
    }

    historyData.forEach(entry => {
        const row = document.createElement("tr");

        row.innerHTML = `
            <td>${entry.time}</td>
            <td>${entry.temperature.toFixed(1)}°C</td>
            <td>${entry.current.toFixed(2)}A</td>
            <td>${entry.breakerState}</td>
        `;

        logBody.appendChild(row);
    });
}

// ----------------------------
// DASHBOARD UPDATE
// ----------------------------
function updateDashboard(data) {
    if (!data) return;

    console.log("📊 DATA RECEIVED:", data);

    // graphs
    tempHistory.push(data.temperature || 0);
    currentHistory.push(data.current || 0);

    if (tempHistory.length > MAX_HISTORY) tempHistory.shift();
    if (currentHistory.length > MAX_HISTORY) currentHistory.shift();

    drawGraphs();

    // UI values
    document.getElementById("temperature-value").textContent =
        (data.temperature || 0).toFixed(1);

    document.getElementById("current-value").textContent =
        (data.current || 0).toFixed(2);

    document.getElementById("breaker-state").textContent =
        data.breakerState || "Unknown";

    // style state
    const breakerEl = document.getElementById("breaker-state");
    if (breakerEl) {
        breakerEl.className = `kpi__value state ${data.breakerState}`;
    }

    // add history
    addToHistory(data);
}

// ----------------------------
// FETCH BACKEND DATA (FIXED)
// ----------------------------
async function refreshDashboard() {
    if (isFetching) return;
    isFetching = true;

    try {
        const response = await fetch(`${BACKEND_URL}/api/latest-data`);

        if (!response.ok) {
            console.warn("Backend not ready:", response.status);
            return;
        }

        const data = await response.json();

        if (!data || Object.keys(data).length === 0) return;

        updateDashboard(data);

    } catch (err) {
        console.error("Fetch error:", err);
    } finally {
        isFetching = false;
    }
}

// ----------------------------
// INIT
// ----------------------------
window.addEventListener("load", () => {
    console.log("🚀 Dashboard starting...");
    initGraphs();

    setTimeout(refreshDashboard, 1000);
    setInterval(refreshDashboard, 2000);
});