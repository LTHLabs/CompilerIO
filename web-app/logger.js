const logger = {
  modal: null,
  contentEl: null,
  closeBtn: null,

  init() {
    this.modal = document.getElementById('logSection');
    this.contentEl = document.getElementById('logContent');
    this.closeBtn = document.getElementById('closeLogBtn');

    this.closeBtn.addEventListener('click', () => this.hide());
    this.modal.addEventListener('click', (e) => {
      if (e.target === this.modal) this.hide();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !this.modal.hasAttribute('hidden')) {
        this.hide();
      }
    });
  },

  show(logContent) {
    this.contentEl.textContent = logContent || 'No log available';
    this.modal.hidden = false;
    this.contentEl.scrollTop = this.contentEl.scrollHeight;
  },

  hide() {
    this.modal.hidden = true;
  }
};

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => logger.init());
}

export { logger };
