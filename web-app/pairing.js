import { store } from './state.js';
import { api } from './api.js';

const pairing = {
  modal: null,
  codeInput: null,
  submitBtn: null,
  agentUrlInput: null,

  init() {
    this.modal = document.getElementById('pairingModal');
    this.codeInput = document.getElementById('pairingCode');
    this.submitBtn = document.getElementById('pairSubmitBtn');
    this.agentUrlInput = document.getElementById('agentUrl');

    this.modal.addEventListener('submit', (e) => this.handleSubmit(e));
    this.modal.addEventListener('close', () => this.onClose());

    this.agentUrlInput.value = api.getStoredAgentUrl() || 'http://127.0.0.1:8765';
  },

  show() {
    this.modal.showModal();
    this.codeInput.focus();
  },

  hide() {
    this.modal.close();
  },

  async handleSubmit(e) {
    e.preventDefault();
    const code = this.codeInput.value.trim();
    const agentUrl = this.agentUrlInput.value.trim();

    if (!code) {
      this.codeInput.focus();
      return;
    }

    this.submitBtn.disabled = true;
    this.submitBtn.textContent = 'Connecting...';

    try {
      const token = await api.pair(code, agentUrl);
      store.set({ token, agentUrl });
      this.hide();
    } catch (err) {
      if (err.message === 'AUTH_REQUIRED') {
        alert('Invalid or expired pairing code. Please check the agent terminal for a new code.');
      } else {
        alert(`Pairing failed: ${err.message}`);
      }
      this.submitBtn.disabled = false;
      this.submitBtn.textContent = 'Connect';
      this.codeInput.focus();
    }
  },

  onClose() {
    this.codeInput.value = '';
    this.submitBtn.disabled = false;
    this.submitBtn.textContent = 'Connect';
  }
};

export { pairing };
