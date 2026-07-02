(() => {
  "use strict";

  const state = {
    devices: [],
    selectedDeviceId: null,
    zoom: 1.0,
    logSince: 0,
    autoRefreshTimer: null,
    dragStart: null,
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

  function setAction(text) {
    el("current-action").textContent = text;
  }

  function selectedDevice() {
    return state.devices.find((d) => d.id === state.selectedDeviceId) || null;
  }

  // ---------------------------------------------------------------------
  // Devices
  // ---------------------------------------------------------------------

  async function refreshDevices() {
    const res = await api("/api/devices");
    state.devices = await res.json();
    renderDevices();
    renderDeviceInfo();
  }

  function renderDevices() {
    const list = el("device-list");
    list.innerHTML = "";
    for (const d of state.devices) {
      const li = document.createElement("li");
      li.className = "device-item" + (d.id === state.selectedDeviceId ? " selected" : "");
      li.innerHTML = `
        <div class="name">${d.name} (${d.id})</div>
        <div class="status ${d.status}">${d.status}${d.connected ? " · connected" : ""}</div>
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
    dl.innerHTML = `
      <dt>ID</dt><dd>${d.id}</dd>
      <dt>Name</dt><dd>${d.name}</dd>
      <dt>Status</dt><dd class="status ${d.status}">${d.status}</dd>
      <dt>Transport</dt><dd>${d.transport}</dd>
      <dt>Connected</dt><dd>${d.connected ? "yes" : "no"}</dd>
    `;
  }

  async function connectSelected() {
    const d = selectedDevice();
    if (!d) return setAction("Select a device first");
    setAction(`Connecting to ${d.id}…`);
    try {
      await api(`/api/devices/${d.id}/connect`, { method: "POST" });
      setAction(`Connected to ${d.id}`);
      await refreshDevices();
      await captureScreenshot();
    } catch (err) {
      setAction(`Connect failed: ${err.message}`);
    }
  }

  async function disconnectSelected() {
    const d = selectedDevice();
    if (!d) return;
    await api(`/api/devices/${d.id}/disconnect`, { method: "POST" });
    setAction(`Disconnected from ${d.id}`);
    await refreshDevices();
  }

  // ---------------------------------------------------------------------
  // Screen capture / tap / swipe
  // ---------------------------------------------------------------------

  async function captureScreenshot() {
    const d = selectedDevice();
    if (!d) return setAction("Select and connect a device first");
    setAction("Capturing screen…");
    try {
      const res = await api(`/api/devices/${d.id}/screenshot`);
      const blob = await res.blob();
      const img = el("screen-img");
      img.src = URL.createObjectURL(blob);
      img.onload = () => {
        img.style.width = `${img.naturalWidth * state.zoom}px`;
      };
      setAction("Screen captured");
    } catch (err) {
      setAction(`Screenshot failed: ${err.message}`);
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
      setAction(`Tap failed: ${err.message}`);
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
      setAction(`Swipe failed: ${err.message}`);
    }
  }

  function setupScreenInteraction() {
    const img = el("screen-img");
    img.addEventListener("mousemove", (evt) => {
      const { x, y } = imageToDeviceCoords(evt);
      el("coord-readout").textContent = `x=${x}, y=${y}`;
    });
    img.addEventListener("mousedown", (evt) => {
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
      setAction(`Text failed: ${err.message}`);
    }
  }

  // ---------------------------------------------------------------------
  // Plugins
  // ---------------------------------------------------------------------

  async function refreshPlugins() {
    const res = await api("/api/plugins");
    const plugins = await res.json();
    const list = el("plugin-list");
    list.innerHTML = "";
    for (const p of plugins) {
      const li = document.createElement("li");
      li.className = "plugin-item";
      li.innerHTML = `
        <div class="name">${p.name} <span style="color:var(--muted)">v${p.version}</span></div>
        <div class="desc">${p.description}</div>
        <div class="row">
          <button class="primary run-btn">Run</button>
          <button class="stop-btn">Stop</button>
        </div>
      `;
      li.querySelector(".run-btn").addEventListener("click", async () => {
        setAction(`Running plugin ${p.id}…`);
        try {
          await api(`/api/plugins/${p.id}/run`, { method: "POST" });
          setAction(`Plugin ${p.id} running`);
        } catch (err) {
          setAction(`Plugin run failed: ${err.message}`);
        }
      });
      li.querySelector(".stop-btn").addEventListener("click", async () => {
        try {
          await api(`/api/plugins/${p.id}/stop`, { method: "POST" });
          setAction(`Plugin ${p.id} stopped`);
        } catch (err) {
          setAction(`Plugin stop failed: ${err.message}`);
        }
      });
      list.appendChild(li);
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
        for (const e of entries) {
          const div = document.createElement("div");
          div.className = `log-line ${e.level}`;
          const ts = new Date(e.timestamp * 1000).toLocaleTimeString();
          div.textContent = `[${ts}] ${e.level} ${e.logger}: ${e.message}`;
          panel.appendChild(div);
        }
        panel.scrollTop = panel.scrollHeight;
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
    el("theme-toggle").textContent = next === "dark" ? "Light mode" : "Dark mode";
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
