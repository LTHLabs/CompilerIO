import { store, AppState } from './state.js';
import { api } from './api.js';
import { editor } from './editor.js';
import { pairing } from './pairing.js';
import { prepare } from './prepare.js';
import { build } from './build.js';
import { logger } from './logger.js';
import { wokwi } from './wokwi.js';
import { library } from './library.js';

async function init() {
  editor.init((code) => {
    const detected = library.detectIncludes(code);
    store.set({ detectedLibraries: detected });
  });
  pairing.init();
  prepare.init();
  build.init();
  logger.init();

  store.subscribe(render);
  await checkAgent();
}

async function checkAgent() {
  store.set({ appState: AppState.CHECKING });
  render();

  try {
    const status = await api.getStatus();
    handleEnvironmentStatus(status);
  } catch (err) {
    if (err.message === 'AUTH_REQUIRED') {
      store.set({ appState: AppState.PAIRING_REQUIRED, token: null });
    } else {
      store.set({ appState: AppState.DISCONNECTED, lastError: err.message });
    }
  }
  render();
}

function handleEnvironmentStatus(status) {
  const token = api.getStoredToken();
  const hasToken = !!token;

  if (status.status === 'READY') {
    if (hasToken) {
      store.set({ token, appState: AppState.READY });
      loadBoardsAndFrameworks();
    } else {
      store.set({ appState: AppState.PAIRING_REQUIRED });
    }
  } else if (status.status === 'NOT_READY') {
    if (hasToken) {
      store.set({ token, appState: AppState.PREPARING });
      prepare.show();
    } else {
      store.set({ appState: AppState.PAIRING_REQUIRED });
    }
  } else if (status.status === 'PREPARING') {
    if (hasToken) {
      store.set({ token, appState: AppState.PREPARING });
    } else {
      store.set({ appState: AppState.PAIRING_REQUIRED });
    }
  } else {
    store.set({ appState: AppState.DISCONNECTED, lastError: status.reason });
  }
}

async function loadBoardsAndFrameworks() {
  try {
    const [boards, frameworks] = await Promise.all([
      api.getBoards(),
      api.getFrameworks()
    ]);
    store.set({ boards, frameworks });
  } catch (err) {
    console.warn('Failed to load boards/frameworks:', err);
  }
}

function render() {
  const state = store.getState();
  updateHeader(state);
  updateEditorSection(state);
  updateBuildSection(state);
  updateLibraryPanel(state);
  updateModals(state);
}

function updateHeader(state) {
  const indicator = document.getElementById('statusIndicator');
  const text = document.getElementById('statusText');

  indicator.className = 'status-indicator';
  switch (state.appState) {
    case AppState.CHECKING:
      indicator.classList.add('connecting');
      text.textContent = 'Checking Local Agent...';
      break;
    case AppState.PAIRING_REQUIRED:
      indicator.classList.add('disconnected');
      text.textContent = 'Local Agent Not Connected';
      break;
    case AppState.PREPARING:
      indicator.classList.add('preparing');
      text.textContent = 'Preparing Environment...';
      break;
    case AppState.READY:
      indicator.classList.add('connected');
      text.textContent = 'Local Agent Connected';
      break;
    case AppState.BUILDING:
      indicator.classList.add('connected');
      text.textContent = 'Building...';
      break;
    case AppState.SUCCESS:
    case AppState.FAILED:
      indicator.classList.add('connected');
      text.textContent = 'Local Agent Connected';
      break;
    case AppState.DISCONNECTED:
    default:
      indicator.classList.add('disconnected');
      text.textContent = state.lastError ? `Error: ${state.lastError}` : 'Local Agent Not Connected';
  }
}

function updateEditorSection(state) {
  const section = document.getElementById('editorSection');
  const boardSelect = document.getElementById('boardSelect');
  const frameworkSelect = document.getElementById('frameworkSelect');

  const readyStates = [AppState.READY, AppState.BUILDING, AppState.SUCCESS, AppState.FAILED];
  section.hidden = !readyStates.includes(state.appState);

  boardSelect.innerHTML = state.boards.map(b =>
    `<option value="${b.id}" ${b.id === state.selectedBoard ? 'selected' : ''}>${b.name}</option>`
  ).join('');

  frameworkSelect.innerHTML = state.frameworks.map(f =>
    `<option value="${f.id}" ${f.id === state.selectedFramework ? 'selected' : ''}>${f.name}</option>`
  ).join('');

  boardSelect.disabled = state.appState === AppState.BUILDING;
  frameworkSelect.disabled = state.appState === AppState.BUILDING;

  boardSelect.onchange = (e) => store.set({ selectedBoard: e.target.value });
  frameworkSelect.onchange = (e) => store.set({ selectedFramework: e.target.value });
}

function updateBuildSection(state) {
  const section = document.getElementById('buildSection');
  section.hidden = state.appState === AppState.DISCONNECTED ||
                   state.appState === AppState.PAIRING_REQUIRED ||
                   state.appState === AppState.PREPARING;
}

function updateLibraryPanel(state) {
  library.renderLibraryPanel(
    state.detectedLibraries,
    state.selectedLibDeps,
    (header, platformioName) => {
      if (!state.selectedLibDeps.some(s => s.header === header)) {
        store.set({
          selectedLibDeps: [...state.selectedLibDeps, { header, platformioName }]
        });
      }
    },
    (header) => {
      store.set({
        selectedLibDeps: state.selectedLibDeps.filter(s => s.header !== header)
      });
    }
  );
}

function updateModals(state) {
  if (state.appState === AppState.PAIRING_REQUIRED && !pairing.modal.open) {
    pairing.show();
  }

  if (state.appState === AppState.PREPARING && !prepare.modal.open) {
    prepare.show();
  }
}

document.addEventListener('DOMContentLoaded', init);