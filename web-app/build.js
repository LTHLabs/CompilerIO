import { store } from './state.js';
import { api } from './api.js';
import { editor } from './editor.js';
import { library } from './library.js';
import { formatDuration, formatBytes } from './state.js';

const build = {
  compileBtn: null,
  statusEl: null,
  spinner: null,
  timerEl: null,
  infoEl: null,
  resultEl: null,
  resultIcon: null,
  resultTitle: null,
  resultDetails: null,
  resultActions: null,
  pollInterval: null,
  buildStartTime: null,
  firmwareBlob: null,

  init() {
    this.compileBtn = document.getElementById('compileBtn');
    this.statusEl = document.getElementById('buildStatus');
    this.spinner = document.getElementById('buildSpinner');
    this.timerEl = document.getElementById('buildTimer');
    this.infoEl = document.getElementById('buildInfo');
    this.resultEl = document.getElementById('buildResult');
    this.resultIcon = document.getElementById('resultIcon');
    this.resultTitle = document.getElementById('resultTitle');
    this.resultDetails = document.getElementById('resultDetails');
    this.resultActions = document.getElementById('resultActions');

    this.compileBtn.addEventListener('click', () => this.startBuild());

    store.subscribe((state) => {
      if (state.appState === store.AppState.READY) {
        this.compileBtn.disabled = false;
      } else if (state.appState === store.AppState.BUILDING) {
        this.compileBtn.disabled = true;
      }
    });
  },

  async startBuild() {
    const code = editor.getCode().trim();
    if (!code) {
      editor.focus();
      return;
    }

    const { token, selectedBoard, selectedFramework, selectedLibDeps } = store.getState();
    if (!token) {
      alert('Not connected to Local Agent');
      return;
    }

    const finalDetected = library.detectIncludes(code);
    store.set({ detectedLibraries: finalDetected });

    this.resetUI();
    this.showBuilding();
    store.set({ appState: store.AppState.BUILDING, lastError: null });

    try {
      const libDeps = selectedLibDeps.map(dep => dep.platformioName);
      const response = await api.build(code, libDeps, selectedBoard, selectedFramework);
      const buildId = response.build_id;
      store.set({ currentBuildId: buildId, buildStartTime: Date.now() });
      this.startPolling(buildId, token);
    } catch (err) {
      if (err.message === 'AUTH_REQUIRED') {
        this.handleAuthError();
      } else {
        this.showError(`Build failed to start: ${err.message}`);
      }
    }
  },

  showBuilding() {
    this.statusEl.hidden = false;
    this.spinner.hidden = false;
    this.timerEl.hidden = false;
    this.infoEl.textContent = 'Compiling...';
    this.resultEl.hidden = true;
    this.buildStartTime = Date.now();
    this.updateTimer();
  },

  updateTimer() {
    if (!this.buildStartTime) return;
    const elapsed = Math.floor((Date.now() - this.buildStartTime) / 1000);
    this.timerEl.textContent = formatDuration(elapsed);
    requestAnimationFrame(() => this.updateTimer());
  },

  startPolling(buildId, token) {
    this.pollInterval = setInterval(async () => {
      try {
        const status = await api.getBuildStatus(buildId, token);
        if (status.status === 'SUCCEEDED') {
          this.handleSuccess(status, token);
        } else if (status.status === 'FAILED') {
          this.handleFailure(status, token);
        }
      } catch (err) {
        if (err.message === 'AUTH_REQUIRED') {
          this.handleAuthError();
        }
      }
    }, 2000);
  },

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  },

  async handleSuccess(status, token) {
    this.stopPolling();
    const duration = status.duration_seconds;
    store.set({
      appState: store.AppState.SUCCESS,
      buildDuration: duration
    });

    this.spinner.hidden = true;
    this.infoEl.textContent = 'Build completed';
    this.timerEl.textContent = formatDuration(duration);

    let firmwareSize = null;
    try {
      const blob = await api.downloadFirmware(status.build_id, 'wokwi-firmware.bin', token);
      firmwareSize = blob.size;
      this.firmwareBlob = blob;
    } catch (err) {
      console.error('Firmware download failed:', err);
    }

    this.showSuccessUI(duration, firmwareSize);
  },

  async handleFailure(status, token) {
    this.stopPolling();
    const duration = status.duration_seconds;
    store.set({
      appState: store.AppState.FAILED,
      buildDuration: duration,
      lastError: status.error
    });

    this.spinner.hidden = true;
    this.infoEl.textContent = 'Build failed';
    this.timerEl.textContent = formatDuration(duration);

    this.showErrorUI(status.error, duration);

    let log = '';
    try {
      log = await api.getBuildLog(status.build_id, token);
    } catch (err) {
      log = 'Failed to fetch compiler log';
    }
    store.set({ logContent: log });
  },

  showSuccessUI(duration, firmwareSize) {
    this.resultEl.hidden = false;
    this.resultIcon.className = 'result-icon success';
    this.resultIcon.textContent = '✓';
    this.resultTitle.textContent = 'Build Successful';

    this.resultDetails.innerHTML = `
      <div class="result-detail">
        <span class="result-detail-label">Build Time</span>
        <span class="result-detail-value">${formatDuration(duration)}</span>
      </div>
      <div class="result-detail">
        <span class="result-detail-label">Firmware Size</span>
        <span class="result-detail-value">${firmwareSize ? formatBytes(firmwareSize) : 'Unknown'}</span>
      </div>
    `;

    this.resultActions.innerHTML = `
      <button id="downloadFirmwareBtn" class="btn btn-primary">Download wokwi-firmware.bin</button>
      <button id="showLogBtn" class="btn btn-secondary">Show Compiler Log</button>
    `;

    document.getElementById('downloadFirmwareBtn').addEventListener('click', () => this.downloadFirmware());
    document.getElementById('showLogBtn').addEventListener('click', () => this.showLog());
  },

  showErrorUI(error, duration) {
    this.resultEl.hidden = false;
    this.resultIcon.className = 'result-icon error';
    this.resultIcon.textContent = '✕';
    this.resultTitle.textContent = 'Build Failed';

    this.resultDetails.innerHTML = `
      <div class="result-detail">
        <span class="result-detail-label">Build Time</span>
        <span class="result-detail-value">${formatDuration(duration)}</span>
      </div>
      <div class="result-detail">
        <span class="result-detail-label">Error</span>
        <span class="result-detail-value" style="color: var(--error); font-family: var(--font-mono);">${error || 'Unknown error'}</span>
      </div>
    `;

    this.resultActions.innerHTML = `
      <button id="showLogBtn" class="btn btn-primary">Show Compiler Log</button>
      <button id="retryBuildBtn" class="btn btn-secondary">Try Again</button>
    `;

    document.getElementById('showLogBtn').addEventListener('click', () => this.showLog());
    document.getElementById('retryBuildBtn').addEventListener('click', () => this.startBuild());
  },

  async downloadFirmware() {
    const { currentBuildId, token } = store.getState();
    if (!currentBuildId) return;

    try {
      let blob = this.firmwareBlob;
      if (!blob) {
        blob = await api.downloadFirmware(currentBuildId, 'wokwi-firmware.bin', token);
      }
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'wokwi-firmware.bin';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(`Download failed: ${err.message}`);
    }
  },

  showLog() {
    import('./logger.js').then(({ logger }) => logger.show(store.getState().logContent));
  },

  handleAuthError() {
    this.stopPolling();
    store.set({ token: null, appState: store.AppState.PAIRING_REQUIRED });
    this.resetUI();
  },

  showError(message) {
    this.stopPolling();
    this.spinner.hidden = true;
    this.infoEl.textContent = message;
    this.infoEl.style.color = 'var(--error)';
    store.set({ appState: store.AppState.FAILED, lastError: message });
  },

  resetUI() {
    this.stopPolling();
    this.buildStartTime = null;
    this.firmwareBlob = null;
    this.spinner.hidden = true;
    this.timerEl.hidden = true;
    this.timerEl.textContent = '00:00';
    this.infoEl.textContent = '';
    this.infoEl.style.color = '';
    this.resultEl.hidden = true;
    this.compileBtn.disabled = false;
  }
};

export { build };
