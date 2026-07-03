(() => {
  "use strict";

  const state = {
    devices: [],
    selectedDeviceId: null,
    zoom: 1.0,
    logSince: 0,
    dragStart: null,
    screenLoaded: false,
  };

  const el = (id) => document.getElementById(id);

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(body.detail || res.statusText);
    }
    return res;
  }

  // Classify a human-readable action message into a banner tone so the
  // "Current Action" panel reads as a status indicator, not just a log line.
  function classify(text) {
    const t = text.toLowerCase();
    if (/(failed|error|not ready|no device)/.test(t)) return "error";
    if (/(…|connecting|capturing|launching|starting|typing|tapping|swiping|stopping)/.test(t)) return "busy";
    if (/(connected|captured|sent|tapped|complete|running|stopped|launched)/.test(t)) return "success";
    return "idle";
  }

  function setAction(text, kind) {
    const tone = kind || classify(text);
    const banner = el("current-action");
    el("current-action-text").textContent = text;
    banner.className = "status-banner" + (tone === "idle" ? "" : ` banner-${tone}`);
  }

  function setGlobalStatus(text, tone) {
    const banner = el("global-status");
    el("global-status-text").textContent = text;
    banner.className = "status-banner" + (tone ? ` banner-${tone}` : "");
  }

  function selectedDevice() {
    return state.devices.find((d) => d.id === state.selectedDeviceId) || null;
  }

  function refreshGlobalStatus() {
    const connected = state.devices.filter((d) => d.connected);
    if (connected.length === 0) {
      setGlobalStatus("No device connected");
    } else if (connected.length === 1) {
      setGlobalStatus(`Connected · ${connected[0].name}`, "success");
    } else {
      setGlobalStatus(`${connected.length} devices connected`, "success");
    }
  }

  // ---------------------------------------------------------------------
  // Devices
  // ---------------------------------------------------------------------

  const DEVICE_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="2" width="12" height="20" rx="2"/><line x1="11" y1="19" x2="13" y2="19"/></svg>`;

  async function refreshDevices() {
    const res = await api("/api/devices");
    state.devices = await res.json();
    if (!state.selectedDeviceId && state.devices.length) {
      state.selectedDeviceId = state.devices[0].id;
    }
    renderDevices();
    renderDeviceInfo();
    refreshGlobalStatus();
  }

  function renderDevices() {
    const list = el("device-list");
    list.innerHTML = "";
    if (!state.devices.length) {
      list.innerHTML = `<li class="empty-hint">No devices found. Connect a phone via USB (or ADB over Wi-Fi) with USB debugging enabled, then click refresh.</li>`;
      return;
    }
    for (const d of state.devices) {
      const li = document.createElement("li");
      li.className = "device-card" + (d.id === state.selectedDeviceId ? " selected" : "");
      const statusClass = ["online", "offline", "unauthorized"].includes(d.status) ? d.status : "unknown";
      li.innerHTML = `
        <div class="device-icon">${DEVICE_ICON}</div>
        <div class="device-card-body">
          <div class="name">${d.name}</div>
          <div class="meta">
            <span class="status-dot ${statusClass}"></span>
            <span class="status-text ${statusClass}">${d.status}</span>
            ${d.connected ? '<span class="connected-pill">Connected</span>' : ""}
          </div>
        </div>
      `;
      li.addEventListener("click", () => {
        state.selectedDeviceId = d.id;
        renderDevices();
        renderDeviceInfo();
      });
      list.appendChild(li);
    }
  }

  function renderDeviceInfo() {
    const d = selectedDevice();
    const dl = el("device-info");
    if (!d) {
      dl.innerHTML = "<dt>Status</dt><dd>No device selected</dd>";
      return;
    }
    const statusClass = ["online", "offline", "unauthorized"].includes(d.status) ? d.status : "unknown";
    dl.innerHTML = `
      <dt>Name</dt><dd>${d.name}</dd>
      <dt>Serial</dt><dd class="mono-text">${d.id}</dd>
      <dt>Status</dt><dd class="status-text ${statusClass}">${d.status}</dd>
      <dt>Transport</dt><dd>${d.transport.toUpperCase()}</dd>
      <dt>Connected</dt><dd>${d.connected ? "Yes" : "No"}</dd>
    `;
  }

  async function connectSelected() {
    const d = selectedDevice();
    if (!d) return setAction("Select a device first", "error");
    setAction(`Connecting to ${d.name}…`);
    try {
      await api(`/api/devices/${d.id}/connect`, { method: "POST" });
      setAction(`Connected to ${d.name}`);
      await refreshDevices();
      await captureScreenshot();
    } catch (err) {
      setAction(`Connect failed: ${err.message}`, "error");
    }
  }

  async function disconnectSelected() {
    const d = selectedDevice();
    if (!d) return;
    await api(`/api/devices/${d.id}/disconnect`, { method: "POST" });
    setAction(`Disconnected from ${d.name}`);
    setScreenVisible(false);
    await refreshDevices();
  }

  // ---------------------------------------------------------------------
  // Screen capture / tap / swipe
  // ---------------------------------------------------------------------

  function setScreenVisible(visible) {
    state.screenLoaded = visible;
    el("screen-img").classList.toggle("hidden", !visible);
    el("viewer-empty").classList.toggle("hidden", visible);
    if (visible) el("coord-readout").textContent = "Click to tap · drag to swipe";
    else el("coord-readout").textContent = "No device connected";
  }

  async function captureScreenshot() {
    const d = selectedDevice();
    if (!d) return setAction("Select and connect a device first", "error");
    setAction("Capturing screen…");
    try {
      const res = await api(`/api/devices/${d.id}/screenshot`);
      const blob = await res.blob();
      const img = el("screen-img");
      img.src = URL.createObjectURL(blob);
      img.onload = () => {
        img.style.width = `${img.naturalWidth * state.zoom}px`;
        setScreenVisible(true);
      };
      setAction("Screen captured");
    } catch (err) {
      setAction(`Screenshot failed: ${err.message}`, "error");
    }
  }

  function imageToDeviceCoords(evt) {
    const img = el("screen-img");
    const rect = img.getBoundingClientRect();
    const scaleX = img.naturalWidth / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const x = Math.round((evt.clientX - rect.left) * scaleX);
    const y = Math.round((evt.clientY - rect.top) * scaleY);
    return { x, y };
  }

  async function tapAt(x, y) {
    const d = selectedDevice();
    if (!d) return;
    setAction(`Tapping (${x}, ${y})…`);
    try {
      await api(`/api/devices/${d.id}/tap`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x, y }),
      });
      setAction(`Tapped (${x}, ${y})`);
    } catch (err) {
      setAction(`Tap failed: ${err.message}`, "error");
    }
  }

  async function swipeFromTo(x1, y1, x2, y2) {
    const d = selectedDevice();
    if (!d) return;
    setAction(`Swiping (${x1},${y1}) → (${x2},${y2})…`);
    try {
      await api(`/api/devices/${d.id}/swipe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ x1, y1, x2, y2, duration: 0.3 }),
      });
      setAction("Swipe complete");
    } catch (err) {
      setAction(`Swipe failed: ${err.message}`, "error");
    }
  }

  function setupScreenInteraction() {
    const img = el("screen-img");
    img.addEventListener("mousemove", (evt) => {
      if (!state.screenLoaded) return;
      const { x, y } = imageToDeviceCoords(evt);
      el("coord-readout").textContent = `x=${x}, y=${y}`;
    });
    img.addEventListener("mousedown", (evt) => {
      if (!state.screenLoaded) return;
      state.dragStart = imageToDeviceCoords(evt);
    });
    img.addEventListener("mouseup", async (evt) => {
      if (!state.dragStart) return;
      const end = imageToDeviceCoords(evt);
      const dx = Math.abs(end.x - state.dragStart.x);
      const dy = Math.abs(end.y - state.dragStart.y);
      if (dx < 10 && dy < 10) {
        await tapAt(state.dragStart.x, state.dragStart.y);
      } else {
        await swipeFromTo(state.dragStart.x, state.dragStart.y, end.x, end.y);
      }
      state.dragStart = null;
      // Always refresh after an action so the screen reflects what just
      // happened on the device — the auto-refresh checkbox only gates
      // the passive polling interval below, not action feedback.
      await captureScreenshot();
    });
  }

  // ---------------------------------------------------------------------
  // Text input
  // ---------------------------------------------------------------------

  async function sendText() {
    const d = selectedDevice();
    const text = el("text-input").value;
    if (!d || !text) return;
    setAction(`Typing "${text}"…`);
    try {
      await api(`/api/devices/${d.id}/text`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      setAction("Text sent");
      el("text-input").value = "";
      await captureScreenshot();
    } catch (err) {
      setAction(`Text failed: ${err.message}`, "error");
    }
  }

  // ---------------------------------------------------------------------
  // Automations
  // ---------------------------------------------------------------------

  const APP_ICON = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="4"/><path d="M8 12h8M12 8v8"/></svg>`;

  const STATUS_LABEL = {
    created: "Idle",
    initialized: "Ready",
    running: "Running",
    paused: "Paused",
    stopped: "Stopped",
    shutdown: "Shut down",
    error: "Error",
  };

  async function refreshAutomationStatus(li, automationId) {
    try {
      const res = await api(`/api/plugins/${automationId}/health`);
      const health = await res.json();
      applyAutomationStatus(li, health);
    } catch {
      // Health fetch failing shouldn't break the automation list.
    }
  }

  function applyAutomationStatus(li, health) {
    const pill = li.querySelector(".status-pill");
    const statusKey = (health.status || "created").toLowerCase();
    pill.textContent = STATUS_LABEL[statusKey] || health.status;
    pill.className = `status-pill st-${statusKey}`;

    li.classList.toggle("running", statusKey === "running" || statusKey === "paused");
    li.classList.toggle("error", statusKey === "error");

    const statusLine = li.querySelector(".automation-status-line");
    if (health.target_app) {
      const launched = health.target_app.launched;
      statusLine.textContent = launched
        ? `${health.target_app.name} is running on device`
        : `${health.target_app.name} not yet launched`;
    } else {
      statusLine.textContent = "";
    }
  }

  function setAutomationBusy(li, busy, label) {
    const statusLine = li.querySelector(".automation-status-line");
    li.querySelectorAll(".automation-actions button").forEach((btn) => (btn.disabled = busy));
    if (busy) {
      statusLine.innerHTML = `<span class="spinner"></span> ${label}`;
    }
  }

  async function refreshPlugins() {
    const res = await api("/api/plugins");
    const plugins = await res.json();
    const list = el("plugin-list");
    list.innerHTML = "";
    el("automation-count").textContent = String(plugins.length);

    if (!plugins.length) {
      list.innerHTML = `<li class="empty-hint">No automations found under games/. Add a plugin folder with a manifest.yaml to see it here.</li>`;
      return;
    }

    for (const p of plugins) {
      const li = document.createElement("li");
      li.className = "automation-card";
      const targetChip = p.target_app
        ? `<div class="target-app-chip">${APP_ICON}<span>${p.target_app.name}</span><span class="pkg">${p.target_app.package}</span></div>`
        : "";
      li.innerHTML = `
        <div class="automation-head">
          <div>
            <span class="name">${p.name}</span>
            <span class="automation-version">v${p.version}</span>
          </div>
          <span class="status-pill st-created">Idle</span>
        </div>
        <div class="automation-desc">${p.description}</div>
        ${targetChip}
        <div class="automation-status-line"></div>
        <div class="automation-actions">
          <button class="btn btn-primary btn-sm run-btn">
            <svg viewBox="0 0 24 24" fill="currentColor"><polygon points="6 3 20 12 6 21 6 3"/></svg>
            Start
          </button>
          <button class="btn btn-outline btn-sm stop-btn">
            <svg viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="12" height="12" rx="1"/></svg>
            Stop
          </button>
        </div>
      `;
      li.querySelector(".run-btn").addEventListener("click", async () => {
        const label = p.target_app ? `Launching ${p.target_app.name}…` : `Starting ${p.name}…`;
        setAction(label);
        setAutomationBusy(li, true, label);
        try {
          await api(`/api/plugins/${p.id}/run`, { method: "POST" });
          setAction(`${p.name} running`);
        } catch (err) {
          setAction(`${p.name} failed to start: ${err.message}`, "error");
        }
        setAutomationBusy(li, false);
        await refreshAutomationStatus(li, p.id);
      });
      li.querySelector(".stop-btn").addEventListener("click", async () => {
        setAutomationBusy(li, true, `Stopping ${p.name}…`);
        try {
          await api(`/api/plugins/${p.id}/stop`, { method: "POST" });
          setAction(`${p.name} stopped`);
        } catch (err) {
          setAction(`${p.name} failed to stop: ${err.message}`, "error");
        }
        setAutomationBusy(li, false);
        await refreshAutomationStatus(li, p.id);
      });
      list.appendChild(li);
      refreshAutomationStatus(li, p.id);
    }
  }

  // ---------------------------------------------------------------------
  // Logs
  // ---------------------------------------------------------------------

  async function pollLogs() {
    try {
      const res = await api(`/api/logs?since=${state.logSince}`);
      const entries = await res.json();
      if (entries.length) {
        const panel = el("log-panel");
        const wasAtBottom = panel.scrollHeight - panel.scrollTop - panel.clientHeight < 24;
        for (const e of entries) {
          const div = document.createElement("div");
          div.className = `log-line ${e.level}`;
          const ts = new Date(e.timestamp * 1000).toLocaleTimeString();
          div.textContent = `[${ts}] ${e.level} ${e.logger}: ${e.message}`;
          panel.appendChild(div);
        }
        if (wasAtBottom) panel.scrollTop = panel.scrollHeight;
        state.logSince += entries.length;
      }
    } catch (err) {
      // Non-fatal: log polling failures shouldn't interrupt the UI.
    }
  }

  // ---------------------------------------------------------------------
  // Theme + zoom + wiring
  // ---------------------------------------------------------------------

  function toggleTheme() {
    const html = document.documentElement;
    const next = html.dataset.theme === "dark" ? "light" : "dark";
    html.dataset.theme = next;
    el("theme-toggle-label").textContent = next === "dark" ? "Light mode" : "Dark mode";
  }

  function applyZoom(delta) {
    state.zoom = Math.max(0.25, Math.min(3, state.zoom + delta));
    el("zoom-level").textContent = `${Math.round(state.zoom * 100)}%`;
    const img = el("screen-img");
    if (img.naturalWidth) img.style.width = `${img.naturalWidth * state.zoom}px`;
  }

  function init() {
    setupScreenInteraction();
    el("refresh-devices").addEventListener("click", refreshDevices);
    el("btn-connect").addEventListener("click", connectSelected);
    el("btn-disconnect").addEventListener("click", disconnectSelected);
    el("btn-screenshot").addEventListener("click", captureScreenshot);
    el("btn-send-text").addEventListener("click", sendText);
    el("text-input").addEventListener("keydown", (evt) => {
      if (evt.key === "Enter") sendText();
    });
    el("theme-toggle").addEventListener("click", toggleTheme);
    el("zoom-in").addEventListener("click", () => applyZoom(0.1));
    el("zoom-out").addEventListener("click", () => applyZoom(-0.1));

    setInterval(pollLogs, 2000);
    setInterval(() => {
      if (el("auto-refresh").checked && state.selectedDeviceId) captureScreenshot();
    }, 3000);

    refreshDevices();
    refreshPlugins();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
