/* Substrate AI Design Studio — 1. PDN builder + A-Z Functions + Live SVG Viewer + Bottom Jetski Terminal */

(() => {
  "use strict";

  const state = {
    catalog: { categories: [], prompts: [], svgs: [] },
    activeCategory: "core_vddc_sram",
    selectedPromptId: null,
    dispatchMode: "auto",
    sessions: [],
    activeSessionId: null,
    terminals: new Map(),
    expandedDock: false,
    svgs: [],
    selectedSvgPath: null,
    selectedSvgMtimeNs: 0,
    knownMaxSvgMtimeNs: 0,
    autoWatchSvg: true,
    svgZoom: 1,
    svgTx: 0,
    svgTy: 0,
    workspaceInfo: null,
    modalCurPath: "",
    directBusy: false,
  };

  const els = {
    workDirInput: document.getElementById("workDirInput"),
    btnApplyWorkDir: document.getElementById("btnApplyWorkDir"),
    btnBrowseWorkDir: document.getElementById("btnBrowseWorkDir"),
    btnFolderModal: document.getElementById("btnFolderModal"),
    btnResetWorkDir: document.getElementById("btnResetWorkDir"),
    mcmUploadInput: document.getElementById("mcmUploadInput"),
    btnUploadMcm: document.getElementById("btnUploadMcm"),
    btnOutputsModal: document.getElementById("btnOutputsModal"),
    outputsModal: document.getElementById("outputsModal"),
    btnCloseOutputsModal: document.getElementById("btnCloseOutputsModal"),
    outputsModalList: document.getElementById("outputsModalList"),
    workTemplatesMeta: document.getElementById("workTemplatesMeta"),
    folderModal: document.getElementById("folderModal"),
    btnCloseFolderModal: document.getElementById("btnCloseFolderModal"),
    btnModalParent: document.getElementById("btnModalParent"),
    modalPathInput: document.getElementById("modalPathInput"),
    btnModalGo: document.getElementById("btnModalGo"),
    modalDrives: document.getElementById("modalDrives"),
    modalDetectedMcms: document.getElementById("modalDetectedMcms"),
    modalDirList: document.getElementById("modalDirList"),
    btnModalSelectCurrent: document.getElementById("btnModalSelectCurrent"),
    categoryTabs: document.getElementById("categoryTabs"),
    pdnCountLabel: document.getElementById("pdnCountLabel"),
    promptList: document.getElementById("promptList"),
    svgSelect: document.getElementById("svgSelect"),
    btnAutoWatchSvg: document.getElementById("btnAutoWatchSvg"),
    btnRefreshSvg: document.getElementById("btnRefreshSvg"),
    btnZoomOut: document.getElementById("btnZoomOut"),
    btnZoomFit: document.getElementById("btnZoomFit"),
    btnZoomIn: document.getElementById("btnZoomIn"),
    svgZoomLabel: document.getElementById("svgZoomLabel"),
    svgStage: document.getElementById("svgStage"),
    svgPreviewImg: document.getElementById("svgPreviewImg"),
    svgEmptyMsg: document.getElementById("svgEmptyMsg"),
    svgFileLabel: document.getElementById("svgFileLabel"),
    svgWatchStatus: document.getElementById("svgWatchStatus"),
    modeGroup: document.getElementById("modeGroup"),
    composerInput: document.getElementById("composerInput"),
    sendComposerBtn: document.getElementById("sendComposerBtn"),
    sendDirectBtn: document.getElementById("sendDirectBtn"),
    dispatchFeedback: document.getElementById("dispatchFeedback"),
    terminalDock: document.getElementById("terminalDock"),
    dockResizer: document.getElementById("dockResizer"),
    sessionTabs: document.getElementById("sessionTabs"),
    newTabBtn: document.getElementById("newTabBtn"),
    btnLaunchJetski: document.getElementById("btnLaunchJetski"),
    btnLoginOAuth: document.getElementById("btnLoginOAuth"),
    btnLoginLoas: document.getElementById("btnLoginLoas"),
    btnCtrlC: document.getElementById("btnCtrlC"),
    btnClear: document.getElementById("btnClear"),
    btnToggleHeight: document.getElementById("btnToggleHeight"),
    termDimensions: document.getElementById("termDimensions"),
    terminalViewport: document.getElementById("terminalViewport"),
  };

  function escapeHtml(str) {
    return String(str)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function setFeedback(text, isError = false) {
    els.dispatchFeedback.textContent = text;
    els.dispatchFeedback.style.color = isError ? "#f59e0b" : "#98a3b5";
  }

  function renderCategories() {
    els.categoryTabs.innerHTML = state.catalog.categories
      .map((c) => {
        const activeCls = c.id === state.activeCategory ? " active" : "";
        return `<button type="button" class="cat-tab${activeCls}" data-cat="${escapeHtml(c.id)}">${escapeHtml(c.label)}</button>`;
      })
      .join("");
  }

  function renderPrompts() {
    const items = state.catalog.prompts.filter((p) => p.category === state.activeCategory);
    els.pdnCountLabel.textContent = `${items.length} functions`;

    els.promptList.innerHTML = items
      .map((p) => {
        const selectedCls = p.id === state.selectedPromptId ? "selected" : "";
        return `
      <div class="prompt-item ${selectedCls}" role="listitem" data-prompt-id="${escapeHtml(p.id)}">
        <button type="button" class="prompt-main" data-action="select" title="Preview SVG & highlight function">
          <span class="prompt-meta">
            <span class="agent-code">${escapeHtml(p.agent)}</span>
            <span class="layer-span">${escapeHtml(p.layers)}</span>
          </span>
          <span class="prompt-title">${escapeHtml(p.title)}</span>
          <span class="prompt-summary">${escapeHtml(p.summary)}</span>
        </button>
        <div class="prompt-actions">
          <button type="button" class="btn-run-item" data-action="run" title="Run in Jetski terminal">Run</button>
          ${p.cli_command ? '<button type="button" class="btn-stage-item" data-action="direct" title="Run directly in Python/APD without Jetski">Direct</button>' : ""}
          <button type="button" class="btn-stage-item" data-action="stage" title="Edit in Prompt Composer">Edit</button>
        </div>
      </div>`;
      })
      .join("");
  }

  /* ======================== SVG Viewer & File Watcher ======================== */

  function applySvgTransform() {
    els.svgPreviewImg.style.transform = `translate(${state.svgTx}px, ${state.svgTy}px) scale(${state.svgZoom})`;
    els.svgZoomLabel.textContent = `${Math.round(state.svgZoom * 100)}%`;
  }

  function fitSvgToStage() {
    const img = els.svgPreviewImg;
    const sw = els.svgStage.clientWidth;
    const sh = els.svgStage.clientHeight;
    const iw = img.naturalWidth || 1200;
    const ih = img.naturalHeight || 800;
    if (!sw || !sh || !iw || !ih) return;
    const scale = Math.min((sw - 24) / iw, (sh - 24) / ih);
    state.svgZoom = Math.max(0.05, Math.min(scale, 4.0));
    state.svgTx = Math.round((sw - iw * state.svgZoom) / 2);
    state.svgTy = Math.round((sh - ih * state.svgZoom) / 2);
    applySvgTransform();
  }

  function populateSvgSelect() {
    if (!state.svgs.length) {
      const emptyLabel =
        state.workspaceInfo && !state.workspaceInfo.is_custom_dir
          ? "Select a Working Folder (repo SVGs hidden)"
          : "No SVG files in working folder yet";
      els.svgSelect.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
      return;
    }
    els.svgSelect.innerHTML = state.svgs
      .map(
        (s) =>
          `<option value="${escapeHtml(s.rel_path)}">${escapeHtml(s.name)} (${s.size_kb} KB)</option>`
      )
      .join("");
    if (state.selectedSvgPath) {
      els.svgSelect.value = state.selectedSvgPath;
    }
  }

  function loadSvg(relPath, reason = "Loaded") {
    const meta = state.svgs.find((s) => s.rel_path === relPath);
    if (!meta) {
      state.selectedSvgPath = null;
      state.selectedSvgMtimeNs = 0;
      els.svgPreviewImg.style.display = "none";
      els.svgPreviewImg.removeAttribute("src");
      els.svgEmptyMsg.style.display = "flex";
      els.svgEmptyMsg.textContent =
        state.workspaceInfo && state.workspaceInfo.is_custom_dir
          ? "No .svg files created in working space yet — run Stage 1 or a PDN builder function."
          : "Select a Working Folder above — SVG Preview strictly displays SVGs created in working space.";
      els.svgFileLabel.textContent = "No SVG selected";
      els.svgWatchStatus.textContent = reason;
      return;
    }
    state.selectedSvgPath = meta.rel_path;
    state.selectedSvgMtimeNs = meta.mtime_ns;
    els.svgSelect.value = meta.rel_path;
    els.svgEmptyMsg.style.display = "none";
    els.svgPreviewImg.style.display = "block";
    els.svgFileLabel.textContent = `${meta.rel_path} (${meta.size_kb} KB)`;
    const ts = new Date().toLocaleTimeString([], { hour12: false });
    els.svgWatchStatus.textContent = `${reason} at ${ts}`;
    els.svgPreviewImg.onload = () => fitSvgToStage();
    els.svgPreviewImg.src = `/api/svg-file?path=${encodeURIComponent(meta.rel_path)}&v=${meta.mtime_ns}`;
  }

  async function pollSvgUpdates() {
    try {
      const resp = await fetch("/api/svgs");
      if (!resp.ok) return;
      const data = await resp.json();
      const latestList = data.svgs || [];
      if (!latestList.length) {
        if (state.svgs.length || state.selectedSvgPath) {
          state.svgs = [];
          state.knownMaxSvgMtimeNs = 0;
          populateSvgSelect();
          loadSvg("", "No SVGs in working folder");
        }
        return;
      }

      const newest = latestList[0];
      const currentMeta = latestList.find((s) => s.rel_path === state.selectedSvgPath);
      const listChanged =
        latestList.length !== state.svgs.length ||
        !state.svgs[0] ||
        newest.mtime_ns !== state.svgs[0].mtime_ns ||
        newest.rel_path !== state.svgs[0].rel_path;

      state.svgs = latestList;
      if (listChanged) populateSvgSelect();

      const relocList = Array.isArray(data.relocated) ? data.relocated : [];
      const relocTag = relocList.length
        ? `Moved ${relocList.length} agent SVG${relocList.length > 1 ? "s" : ""} -> Working folder`
        : null;

      // Priority 1: Newer/updated SVG or first working-folder SVG appeared & Auto-Watch is enabled
      if (
        (state.autoWatchSvg && newest.mtime_ns > state.knownMaxSvgMtimeNs) ||
        !state.selectedSvgPath ||
        !currentMeta
      ) {
        state.knownMaxSvgMtimeNs = newest.mtime_ns;
        loadSvg(newest.rel_path, relocTag || (currentMeta ? "Auto-updated" : "Working folder SVG"));
        return;
      }
      state.knownMaxSvgMtimeNs = Math.max(state.knownMaxSvgMtimeNs, newest.mtime_ns);

      // Priority 2: Currently selected SVG itself was rewritten on disk
      if (currentMeta && currentMeta.mtime_ns !== state.selectedSvgMtimeNs) {
        loadSvg(currentMeta.rel_path, relocTag || "File changed");
      } else if (relocTag) {
        els.svgWatchStatus.textContent = relocTag;
      }
    } catch {
      // Ignore transient poll errors
    }
  }

  function wireSvgPanZoom() {
    let dragging = false;
    let startX = 0;
    let startY = 0;
    let origTx = 0;
    let origTy = 0;

    els.svgStage.addEventListener("mousedown", (ev) => {
      if (ev.button !== 0) return;
      dragging = true;
      startX = ev.clientX;
      startY = ev.clientY;
      origTx = state.svgTx;
      origTy = state.svgTy;
      els.svgStage.classList.add("panning");
    });

    window.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      state.svgTx = origTx + (ev.clientX - startX);
      state.svgTy = origTy + (ev.clientY - startY);
      applySvgTransform();
    });

    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      els.svgStage.classList.remove("panning");
    });

    els.svgStage.addEventListener(
      "wheel",
      (ev) => {
        ev.preventDefault();
        const rect = els.svgStage.getBoundingClientRect();
        const mx = ev.clientX - rect.left;
        const my = ev.clientY - rect.top;
        const factor = ev.deltaY < 0 ? 1.15 : 1 / 1.15;
        const nextZoom = Math.max(0.03, Math.min(12.0, state.svgZoom * factor));
        const ratio = nextZoom / state.svgZoom;
        state.svgTx = mx - (mx - state.svgTx) * ratio;
        state.svgTy = my - (my - state.svgTy) * ratio;
        state.svgZoom = nextZoom;
        applySvgTransform();
      },
      { passive: false }
    );

    els.svgStage.addEventListener("dblclick", () => fitSvgToStage());

    els.btnZoomIn.addEventListener("click", () => {
      const rect = els.svgStage.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const nextZoom = Math.min(12.0, state.svgZoom * 1.25);
      const r = nextZoom / state.svgZoom;
      state.svgTx = cx - (cx - state.svgTx) * r;
      state.svgTy = cy - (cy - state.svgTy) * r;
      state.svgZoom = nextZoom;
      applySvgTransform();
    });

    els.btnZoomOut.addEventListener("click", () => {
      const rect = els.svgStage.getBoundingClientRect();
      const cx = rect.width / 2;
      const cy = rect.height / 2;
      const nextZoom = Math.max(0.03, state.svgZoom / 1.25);
      const r = nextZoom / state.svgZoom;
      state.svgTx = cx - (cx - state.svgTx) * r;
      state.svgTy = cy - (cy - state.svgTy) * r;
      state.svgZoom = nextZoom;
      applySvgTransform();
    });

    els.btnZoomFit.addEventListener("click", () => fitSvgToStage());

    els.svgSelect.addEventListener("change", () => {
      if (els.svgSelect.value) {
        loadSvg(els.svgSelect.value, "Selected");
      }
    });

    els.btnRefreshSvg.addEventListener("click", () => {
      pollSvgUpdates();
      if (state.selectedSvgPath) {
        loadSvg(state.selectedSvgPath, "Refreshed");
      }
    });

    els.btnAutoWatchSvg.addEventListener("click", () => {
      state.autoWatchSvg = !state.autoWatchSvg;
      els.btnAutoWatchSvg.classList.toggle("active", state.autoWatchSvg);
      els.svgWatchStatus.textContent = state.autoWatchSvg ? "Watching for file changes" : "Auto-Watch paused";
    });
  }

  /* ======================== ConPTY Terminal & Dispatch ======================== */

  function renderSessionTabs() {
    els.sessionTabs.innerHTML = state.sessions
      .map((s) => {
        const active = s.session_id === state.activeSessionId ? "active" : "";
        const closeBtn = state.sessions.length > 1
          ? `<span class="tab-close" data-close="${escapeHtml(s.session_id)}" title="Close tab">&times;</span>`
          : "";
        const label = s.jetski_active ? `${s.title} [Jetski]` : s.title;
        return `<button type="button" class="term-tab ${active}" role="tab" data-sid="${escapeHtml(s.session_id)}"><span>${escapeHtml(label)}</span>${closeBtn}</button>`;
      })
      .join("");
  }

  function mountTerminalInstance(sessionMeta) {
    const sid = sessionMeta.session_id;
    if (state.terminals.has(sid)) return state.terminals.get(sid);

    const container = document.createElement("div");
    container.style.width = "100%";
    container.style.height = "100%";
    container.style.display = "none";
    els.terminalViewport.appendChild(container);

    const term = new window.Terminal({
      cursorBlink: true,
      cursorStyle: "bar",
      fontFamily: '"JetBrains Mono", "Cascadia Code", "Consolas", monospace',
      fontSize: 12,
      lineHeight: 1.24,
      scrollback: 5000,
      theme: {
        background: "#090b0f",
        foreground: "#e6ebf2",
        cursor: "#d89b56",
        cursorAccent: "#090b0f",
        selectionBackground: "rgba(216, 155, 86, 0.28)",
        black: "#12161d",
        red: "#f87171",
        green: "#34d399",
        yellow: "#d89b56",
        blue: "#60a5fa",
        magenta: "#fb7185",
        cyan: "#38bdf8",
        white: "#e6ebf2",
        brightBlack: "#525e70",
        brightRed: "#fca5a5",
        brightGreen: "#6ee7b7",
        brightYellow: "#f3c17a",
        brightBlue: "#93c5fd",
        brightMagenta: "#fda4af",
        brightCyan: "#7dd3fc",
        brightWhite: "#ffffff",
      },
    });

    const fitAddon = new window.FitAddon.FitAddon();
    term.loadAddon(fitAddon);
    term.open(container);

    term.attachCustomKeyEventHandler((ev) => {
      if (ev.type === "keydown" && ev.ctrlKey && ev.key.toLowerCase() === "c" && term.hasSelection()) {
        navigator.clipboard?.writeText(term.getSelection()).catch(() => {});
        return false;
      }
      return true;
    });

    const entry = { term, fitAddon, ws: null, container, status: sessionMeta };
    state.terminals.set(sid, entry);
    connectTerminalWs(sid, entry);
    return entry;
  }

  function connectTerminalWs(sid, entry) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/terminal/${encodeURIComponent(sid)}`);
    entry.ws = ws;

    ws.addEventListener("open", () => {
      fitActiveTerminal();
      const { cols, rows } = entry.term;
      ws.send(JSON.stringify({ type: "resize", cols, rows }));
    });

    ws.addEventListener("message", (ev) => {
      let msg;
      try {
        msg = JSON.parse(ev.data);
      } catch {
        entry.term.write(ev.data);
        return;
      }
      if (msg.type === "output" && typeof msg.data === "string") {
        entry.term.write(msg.data);
      } else if (msg.type === "meta" && msg.status) {
        entry.status = msg.status;
        const idx = state.sessions.findIndex((s) => s.session_id === sid);
        if (idx >= 0) {
          state.sessions[idx] = msg.status;
          renderSessionTabs();
        }
      } else if (msg.type === "exit") {
        entry.term.writeln(`\r\n\x1b[33m[Session exited with code ${msg.code}]\x1b[0m`);
      }
    });

    entry.term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "input", data }));
      }
    });

    entry.term.onResize(({ cols, rows }) => {
      if (sid === state.activeSessionId) {
        els.termDimensions.textContent = `${cols}x${rows}`;
      }
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: "resize", cols, rows }));
      }
    });
  }

  function fitActiveTerminal() {
    const entry = state.terminals.get(state.activeSessionId);
    if (!entry) return;
    requestAnimationFrame(() => {
      try {
        entry.fitAddon.fit();
        els.termDimensions.textContent = `${entry.term.cols}x${entry.term.rows}`;
      } catch {
        // Ignore fit when hidden
      }
    });
  }

  function activateSession(sid) {
    state.activeSessionId = sid;
    for (const [id, entry] of state.terminals.entries()) {
      entry.container.style.display = id === sid ? "block" : "none";
    }
    renderSessionTabs();
    fitActiveTerminal();
    state.terminals.get(sid)?.term.focus();
  }

  async function createNewSession(title = null) {
    const resp = await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title, cols: 140, rows: 6 }),
    });
    const data = await resp.json();
    const meta = data.session;
    state.sessions.push(meta);
    mountTerminalInstance(meta);
    activateSession(meta.session_id);
  }

  async function closeSession(sid) {
    if (state.sessions.length <= 1) return;
    await fetch(`/api/sessions/${encodeURIComponent(sid)}`, { method: "DELETE" });
    const entry = state.terminals.get(sid);
    if (entry) {
      try {
        entry.ws?.close();
        entry.term.dispose();
        entry.container.remove();
      } catch {
        // Ignore
      }
      state.terminals.delete(sid);
    }
    state.sessions = state.sessions.filter((s) => s.session_id !== sid);
    if (state.activeSessionId === sid && state.sessions.length) {
      activateSession(state.sessions[0].session_id);
    } else {
      renderSessionTabs();
    }
  }

  async function dispatchToTerminal(promptText, cliCommand = null, modeOverride = null, retried = false) {
    let sid = state.activeSessionId;
    if (!sid) {
      await createNewSession("Jetski Terminal 1");
      sid = state.activeSessionId;
    }
    const mode = modeOverride || state.dispatchMode;
    try {
      const resp = await fetch(`/api/sessions/${encodeURIComponent(sid)}/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: promptText,
          mode,
          model: "",
          cli_command: cliCommand,
        }),
      });
      if (resp.status === 404 && !retried) {
        state.sessions = [];
        state.terminals.forEach((e) => { try { e.ws?.close(); e.term.dispose(); e.container.remove(); } catch {} });
        state.terminals.clear();
        await createNewSession("Jetski Terminal 1");
        return dispatchToTerminal(promptText, cliCommand, modeOverride, true);
      }
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        setFeedback(data.error || "Dispatch failed", true);
        return;
      }
      setFeedback(`Sent (${data.effective_mode})`);
      state.terminals.get(sid)?.term.focus();
    } catch (err) {
      setFeedback(`Error: ${err.message}`, true);
    }
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes < 1024) return `${bytes || 0} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
  }

  function appendDirectTerminalLog(text) {
    const entry = state.terminals.get(state.activeSessionId);
    if (entry?.term && text) {
      entry.term.write(`\r\n${String(text).replace(/\r?\n/g, "\r\n")}\r\n`);
    }
  }

  async function runDirectPrompt(item) {
    if (!item || !item.cli_command) {
      setFeedback("Select a prompt function with a direct CLI command first", true);
      return;
    }
    if (state.directBusy) {
      setFeedback("A direct execution is already running...", true);
      return;
    }
    state.directBusy = true;
    if (els.sendDirectBtn) els.sendDirectBtn.disabled = true;
    setFeedback(`Running ${item.code} directly in Python/APD...`);
    appendDirectTerminalLog(`[Direct] Running ${item.code}: ${item.title}`);

    try {
      const resp = await fetch("/api/direct/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt_id: item.id, implement_mcm: false }),
      });
      const data = await resp.json();
      if (data.stdout) appendDirectTerminalLog(data.stdout.trimEnd());
      if (data.stderr) appendDirectTerminalLog(`[stderr]\n${data.stderr.trimEnd()}`);
      await pollSvgUpdates();

      if (!resp.ok || !data.ok) {
        setFeedback(`Direct run failed (rc=${data.returncode ?? resp.status})`, true);
        return;
      }
      const moved = Array.isArray(data.relocated) ? data.relocated.length : 0;
      const svgCount = Array.isArray(data.svgs) ? data.svgs.length : 0;
      setFeedback(`Direct run complete (${item.code}) — ${svgCount} SVGs ready${moved ? `, synced ${moved} files` : ""}`);
    } catch (err) {
      appendDirectTerminalLog(`[Direct error] ${err.message}`);
      setFeedback(`Direct run error: ${err.message}`, true);
    } finally {
      state.directBusy = false;
      if (els.sendDirectBtn) els.sendDirectBtn.disabled = false;
    }
  }

  async function uploadSelectedMcm(file) {
    if (!file) return;
    setFeedback(`Uploading ${file.name} (${formatBytes(file.size)}) to MCM_template/...`);
    if (els.btnUploadMcm) els.btnUploadMcm.disabled = true;
    try {
      const form = new FormData();
      form.append("file", file, file.name);
      const resp = await fetch("/api/workspace/upload-mcm", {
        method: "POST",
        body: form,
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        setFeedback(data.error || "MCM upload failed", true);
        return;
      }
      if (data.workspace) {
        applyWorkspaceUI(data.workspace);
      }
      appendDirectTerminalLog(`[Upload] Saved ${data.rel_path} (${formatBytes(data.size)})`);
      setFeedback(`Uploaded ${data.filename} (${formatBytes(data.size)}) -> MCM_template/`);
    } catch (err) {
      setFeedback(`Upload error: ${err.message}`, true);
    } finally {
      if (els.btnUploadMcm) els.btnUploadMcm.disabled = false;
      if (els.mcmUploadInput) els.mcmUploadInput.value = "";
    }
  }

  async function openOutputsModal() {
    if (!els.outputsModal || !els.outputsModalList) return;
    els.outputsModal.classList.add("open");
    els.outputsModal.setAttribute("aria-hidden", "false");
    els.outputsModalList.innerHTML = `<div class="modal-detected-mcms">Loading workspace files...</div>`;
    try {
      const resp = await fetch("/api/workspace/downloads");
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        els.outputsModalList.innerHTML = `<div class="modal-detected-mcms">Failed to list outputs: ${escapeHtml(data.error || resp.status)}</div>`;
        return;
      }
      const files = data.files || [];
      if (!files.length) {
        els.outputsModalList.innerHTML = `<div class="modal-detected-mcms">No generated files (.mcm, .svg, .csv, .txt) found yet.</div>`;
        return;
      }
      els.outputsModalList.innerHTML = files
        .map((f) => {
          const href = `/api/workspace/download?path=${encodeURIComponent(f.rel_path)}`;
          return `<a class="modal-dir-row" href="${href}" download="${escapeHtml(f.name)}"><span>${escapeHtml(f.rel_path)}</span><span>${escapeHtml(formatBytes(f.size))}</span></a>`;
        })
        .join("");
    } catch (err) {
      els.outputsModalList.innerHTML = `<div class="modal-detected-mcms">Error: ${escapeHtml(err.message)}</div>`;
    }
  }

  async function triggerTerminalAction(action, retried = false) {
    let sid = state.activeSessionId;
    if (!sid) {
      await createNewSession("Jetski Terminal 1");
      sid = state.activeSessionId;
    }
    const resp = await fetch(`/api/sessions/${encodeURIComponent(sid)}/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, model: "" }),
    });
    if (resp.status === 404 && !retried) {
      state.sessions = [];
      state.terminals.forEach((e) => { try { e.ws?.close(); e.term.dispose(); e.container.remove(); } catch {} });
      state.terminals.clear();
      await createNewSession("Jetski Terminal 1");
      return triggerTerminalAction(action, true);
    }
    state.terminals.get(sid)?.term.focus();
  }

  function applyWorkspaceUI(wsInfo, updatedSvgs = null) {
    if (!wsInfo) return;
    state.workspaceInfo = wsInfo;
    els.workDirInput.value = wsInfo.working_dir;
    els.btnResetWorkDir.style.display = wsInfo.is_custom_dir ? "inline-flex" : "none";
    const tpls = wsInfo.origin_templates && wsInfo.origin_templates.length
      ? wsInfo.origin_templates
      : (wsInfo.working_templates || []);
    if (wsInfo.is_custom_dir) {
      const mcmLabel = tpls.length
        ? `${tpls.length} .mcm (${tpls[0].rel_path || tpls[0].name})`
        : (wsInfo.mcm_template_dir ? "MCM_template (0 .mcm)" : (wsInfo.has_master_tag ? "master.tag found" : "Custom Folder"));
      els.workTemplatesMeta.textContent = mcmLabel;
    } else {
      els.workTemplatesMeta.textContent = `Repo Default (${tpls.length} .mcm)`;
    }
    if (Array.isArray(updatedSvgs)) {
      state.svgs = updatedSvgs;
      state.knownMaxSvgMtimeNs = updatedSvgs.length ? updatedSvgs[0].mtime_ns : 0;
      if (!updatedSvgs.some((s) => s.rel_path === state.selectedSvgPath)) {
        state.selectedSvgPath = null;
        state.selectedSvgMtimeNs = 0;
      }
      populateSvgSelect();
      if (updatedSvgs.length) {
        loadSvg(updatedSvgs[0].rel_path, "Working folder SVG");
      } else {
        loadSvg(
          "",
          wsInfo && !wsInfo.is_custom_dir
            ? "Select Working Folder"
            : "No SVGs in working space"
        );
      }
    }
  }

  async function setWorkingFolder(pathStr) {
    const clean = (pathStr || "").trim();
    if (!clean) return;
    try {
      const resp = await fetch("/api/workspace/select", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: clean }),
      });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        setFeedback(data.error || "Invalid folder path", true);
        return;
      }
      applyWorkspaceUI(data.workspace, data.svgs);
      setFeedback(`Working folder set: ${data.workspace.working_dir}`);
    } catch (err) {
      setFeedback(`Folder update error: ${err.message}`, true);
    }
  }

  async function openNativeBrowseFolder() {
    els.btnBrowseWorkDir.disabled = true;
    els.btnBrowseWorkDir.textContent = "Opening...";
    try {
      const resp = await fetch("/api/workspace/browse", { method: "POST" });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        setFeedback(data.error || "Folder picker unavailable — use Folders or paste path", true);
        return;
      }
      if (!data.cancelled && data.workspace) {
        applyWorkspaceUI(data.workspace, data.svgs);
        setFeedback(`Working folder set: ${data.workspace.working_dir}`);
      }
    } catch (err) {
      setFeedback(`Browse failed: ${err.message}`, true);
    } finally {
      els.btnBrowseWorkDir.disabled = false;
      els.btnBrowseWorkDir.textContent = "Browse...";
    }
  }

  async function loadFolderModalDir(dirPath = "") {
    const q = dirPath ? `?path=${encodeURIComponent(dirPath)}` : "";
    const resp = await fetch(`/api/workspace/ls${q}`);
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      setFeedback(data.error || "Cannot list directory", true);
      return;
    }
    state.modalCurPath = data.path;
    els.modalPathInput.value = data.path;
    els.btnModalParent.disabled = !data.parent;
    els.btnModalParent.onclick = () => data.parent && loadFolderModalDir(data.parent);

    els.modalDrives.innerHTML = (data.drives || [])
      .map((drv) => `<button type="button" class="btn-ghost" data-drv="${escapeHtml(drv)}">${escapeHtml(drv)}</button>`)
      .join("");

    const mcmList = data.mcm_files || [];
    const tagTxt = data.has_master_tag ? "master.tag + " : "";
    els.modalDetectedMcms.textContent = mcmList.length
      ? `${tagTxt}MCM templates (${mcmList.length}): ${mcmList.slice(0, 6).join(", ")}`
      : (data.has_mcm_template_dir
          ? "MCM_template subfolder found (no .mcm inside yet)"
          : (data.has_master_tag ? "master.tag found in this folder" : "No .mcm in folder or MCM_template/"));

    els.modalDirList.innerHTML = (data.dirs || [])
      .map((d) => `<button type="button" class="modal-dir-row" data-path="${escapeHtml(d.path)}"><span>[DIR] ${escapeHtml(d.name)}</span></button>`)
      .join("") || `<div class="empty-state">No subdirectories</div>`;
  }

  function wireFolderControls() {
    els.btnApplyWorkDir.addEventListener("click", () => setWorkingFolder(els.workDirInput.value));
    els.workDirInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        setWorkingFolder(els.workDirInput.value);
      }
    });
    els.btnBrowseWorkDir.addEventListener("click", () => openNativeBrowseFolder());
    els.btnResetWorkDir.addEventListener("click", () => {
      if (state.workspaceInfo?.agent_root) {
        setWorkingFolder(state.workspaceInfo.agent_root);
      }
    });

    const toggleModal = (open) => {
      els.folderModal.classList.toggle("open", open);
      els.folderModal.setAttribute("aria-hidden", String(!open));
    };
    els.btnFolderModal.addEventListener("click", () => {
      toggleModal(true);
      loadFolderModalDir(els.workDirInput.value || "");
    });
    els.btnCloseFolderModal.addEventListener("click", () => toggleModal(false));
    els.btnModalGo.addEventListener("click", () => loadFolderModalDir(els.modalPathInput.value));
    els.modalPathInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        loadFolderModalDir(els.modalPathInput.value);
      }
    });
    els.modalDrives.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-drv]");
      if (btn) loadFolderModalDir(btn.dataset.drv);
    });
    els.modalDirList.addEventListener("click", (ev) => {
      const row = ev.target.closest("[data-path]");
      if (row) loadFolderModalDir(row.dataset.path);
    });
    els.btnModalSelectCurrent.addEventListener("click", async () => {
      await setWorkingFolder(state.modalCurPath || els.modalPathInput.value);
      toggleModal(false);
    });
  }

  function wireDockResize() {
    let dragging = false;
    let startY = 0;
    let startH = 0;

    els.dockResizer.addEventListener("mousedown", (ev) => {
      dragging = true;
      startY = ev.clientY;
      startH = els.terminalDock.getBoundingClientRect().height;
      els.dockResizer.classList.add("dragging");
      ev.preventDefault();
    });

    window.addEventListener("mousemove", (ev) => {
      if (!dragging) return;
      const delta = startY - ev.clientY;
      const nextH = Math.max(96, Math.min(window.innerHeight * 0.72, startH + delta));
      els.terminalDock.style.height = `${Math.round(nextH)}px`;
      fitActiveTerminal();
    });

    window.addEventListener("mouseup", () => {
      if (!dragging) return;
      dragging = false;
      els.dockResizer.classList.remove("dragging");
      fitActiveTerminal();
    });

    els.btnToggleHeight.addEventListener("click", () => {
      state.expandedDock = !state.expandedDock;
      els.terminalDock.style.height = state.expandedDock ? "42vh" : "12.5vh";
      els.btnToggleHeight.textContent = state.expandedDock ? "Compact 1/8" : "Expand";
      fitActiveTerminal();
      state.terminals.get(state.activeSessionId)?.term.focus();
    });
  }

  function wireEvents() {
    els.categoryTabs.addEventListener("click", (ev) => {
      const tab = ev.target.closest("[data-cat]");
      if (!tab) return;
      state.activeCategory = tab.dataset.cat;
      renderCategories();
      renderPrompts();
    });

    els.promptList.addEventListener("click", (ev) => {
      const actionEl = ev.target.closest("[data-action]");
      const itemEl = ev.target.closest("[data-prompt-id]");
      if (!actionEl || !itemEl) return;
      const item = state.catalog.prompts.find((p) => p.id === itemEl.dataset.promptId);
      if (!item) return;

      state.selectedPromptId = item.id;
      renderPrompts();
      if (item.default_svg) {
        const matchExact = state.svgs.find((s) => s.rel_path === item.default_svg);
        const defName = item.default_svg.split("/").pop();
        const matchSvg = matchExact || state.svgs.find((s) => s.name === defName);
        if (matchSvg) {
          loadSvg(matchSvg.rel_path, `${item.code}. SVG`);
        }
      }

      if (actionEl.dataset.action === "stage") {
        els.composerInput.value = item.prompt;
        els.composerInput.focus();
        setFeedback(`Loaded "${item.code}." into Prompt Composer`);
      } else if (actionEl.dataset.action === "direct") {
        runDirectPrompt(item);
      } else if (actionEl.dataset.action === "run") {
        dispatchToTerminal(item.prompt, item.cli_command || null);
      }
    });

    els.modeGroup.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-mode]");
      if (!btn) return;
      state.dispatchMode = btn.dataset.mode;
      for (const el of els.modeGroup.querySelectorAll(".mode-pill")) {
        el.classList.toggle("active", el === btn);
      }
    });

    els.sendComposerBtn.addEventListener("click", () => {
      const txt = els.composerInput.value.trim();
      if (!txt) {
        setFeedback("Enter a prompt first", true);
        return;
      }
      dispatchToTerminal(txt);
    });

    if (els.sendDirectBtn) {
      els.sendDirectBtn.addEventListener("click", () => {
        const item = state.catalog.prompts.find((p) => p.id === state.selectedPromptId);
        runDirectPrompt(item);
      });
    }

    if (els.btnUploadMcm && els.mcmUploadInput) {
      els.btnUploadMcm.addEventListener("click", () => els.mcmUploadInput.click());
      els.mcmUploadInput.addEventListener("change", () => {
        const file = els.mcmUploadInput.files && els.mcmUploadInput.files[0];
        if (file) uploadSelectedMcm(file);
      });
    }

    if (els.btnOutputsModal) {
      els.btnOutputsModal.addEventListener("click", () => openOutputsModal());
    }

    if (els.btnCloseOutputsModal && els.outputsModal) {
      els.btnCloseOutputsModal.addEventListener("click", () => {
        els.outputsModal.classList.remove("open");
        els.outputsModal.setAttribute("aria-hidden", "true");
      });
    }

    els.composerInput.addEventListener("keydown", (ev) => {
      if (ev.ctrlKey && ev.key === "Enter") {
        ev.preventDefault();
        els.sendComposerBtn.click();
      }
    });

    els.sessionTabs.addEventListener("click", (ev) => {
      const closeEl = ev.target.closest("[data-close]");
      if (closeEl) {
        ev.stopPropagation();
        closeSession(closeEl.dataset.close);
        return;
      }
      const tabEl = ev.target.closest("[data-sid]");
      if (tabEl) {
        activateSession(tabEl.dataset.sid);
      }
    });

    els.newTabBtn.addEventListener("click", () => createNewSession());
    els.btnLaunchJetski.addEventListener("click", () => triggerTerminalAction("launch_jetski"));
    els.btnLoginOAuth.addEventListener("click", () => triggerTerminalAction("login_jetski_oauth"));
    els.btnLoginLoas.addEventListener("click", () => triggerTerminalAction("login_jetski_loas"));
    els.btnCtrlC.addEventListener("click", () => triggerTerminalAction("ctrl_c"));
    els.btnClear.addEventListener("click", () => triggerTerminalAction("clear"));

    wireFolderControls();
    wireSvgPanZoom();
    wireDockResize();

    const termObserver = new ResizeObserver(() => fitActiveTerminal());
    termObserver.observe(els.terminalViewport);
    const svgObserver = new ResizeObserver(() => fitSvgToStage());
    svgObserver.observe(els.svgStage);
  }

  async function init() {
    wireEvents();

    const [healthResp, catResp, sessResp] = await Promise.all([
      fetch("/api/health").then((r) => r.json()),
      fetch("/api/catalog").then((r) => r.json()),
      fetch("/api/sessions").then((r) => r.json()),
    ]);

    if (healthResp?.os_name && healthResp.os_name !== "nt" && els.btnBrowseWorkDir) {
      els.btnBrowseWorkDir.style.display = "none";
    }

    state.catalog = catResp;
    if (
      state.catalog.categories &&
      state.catalog.categories.length &&
      !state.catalog.categories.some((c) => c.id === state.activeCategory)
    ) {
      state.activeCategory = state.catalog.categories[0].id;
    }
    state.svgs = catResp.svgs || [];
    if (state.svgs.length) {
      state.knownMaxSvgMtimeNs = state.svgs[0].mtime_ns;
    }
    if (catResp.workspace) {
      applyWorkspaceUI(catResp.workspace);
    }

    renderCategories();
    renderPrompts();
    populateSvgSelect();

    if (state.svgs.length) {
      loadSvg(state.svgs[0].rel_path, "Working folder SVG");
    } else {
      loadSvg(
        "",
        state.workspaceInfo && !state.workspaceInfo.is_custom_dir
          ? "Select Working Folder"
          : "No SVGs in working space"
      );
    }

    state.sessions = sessResp.sessions || [];
    if (state.sessions.length) {
      for (const s of state.sessions) mountTerminalInstance(s);
      activateSession(state.sessions[0].session_id);
    } else {
      await createNewSession("Jetski Terminal 1");
    }

    setInterval(pollSvgUpdates, 2000);
  }

  init().catch((err) => {
    setFeedback(`Init failed: ${err.message}`, true);
  });
})();
