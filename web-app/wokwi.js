const wokwi = {
  renderInstructions() {
    return `
      <div class="wokwi-instructions">
        <h3>Upload to Wokwi</h3>
        <ol>
          <li>Click <strong>Download wokwi-firmware.bin</strong> above</li>
          <li>Open your project on <a href="https://wokwi.com" target="_blank" rel="noopener">wokwi.com</a></li>
          <li>Press <kbd>F1</kbd> (or <kbd>Ctrl+Shift+P</kbd> on Windows/Linux, <kbd>Cmd+Shift+P</kbd> on Mac)</li>
          <li>Type <strong>Upload Firmware and Start Simulation</strong> and select it</li>
          <li>Choose the downloaded <code>wokwi-firmware.bin</code> file</li>
          <li>Simulation starts automatically with your firmware</li>
        </ol>
        <p class="wokwi-note">
          <strong>Note:</strong> The firmware is a merged binary (bootloader + partitions + app)
          ready for Wokwi's "Upload Firmware" feature. No additional configuration needed.
        </p>
      </div>
    `;
  }
};

export { wokwi };
