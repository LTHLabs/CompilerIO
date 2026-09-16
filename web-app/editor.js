const editor = {
  textarea: null,
  lineNumbers: null,
  onChangeCallback: null,
  changeDebounceTimer: null,

  init(onChange) {
    this.textarea = document.getElementById('codeEditor');
    this.lineNumbers = document.getElementById('lineNumbers');
    this.onChangeCallback = onChange;

    this.textarea.addEventListener('input', () => this.handleInput());
    this.textarea.addEventListener('scroll', () => this.syncScroll());
    this.textarea.addEventListener('keydown', (e) => this.handleTab(e));

    this.updateLineNumbers();
  },

  handleInput() {
    this.updateLineNumbers();
    if (this.onChangeCallback) {
      clearTimeout(this.changeDebounceTimer);
      this.changeDebounceTimer = setTimeout(() => {
        this.onChangeCallback(this.textarea.value);
      }, 300);
    }
  },

  updateLineNumbers() {
    const lines = this.textarea.value.split('\n').length;
    const nums = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
    this.lineNumbers.textContent = nums;
  },

  syncScroll() {
    this.lineNumbers.scrollTop = this.textarea.scrollTop;
  },

  handleTab(e) {
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = this.textarea.selectionStart;
      const end = this.textarea.selectionEnd;
      this.textarea.value = this.textarea.value.substring(0, start) + '  ' + this.textarea.value.substring(end);
      this.textarea.selectionStart = this.textarea.selectionEnd = start + 2;
      this.updateLineNumbers();
    }
  },

  getCode() {
    return this.textarea.value;
  },

  setCode(code) {
    this.textarea.value = code;
    this.updateLineNumbers();
  },

  clear() {
    this.textarea.value = '';
    this.updateLineNumbers();
  },

  setEnabled(enabled) {
    this.textarea.disabled = !enabled;
  },

  focus() {
    this.textarea.focus();
  }
};