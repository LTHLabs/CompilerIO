const AppState = {
  DISCONNECTED: 'disconnected',
  CHECKING: 'checking',
  PAIRING_REQUIRED: 'pairing_required',
  PREPARING: 'preparing',
  READY: 'ready',
  BUILDING: 'building',
  SUCCESS: 'success',
  FAILED: 'failed'
};

const initialState = {
  appState: AppState.DISCONNECTED,
  token: null,
  agentUrl: 'http://127.0.0.1:8765',
  boards: [],
  frameworks: [],
  selectedBoard: 'esp32dev',
  selectedFramework: 'arduino',
  currentBuildId: null,
  buildStartTime: null,
  buildDuration: null,
  lastError: null,
  logContent: '',
  detectedLibraries: [],
  selectedLibDeps: [],
};

const listeners = new Set();

const state = { ...initialState };

function emit() {
  listeners.forEach(fn => fn(state));
}

export const store = {
  getState() {
    return { ...state };
  },

  get(appState) {
    return state[appState];
  },

  set(partial) {
    Object.assign(state, partial);
    emit();
  },

  reset() {
    Object.assign(state, initialState);
    emit();
  },

  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  AppState
};

export function formatDuration(seconds) {
  if (seconds == null) return '--:--';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
}

export function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export { AppState };
