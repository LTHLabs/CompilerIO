import { store } from './state.js';
import { api } from './api.js';

const prepare = {
  modal: null,
  prepareBtn: null,
  closeBtn: null,
  spinner: null,
  statusEl: null,
  messageEl: null,
  isPreparing: false,

  init() {
    this.modal = document.getElementById('prepareModal');
    this.prepareBtn = document.getElementById('prepareBtn');
    this.closeBtn = document.getElementById('closePrepareBtn');
    this.spinner = document.getElementById('prepareSpinner');
    this.statusEl = document.getElementById('prepareStatus');
    this.messageEl = document.getElementById('prepareMessage');

    this.prepareBtn.addEventListener('click', () => this.startPrepare());
    this.closeBtn.addEventListener('click', () => this.close());
    this.modal.addEventListener('close', () => this.onClose());
  },

  show(message = null) {
    if (message) this.messageEl.textContent = message;
    this.resetUI();
    this.modal.showModal();
  },

  hide() {
    this.modal.close();
  },

  resetUI() {
    this.prepareBtn.hidden = false;
    this.closeBtn.hidden = true;
    this.spinner.hidden = true;
    this.statusEl.hidden = true;
    this.statusEl.textContent = '';
    this.isPreparing = false;
  },

  async startPrepare() {
    this.isPreparing = true;
    this.prepareBtn.hidden = true;
    this.closeBtn.hidden = false;
    this.spinner.hidden = false;
    this.statusEl.hidden = false;
    this.statusEl.textContent = 'Preparing environment...';

    const token = store.getState().token;
    if (!token) {
      this.showError('No session token. Please pair first.');
      return;
    }

    try {
      const result = await api.prepare(token);
      if (result.status === 'READY') {
        this.statusEl.textContent = 'Environment ready!';
        this.statusEl.style.color = 'var(--success)';
        setTimeout(() => this.hide(), 1000);
      } else {
        this.showError(`Environment not ready: ${result.reason || 'Unknown error'}`);
      }
    } catch (err) {
      this.showError(err.message);
    }
  },

  showError(message) {
    this.isPreparing = false;
    this.spinner.hidden = true;
    this.prepareBtn.hidden = false;
    this.closeBtn.hidden = true;
    this.statusEl.textContent = `Error: ${message}`;
    this.statusEl.style.color = 'var(--error)';
  },

  close() {
    if (this.isPreparing) {
      this.isPreparing = false;
      this.spinner.hidden = true;
      this.prepareBtn.hidden = false;
      this.closeBtn.hidden = true;
      this.statusEl.textContent = 'Closed';
    } else {
      this.hide();
    }
  },

  onClose() {
    this.resetUI();
  }
};

export { prepare };
