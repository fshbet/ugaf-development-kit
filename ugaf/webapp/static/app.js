(() => {
  "use strict";

  const state = {
    devices: [],
    selectedDeviceId: null,
    zoom: 1.0,
    fitApplied: false,
    logSince: 0,
    dragStart: null,
    screenLoaded: false,
  };

  const el = (id) => document.getElementById(id);

  async function api(path, options) {
    const res = await fetch(path, options);
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      // /connect and action routes report DeviceRecoveryError failures as a
      // structured {stage, reason, detail} object (ADR-020) rather than a
      // plain string, so recovery failures show *which stage* failed.
      const detail = body.detail;
      const message =
        typeof detail === "string" ? detail : detail && (detail.detail || detail.reason) || res.statusText;
      throw new Error(message);
    }
    return res;
  }

  // Single authoritative lifecycle state per device (ADR-020) -- the UI
  // never derives "connected"/"online" from more than one field, so it can
  // never show a contradiction like "Status = Online / Connected = No".
  const STATE_META = {
    discovered: { label: "Discovered", cls: "unknown" },
    starting: { label: "Connecting…", cls: "unknown" },
    waiting_for_adb: { label: "Waiting for ADB…", cls: "unknown" },
    booting: { label: "Booting…", cls: "unknown" },
    initializing: { label: "Initializing…", cls: "unknown" },
    capturing_test_frame: { label: "Verifying…", cls: "unknown" },
    ready: { label: "Ready", cls: "online" },
    disconnected: { label: "Disconnected", cls: "offline" },
    error: { label: "Error", cls: "offline" },
  };

  function stateMeta(d) {
    return STATE_META[d.state] || { label: d.state || "Unknown", cls: "unknown" };
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
    const ready = state.devices.filter((d) => d.state === "ready");
    if (ready.length === 0) {
      setGlobalStatus("No device connected");
    } else if (ready.length === 1) {
      setGlobalStatus(`Connected · ${ready[0].name}`, "success");
    } else {
      setGlobalStatus(`${ready.length} devices connected`, "success");
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
      const meta = stateMeta(d);
      li.innerHTML = `
        <div class="device-icon">${DEVICE_ICON}</div>
        <div class="device-card-body">
          <div class="name">${d.name}</div>
          <div class="meta">
            <span class="status-dot ${meta.cls}"></span>
            <span class="status-text ${meta.cls}">${meta.label}</span>
          </div>
        </div>
      `;
      li.addEventListener("click", () => {
        state.selectedDeviceId = d.id;
        renderDevices();
        renderDeviceInfo();
        refreshAutomationStatus();
        refreshMetrics();
        refreshBootTimeline();
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
    const meta = stateMeta(d);
    dl.innerHTML = `
      <dt>Name</dt><dd>${d.name}</dd>
      <dt>Serial</dt><dd class="mono-text">${d.id}</dd>
      <dt>Status</dt><dd class="status-text ${meta.cls}">${meta.label}</dd>
      <dt>ADB Reachability</dt><dd>${d.status}</dd>
      <dt>Transport</dt><dd>${d.transport.toUpperCase()}</dd>
      <dt>Detail</dt><dd>${d.state_reason || ""}</dd>
    `;
  }

  async function connectSelected() {
    const d = selectedDevice();
    if (!d) return setAction("Select a device first", "error");
    const captureProvider = el("capture-provider").value;
    const windowTitle = el("window-title").value.trim();
    setAction(`Connecting to ${d.name}…`);
    try {
      await api(`/api/devices/${d.id}/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          capture_provider: captureProvider,
          window_title: windowTitle || null,
        }),
      });
      setAction(`Connected to ${d.name}`);
      state.fitApplied = false;
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
    resetMetrics();
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

  // Computes the zoom level that fits the image's natural size exactly inside
  // the viewer's available space (accounting for #screen-wrap's padding/border),
  // so the very first frame of a newly connected device fills the viewer
  // instead of rendering at a fixed 100% that's either way too large (a real
  // phone's native resolution) or too small.
  function fitZoomFor(naturalWidth, naturalHeight) {
    const stage = document.querySelector(".viewer-stage");
    const wrap = el("screen-wrap");
    const stageStyle = getComputedStyle(stage);
    const wrapStyle = getComputedStyle(wrap);
    const paddingX = parseFloat(stageStyle.paddingLeft) + parseFloat(stageStyle.paddingRight);
    const paddingY = parseFloat(stageStyle.paddingTop) + parseFloat(stageStyle.paddingBottom);
    const borderX = parseFloat(wrapStyle.borderLeftWidth) + parseFloat(wrapStyle.borderRightWidth);
    const borderY = parseFloat(wrapStyle.borderTopWidth) + parseFloat(wrapStyle.borderBottomWidth);
    const availWidth = stage.clientWidth - paddingX - borderX;
    const availHeight = stage.clientHeight - paddingY - borderY;
    if (availWidth <= 0 || availHeight <= 0 || !naturalWidth || !naturalHeight) return 1.0;
    return Math.min(availWidth / naturalWidth, availHeight / naturalHeight);
  }

  function applyImageSize(img) {
    if (img.naturalWidth) img.style.width = `${img.naturalWidth * state.zoom}px`;
    el("zoom-level").textContent = `${Math.round(state.zoom * 100)}%`;
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
        if (!state.fitApplied) {
          state.zoom = fitZoomFor(img.naturalWidth, img.naturalHeight);
          state.fitApplied = true;
        }
        applyImageSize(img);
        setScreenVisible(true);
      };
      setAction("Screen captured");
    } catch (err) {
      setAction(`Screenshot failed: ${err.message}`, "error");
    }
  }

  // Returns null instead of Infinity/NaN coordinates when the image element
  // has collapsed to zero width/height (e.g. an unusually short browser
  // viewport) — a real bug found in ATDD acceptance testing where a
  // zero-height rect silently produced `y=Infinity`, which the JSON
  // serializer then turned into `null` on the wire, failing the tap/swipe
  // request with a confusing 422 instead of just not acting on a bad click.
  function imageToDeviceCoords(evt) {
    const img = el("screen-img");
    const rect = img.getBoundingClientRect();
    if (!rect.width || !rect.height) return null;
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
      const coords = imageToDeviceCoords(evt);
      if (!coords) return;
      el("coord-readout").textContent = `x=${coords.x}, y=${coords.y}`;
    });
    img.addEventListener("mousedown", (evt) => {
      if (!state.screenLoaded) return;
      state.dragStart = imageToDeviceCoords(evt);
    });
    img.addEventListener("mouseup", async (evt) => {
      if (!state.dragStart) return;
      const end = imageToDeviceCoords(evt);
      if (!end) {
        state.dragStart = null;
        return;
      }
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
  // Performance metrics
  // ---------------------------------------------------------------------

  function resetMetrics() {
    el("metrics-info").innerHTML = "<dt>Capture FPS</dt><dd>—</dd>";
  }

  async function refreshMetrics() {
    const d = selectedDevice();
    if (!d || !d.connected) return resetMetrics();
    try {
      const res = await api(`/api/devices/${d.id}/metrics`);
      const m = await res.json();
      el("metrics-info").innerHTML = `
        <dt>Capture FPS</dt><dd>${m.capture.fps.toFixed(1)}</dd>
        <dt>Capture latency</dt><dd>${m.capture.avg_ms.toFixed(1)} ms</dd>
        <dt>Input latency</dt><dd>${m.input.avg_ms.toFixed(1)} ms</dd>
      `;
    } catch {
      // A connected device with no capture/input activity yet reports
      // zeroed metrics server-side, not an error — failures here are
      // non-fatal to the rest of the UI either way.
    }
  }

  // Friendly labels for the Boot Timeline panel (ADR-023) -- maps the
  // authoritative DeviceLifecycle states onto the plain-English boot
  // stages a user should see, never raw SDK/state-machine identifiers.
  const BOOT_STAGE_LABELS = {
    validating: "SDK Validated",
    starting: "Connecting",
    waiting_for_adb: "ADB Connected",
    booting: "Android Boot Complete",
    initializing: "Capture Provider Initialized",
    capturing_test_frame: "Screenshot Working",
    testing_input: "Input Working",
    ready: "Device Ready",
    stopping: "Stopping",
    stopped: "Stopped",
    disconnected: "Disconnected",
    error: "Failed",
  };

  async function refreshBootTimeline() {
    const d = selectedDevice();
    const list = el("boot-timeline");
    if (!d) {
      list.innerHTML = `<li class="empty-hint">No device selected.</li>`;
      return;
    }
    try {
      const res = await api(`/api/devices/${d.id}/boot-timeline`);
      const timeline = await res.json();
      if (!timeline.length) {
        list.innerHTML = `<li class="empty-hint">No boot activity recorded yet.</li>`;
        return;
      }
      list.innerHTML = "";
      for (const step of timeline) {
        const failed = step.state === "error";
        const label = BOOT_STAGE_LABELS[step.state] || step.state;
        const li = document.createElement("li");
        li.className = `dependency-item ${failed ? "dep-missing" : "dep-ok"}`;
        li.title = `${step.owner} · +${step.elapsed_seconds.toFixed(1)}s`;
        li.innerHTML = `${failed ? DEP_MISSING_ICON : DEP_OK_ICON}<span class="dep-name">${label}</span><span class="dep-path">${step.reason}</span>`;
        list.appendChild(li);
      }
    } catch {
      list.innerHTML = `<li class="empty-hint">Boot timeline unavailable.</li>`;
    }
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

  const automations = { list: [] };

  // Automation status/run/stop are scoped to the currently selected
  // device (PluginManager's device_id-parametrized instances) so the
  // same automation can run concurrently on several devices, each
  // tracked independently — the dropdown just reflects whichever device
  // is selected right now.
  function deviceQuery() {
    return state.selectedDeviceId ? `?device_id=${encodeURIComponent(state.selectedDeviceId)}` : "";
  }

  function selectedAutomation() {
    const id = el("automation-select").value;
    return automations.list.find((p) => p.id === id) || null;
  }

  function renderAutomationDetails() {
    const p = selectedAutomation();
    const chip = el("automation-target-app");
    if (p && p.target_app) {
      chip.innerHTML = `${APP_ICON}<span>${p.target_app.name}</span><span class="pkg">${p.target_app.package}</span>`;
      chip.classList.remove("hidden");
    } else {
      chip.classList.add("hidden");
    }
    el("automation-desc").textContent = p ? p.description : "";
  }

  async function refreshAutomationStatus() {
    const p = selectedAutomation();
    if (!p) return;
    try {
      const res = await api(`/api/plugins/${p.id}/health${deviceQuery()}`);
      const health = await res.json();
      const statusKey = (health.status || "created").toLowerCase();
      const onDevice = state.selectedDeviceId ? ` on ${state.selectedDeviceId}` : "";
      let text = STATUS_LABEL[statusKey] || health.status;
      if (health.target_app) {
        text += health.target_app.launched
          ? ` — ${health.target_app.name} is running${onDevice}`
          : ` — ${health.target_app.name} not yet launched`;
      }
      const tone =
        statusKey === "running" || statusKey === "paused"
          ? "success"
          : statusKey === "error"
            ? "error"
            : null;
      setAutomationStatus(text, tone);
    } catch {
      // Health fetch failing shouldn't break the rest of the UI.
    }
  }

  function setAutomationStatus(text, tone) {
    const banner = el("automation-status");
    el("automation-status-text").textContent = text;
    banner.className = "status-banner" + (tone ? ` banner-${tone}` : "");
  }

  function setAutomationBusy(busy) {
    el("automation-btn-start").disabled = busy;
    el("automation-btn-stop").disabled = busy;
    el("automation-select").disabled = busy;
  }

  async function startSelectedAutomation() {
    const p = selectedAutomation();
    if (!p) return;
    const onDevice = state.selectedDeviceId ? ` on ${state.selectedDeviceId}` : "";
    const label = p.target_app ? `Launching ${p.target_app.name}${onDevice}…` : `Starting ${p.name}${onDevice}…`;
    setAction(label);
    setAutomationBusy(true);
    setAutomationStatus(label, "busy");
    try {
      await api(`/api/plugins/${p.id}/run${deviceQuery()}`, { method: "POST" });
      setAction(`${p.name} running${onDevice}`);
    } catch (err) {
      setAction(`${p.name} failed to start: ${err.message}`, "error");
    }
    setAutomationBusy(false);
    await refreshAutomationStatus();
  }

  async function stopSelectedAutomation() {
    const p = selectedAutomation();
    if (!p) return;
    setAutomationBusy(true);
    setAutomationStatus(`Stopping ${p.name}…`, "busy");
    try {
      await api(`/api/plugins/${p.id}/stop${deviceQuery()}`, { method: "POST" });
      setAction(`${p.name} stopped`);
    } catch (err) {
      setAction(`${p.name} failed to stop: ${err.message}`, "error");
    }
    setAutomationBusy(false);
    await refreshAutomationStatus();
  }

  async function refreshPlugins() {
    const res = await api("/api/plugins");
    automations.list = await res.json();
    el("automation-count").textContent = String(automations.list.length);

    const select = el("automation-select");
    if (!automations.list.length) {
      select.innerHTML = `<option value="">No automations found under games/</option>`;
      el("automation-btn-start").disabled = true;
      el("automation-btn-stop").disabled = true;
      renderAutomationDetails();
      return;
    }
    el("automation-btn-start").disabled = false;
    el("automation-btn-stop").disabled = false;

    const previous = select.value;
    fillSelect(select, automations.list, { value: (p) => p.id, label: (p) => `${p.name} (v${p.version})` });
    if (previous && automations.list.some((p) => p.id === previous)) select.value = previous;

    renderAutomationDetails();
    await refreshAutomationStatus();
  }

  // ---------------------------------------------------------------------
  // Android Emulator (ugaf.emulator)
  // ---------------------------------------------------------------------

  const emu = {
    manufacturer: null,
    devices: [],
  };

  function setEmulatorStatus(text, tone) {
    const banner = el("emulator-status");
    el("emulator-status-text").textContent = text;
    banner.className = "status-banner" + (tone ? ` banner-${tone}` : "");
  }

  function fillSelect(select, items, { value, label, selected } = {}) {
    select.innerHTML = "";
    for (const item of items) {
      const opt = document.createElement("option");
      opt.value = value ? value(item) : item;
      opt.textContent = label ? label(item) : item;
      if (selected && selected(item)) opt.selected = true;
      select.appendChild(opt);
    }
  }

  const DEP_OK_ICON = `<svg class="dep-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>`;
  const DEP_MISSING_ICON = `<svg class="dep-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

  // Renders the Create-Emulator acceptance checklist (Android Studio, SDK,
  // platform-tools, emulator.exe, sdkmanager, avdmanager) with a checkmark
  // or cross per item and the exact missing-component reason as a tooltip
  // — never a single generic "SDK not found" message.
  function renderDependencies(dependencies) {
    const list = el("emulator-dependencies");
    list.innerHTML = "";
    for (const dep of dependencies) {
      const li = document.createElement("li");
      li.className = `dependency-item ${dep.found ? "dep-ok" : "dep-missing"}`;
      li.title = dep.found ? (dep.path || "") : dep.detail;
      const nameWithVersion = dep.version ? `${dep.name} (${dep.version})` : dep.name;
      li.innerHTML = `${dep.found ? DEP_OK_ICON : DEP_MISSING_ICON}<span class="dep-name">${nameWithVersion}</span>${dep.found && dep.path ? `<span class="dep-path">${dep.path}</span>` : ""}`;
      list.appendChild(li);
    }
  }

  function setEmulatorActionsEnabled(enabled) {
    for (const id of ["emu-btn-create", "emu-btn-start", "emu-btn-stop", "emu-btn-rename", "emu-btn-delete"]) {
      el(id).disabled = !enabled;
    }
  }

  // "Environment Doctor" summary: overall platform health plus how many
  // physical/virtual devices are visible right now, from the same single
  // DeviceManager source `/api/devices` uses -- never a second count.
  function renderPlatformHealthSummary(status) {
    const el_ = el("platform-health-summary");
    const healthy = status.available;
    el_.className = `dependency-item ${healthy ? "dep-ok" : "dep-missing"}`;
    el_.innerHTML = `${healthy ? DEP_OK_ICON : DEP_MISSING_ICON}<span class="dep-name">Overall Platform Health: ${healthy ? "Healthy" : "Needs attention"}</span><span class="dep-path">${status.physical_device_count} physical · ${status.virtual_device_count} virtual device(s) connected</span>`;
  }

  async function initEmulatorPanel() {
    try {
      const res = await api("/api/emulator/status");
      const status = await res.json();
      renderPlatformHealthSummary(status);
      renderDependencies(status.dependencies || []);

      if (!status.available) {
        el("emulator-sdk-warning").textContent = status.error;
        el("emulator-sdk-warning").classList.remove("hidden");
        setEmulatorStatus("Cannot create or run emulators until every dependency above is resolved", "error");
        setEmulatorActionsEnabled(false);
        return;
      }
      el("emulator-sdk-warning").classList.add("hidden");
      setEmulatorActionsEnabled(true);
      await Promise.all([loadManufacturers(), loadPerformanceProfiles(), loadAndroidVersions()]);
      await refreshAvds();
      setEmulatorStatus("Ready");
    } catch (err) {
      setEmulatorStatus(`Emulator Manager error: ${err.message}`, "error");
      setEmulatorActionsEnabled(false);
    }
  }

  async function loadManufacturers() {
    const res = await api("/api/emulator/manufacturers");
    const manufacturers = await res.json();
    fillSelect(el("emu-manufacturer"), manufacturers);
    emu.manufacturer = manufacturers[0] || null;
    await loadDevicesForManufacturer();
  }

  // Same stale-response race as refreshSystemImageStatus below: rapid
  // manufacturer switching must not let an earlier, slower device-list
  // response overwrite the dropdown after a later manufacturer was
  // already selected.
  let deviceListRequestToken = 0;

  async function loadDevicesForManufacturer() {
    const manufacturer = el("emu-manufacturer").value || emu.manufacturer;
    if (!manufacturer) return;
    const token = ++deviceListRequestToken;
    const res = await api(`/api/emulator/manufacturers/${encodeURIComponent(manufacturer)}/devices`);
    const devices = await res.json();
    if (token !== deviceListRequestToken) return; // a newer request has since been issued
    emu.devices = devices;
    fillSelect(el("emu-device"), emu.devices, {
      value: (d) => d.device_name,
      label: (d) => `${d.model} (${d.android_version})`,
    });
    await refreshSystemImageStatus();
  }

  // Manufacturer/device changes can fire in quick succession (a
  // manufacturer switch immediately re-triggers this for its first
  // device). Without a request token, a slower *earlier* response can
  // resolve after a faster *later* one and overwrite it with stale
  // data for whatever is currently selected — exactly the "status
  // doesn't match real state" bug class this project's ATDD process
  // guards against. Only the response from the most recently issued
  // request is ever applied.
  let systemImageRequestToken = 0;

  async function refreshSystemImageStatus() {
    const manufacturer = el("emu-manufacturer").value;
    const deviceName = el("emu-device").value;
    const target = el("emu-system-image-status");
    const token = ++systemImageRequestToken;
    if (!manufacturer || !deviceName) {
      target.innerHTML = "";
      return;
    }
    try {
      const res = await api(
        `/api/emulator/manufacturers/${encodeURIComponent(manufacturer)}/devices/${encodeURIComponent(deviceName)}/system-image`
      );
      const { installed } = await res.json();
      if (token !== systemImageRequestToken) return; // a newer request has since been issued
      target.className = `dependency-item ${installed ? "dep-ok" : "dep-missing"}`;
      target.title = installed
        ? "Required system image is already installed."
        : "Not installed yet — creating this Virtual Device will download it automatically (can take several minutes).";
      target.innerHTML = `${installed ? DEP_OK_ICON : DEP_MISSING_ICON}<span class="dep-name">Required system image</span><span class="dep-path">${installed ? "installed" : "will download on create"}</span>`;
    } catch {
      if (token === systemImageRequestToken) target.innerHTML = "";
    }
  }

  // User-facing labels for performance presets -- the underlying names
  // (mid_range, gaming, ...) are an internal profile-config identifier,
  // not something a user should have to interpret.
  const PERFORMANCE_PROFILE_LABELS = {
    low_end: "Budget Phone",
    mid_range: "Balanced Phone",
    flagship: "High Performance",
    gaming: "Gaming Phone",
  };

  async function loadPerformanceProfiles() {
    const res = await api("/api/emulator/performance-profiles");
    const profiles = await res.json();
    fillSelect(el("emu-performance"), profiles, {
      label: (p) => PERFORMANCE_PROFILE_LABELS[p] || p,
      selected: (p) => p === "mid_range",
    });
  }

  async function loadAndroidVersions() {
    const res = await api("/api/emulator/android-versions");
    const versions = await res.json();
    const byApi = new Map();
    for (const v of versions) {
      if (!byApi.has(v.api_level) || v.installed) byApi.set(v.api_level, v);
    }
    const sorted = [...byApi.values()].sort((a, b) => b.api_level - a.api_level);
    fillSelect(el("emu-android-version"), sorted, {
      value: (v) => v.api_level,
      label: (v) => `${v.version_name || "API " + v.api_level} (API ${v.api_level})${v.installed ? " — installed" : ""}`,
      selected: (v) => v.installed,
    });
  }

  async function refreshAvds() {
    const res = await api("/api/emulator/avds");
    const avds = await res.json();
    fillSelect(el("emu-avd-select"), avds, {
      value: (a) => a.name,
      label: (a) => `${a.name}${a.running ? " (running)" : ""}${a.valid ? "" : " (broken)"}`,
    });
    syncWindowTitleFromAvd();
  }

  // One-click Create Virtual Device (ADR-022): a single click takes the
  // device all the way from "does not exist yet" to READY with a live
  // screen -- create, validate, boot, connect, test-capture, test-tap --
  // with no intermediate Start/Connect actions required.
  async function createAvd() {
    const name = el("emu-avd-name").value.trim();
    if (!name) return setEmulatorStatus("Enter a name for the new Virtual Device first", "error");
    const manufacturer = el("emu-manufacturer").value;
    const deviceName = el("emu-device").value;
    const performanceProfile = el("emu-performance").value;
    setEmulatorStatus(`Creating ${name}… this can take a few minutes on first use`, "busy");
    setEmulatorActionsEnabled(false);
    try {
      const res = await api("/api/emulator/avds/one-click", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          manufacturer,
          device_name: deviceName,
          performance_profile: performanceProfile,
        }),
      });
      const result = await res.json();
      setEmulatorStatus(`${result.avd_name} is ready`, "success");
      await refreshAvds();
      state.selectedDeviceId = result.device_id;
      state.fitApplied = false;
      await refreshDevices();
      await captureScreenshot();
    } catch (err) {
      setEmulatorStatus(`Create failed: ${err.message}`, "error");
    } finally {
      setEmulatorActionsEnabled(true);
    }
  }

  function selectedAvdName() {
    const select = el("emu-avd-select");
    return select.value || null;
  }

  async function startAvd() {
    const name = selectedAvdName();
    if (!name) return setEmulatorStatus("Select a Virtual Device first", "error");
    setEmulatorStatus(`Starting ${name}…`, "busy");
    try {
      await api(`/api/emulator/avds/${encodeURIComponent(name)}/start`, { method: "POST" });
      setEmulatorStatus(`${name} starting — booting Android…`, "success");
      await refreshAvds();
      await refreshDevices();
    } catch (err) {
      setEmulatorStatus(`Start failed: ${err.message}`, "error");
    }
  }

  async function stopAvd() {
    const name = selectedAvdName();
    if (!name) return setEmulatorStatus("Select a Virtual Device first", "error");
    setEmulatorStatus(`Stopping ${name}…`, "busy");
    try {
      await api(`/api/emulator/avds/${encodeURIComponent(name)}/stop`, { method: "POST" });
      setEmulatorStatus(`${name} stopped`, "success");
      await refreshAvds();
      await refreshDevices();
    } catch (err) {
      setEmulatorStatus(`Stop failed: ${err.message}`, "error");
    }
  }

  async function deleteAvd() {
    const name = selectedAvdName();
    if (!name) return setEmulatorStatus("Select a Virtual Device first", "error");
    setEmulatorStatus(`Deleting ${name}…`, "busy");
    try {
      await api(`/api/emulator/avds/${encodeURIComponent(name)}`, { method: "DELETE" });
      setEmulatorStatus(`${name} deleted`, "success");
      await refreshAvds();
    } catch (err) {
      setEmulatorStatus(`Delete failed: ${err.message}`, "error");
    }
  }

  async function renameAvd() {
    const name = selectedAvdName();
    if (!name) return setEmulatorStatus("Select a Virtual Device first", "error");
    const newName = window.prompt(`Rename "${name}" to:`, name);
    if (!newName || newName === name) return;
    setEmulatorStatus(`Renaming ${name} to ${newName}…`, "busy");
    try {
      await api(`/api/emulator/avds/${encodeURIComponent(name)}/rename`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_name: newName }),
      });
      setEmulatorStatus(`Renamed to ${newName}`, "success");
      await refreshAvds();
    } catch (err) {
      setEmulatorStatus(`Rename failed: ${err.message}`, "error");
    }
  }

  // Physical Device implies ADB screen capture (the only transport that
  // makes sense for a real phone); Android Emulator implies direct window
  // capture, since an AVD is an ordinary desktop window UGAF can grab
  // pixels from without going through ADB at all. The dropdown stays a
  // plain <select> so a user can still override this default by hand.
  function setConnectionType(type) {
    const isEmulator = type === "emulator";
    el("emulator-section").classList.toggle("hidden", !isEmulator);
    el("devices-section").classList.toggle("hidden", isEmulator);
    // Always re-check on every switch to Emulator mode, never only once —
    // dependency/AVD state can genuinely change between switches (SDK
    // installed/removed, an AVD created via Android Studio directly), and
    // a cached "first load only" skip would let the panel show stale
    // status instead of the real backend state.
    if (isEmulator) initEmulatorPanel();

    el("capture-provider").value = isEmulator ? "window" : "adb";
    el("window-title").classList.toggle("hidden", !isEmulator);
    if (isEmulator) syncWindowTitleFromAvd();
  }

  function syncWindowTitleFromAvd() {
    const avdName = el("emu-avd-select").value;
    if (avdName) el("window-title").value = avdName;
  }

  function initConnectionType() {
    el("conn-type-physical").addEventListener("change", () => setConnectionType("physical"));
    el("conn-type-emulator").addEventListener("change", () => setConnectionType("emulator"));
    el("emu-manufacturer").addEventListener("change", loadDevicesForManufacturer);
    el("emu-device").addEventListener("change", refreshSystemImageStatus);
    el("emu-avd-select").addEventListener("change", syncWindowTitleFromAvd);
    el("refresh-emulators").addEventListener("click", refreshAvds);
    el("emu-btn-create").addEventListener("click", createAvd);
    el("emu-btn-start").addEventListener("click", startAvd);
    el("emu-btn-stop").addEventListener("click", stopAvd);
    el("emu-btn-rename").addEventListener("click", renameAvd);
    el("emu-btn-delete").addEventListener("click", deleteAvd);
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
    state.zoom = Math.max(0.1, Math.min(3, state.zoom + delta));
    applyImageSize(el("screen-img"));
  }

  function init() {
    setupScreenInteraction();
    initConnectionType();
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
    el("capture-provider").addEventListener("change", (evt) => {
      el("window-title").classList.toggle("hidden", evt.target.value !== "window");
    });
    el("automation-select").addEventListener("change", () => {
      renderAutomationDetails();
      refreshAutomationStatus();
    });
    el("automation-btn-start").addEventListener("click", startSelectedAutomation);
    el("automation-btn-stop").addEventListener("click", stopSelectedAutomation);

    setInterval(pollLogs, 2000);
    setInterval(() => {
      if (el("auto-refresh").checked && state.selectedDeviceId) captureScreenshot();
    }, 3000);
    setInterval(refreshMetrics, 2000);
    setInterval(refreshAutomationStatus, 3000);
    setInterval(refreshBootTimeline, 2000);

    refreshDevices();
    refreshPlugins();
  }

  document.addEventListener("DOMContentLoaded", init);
})();
