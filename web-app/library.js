import { LIBRARY_CATALOG } from './library-catalog.js';

const CORE_HEADERS = new Set([
  'Arduino.h',
  'SPI.h',
  'Wire.h',
  'WiFi.h',
  'WiFiClient.h',
  'WiFiServer.h',
  'WiFiUdp.h',
  'WebServer.h',
  'HTTPClient.h',
  'FS.h',
  'SD.h',
  'SD_MMC.h',
  'EEPROM.h',
  'Preferences.h',
  'BluetoothSerial.h',
  'ESP32Servo.h',
  'analogWrite.h',
  'driver/adc.h',
  'driver/dac.h',
  'driver/gpio.h',
  'driver/i2c.h',
  'driver/ledc.h',
  'driver/spi_master.h',
  'driver/uart.h',
  'esp_wifi.h',
  'esp_bt.h',
  'esp_system.h',
  'esp_event.h',
  'esp_log.h',
  'esp_timer.h',
  'esp_sleep.h',
  'esp_ota_ops.h',
  'esp_partition.h',
  'nvs_flash.h',
  'nvs.h',
  'freertos/FreeRTOS.h',
  'freertos/task.h',
  'freertos/queue.h',
  'freertos/semphr.h',
  'freertos/timers.h',
  'freertos/event_groups.h',
  'soc/soc.h',
  'soc/rtc.h',
  'hal/adc_hal.h',
  'hal/dac_hal.h',
  'hal/gpio_hal.h',
  'rom/ets_sys.h',
  'rom/gpio.h',
  'rom/uart.h',
]);

function detectIncludes(source) {
  const includes = [];
  let state = 'NORMAL';
  let i = 0;
  let lineNumber = 1;
  let blockCommentStartLine = 1;

  while (i < source.length) {
    const ch = source[i];
    const next = source[i + 1];

    switch (state) {
      case 'NORMAL':
        if (ch === '\n') {
          lineNumber++;
        }
        if (ch === '/' && next === '/') {
          state = 'LINE_COMMENT';
          i += 2;
        } else if (ch === '/' && next === '*') {
          state = 'BLOCK_COMMENT';
          blockCommentStartLine = lineNumber;
          i += 2;
        } else if (ch === '"') {
          state = 'STRING';
          i++;
        } else if (ch === "'") {
          state = 'CHAR';
          i++;
        } else if (ch === '#') {
          const includeMatch = matchInclude(source, i, lineNumber);
          if (includeMatch) {
            includes.push(includeMatch);
            i = includeMatch.endIndex;
          } else {
            i++;
          }
        } else {
          i++;
        }
        break;

      case 'LINE_COMMENT':
        if (ch === '\n') {
          state = 'NORMAL';
          lineNumber++;
        }
        i++;
        break;

      case 'BLOCK_COMMENT':
        if (ch === '\n') {
          lineNumber++;
        }
        if (ch === '*' && next === '/') {
          state = 'NORMAL';
          i += 2;
        } else {
          i++;
        }
        break;

      case 'STRING':
        if (ch === '\\' && next) {
          i += 2;
        } else if (ch === '"') {
          state = 'NORMAL';
          i++;
        } else if (ch === '\n') {
          lineNumber++;
          i++;
        } else {
          i++;
        }
        break;

      case 'CHAR':
        if (ch === '\\' && next) {
          i += 2;
        } else if (ch === "'") {
          state = 'NORMAL';
          i++;
        } else if (ch === '\n') {
          lineNumber++;
          i++;
        } else {
          i++;
        }
        break;
    }
  }

  const seen = new Set();
  const unique = [];
  for (const inc of includes) {
    const key = inc.header;
    if (!seen.has(key)) {
      seen.add(key);
      unique.push({
        header: inc.header,
        type: classifyHeader(inc.header, inc.type),
        line: inc.line,
      });
    }
  }

  return unique;
}

function matchInclude(source, startIndex, lineNumber) {
  let i = startIndex + 1;
  const len = source.length;

  while (i < len && (source[i] === ' ' || source[i] === '\t')) {
    i++;
  }

  if (i + 7 > len) return null;
  const keyword = source.substring(i, i + 7);
  if (keyword !== 'include') return null;
  i += 7;

  while (i < len && (source[i] === ' ' || source[i] === '\t')) {
    i++;
  }

  if (i >= len) return null;

  const delimiter = source[i];
  if (delimiter !== '<' && delimiter !== '"') return null;
  i++;

  const endDelimiter = delimiter === '<' ? '>' : '"';
  let header = '';
  let headerStartLine = lineNumber;

  while (i < len) {
    const ch = source[i];
    if (ch === '\n') {
      return null;
    }
    if (ch === endDelimiter) {
      i++;
      break;
    }
    header += ch;
    i++;
  }

  if (!header) return null;

  return {
    header,
    type: delimiter === '<' ? 'system' : 'local',
    line: headerStartLine,
    endIndex: i,
  };
}

function classifyHeader(header, includeType) {
  if (includeType === 'local') {
    return 'local';
  }
  if (CORE_HEADERS.has(header)) {
    return 'core';
  }
  if (LIBRARY_CATALOG[header]) {
    return 'external';
  }
  return 'unknown';
}

// Resolve a detected header against the verified catalog only. A header not
// in the catalog has no known Registry spec here — it must not be guessed.
// `platformioName` is null for that case, and callers must not offer it for
// selection (see renderLibraryPanel), so it can never reach selectedLibDeps
// or the build payload.
function resolveLibrary(header) {
  const entry = LIBRARY_CATALOG[header];
  if (entry) {
    return {
      header,
      name: entry.name,
      platformioName: entry.platformioName,
      type: 'external',
    };
  }
  return {
    header,
    name: header,
    platformioName: null,
    type: 'unknown',
  };
}

function renderLibraryPanel(detectedLibraries, selectedLibDeps, onAdd, onRemove) {
  const panel = document.getElementById('libraryPanel');
  const list = document.getElementById('libraryList');

  if (!detectedLibraries || detectedLibraries.length === 0) {
    panel.hidden = true;
    return;
  }

  const externalLibs = detectedLibraries.filter(l => l.type === 'external' || l.type === 'unknown');
  const coreLibs = detectedLibraries.filter(l => l.type === 'core');
  const localLibs = detectedLibraries.filter(l => l.type === 'local');

  if (externalLibs.length === 0 && coreLibs.length === 0 && localLibs.length === 0) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;

  let html = '';

  if (coreLibs.length > 0) {
    html += '<div class="library-group">';
    html += '<h4 class="library-group-title">Core (Arduino ESP32)</h4>';
    html += '<ul class="library-list">';
    for (const lib of coreLibs) {
      html += `
        <li class="library-item library-core">
          <span class="library-name">${escapeHtml(lib.header)}</span>
          <span class="library-badge badge-core">✓ Included in Arduino core</span>
        </li>
      `;
    }
    html += '</ul></div>';
  }

  if (localLibs.length > 0) {
    html += '<div class="library-group">';
    html += '<h4 class="library-group-title">Local / Project Files</h4>';
    html += '<ul class="library-list">';
    for (const lib of localLibs) {
      html += `
        <li class="library-item library-local">
          <span class="library-name">${escapeHtml(lib.header)}</span>
          <span class="library-badge badge-local">📁 Project file</span>
        </li>
      `;
    }
    html += '</ul></div>';
  }

  if (externalLibs.length > 0) {
    html += '<div class="library-group">';
    html += '<h4 class="library-group-title">External Libraries</h4>';
    html += '<ul class="library-list">';
    for (const lib of externalLibs) {
      const resolved = resolveLibrary(lib.header);
      const isSelected = selectedLibDeps.some(s => s.header === lib.header);
      const isVerified = lib.type === 'external' && resolved.platformioName;
      const badgeClass = isVerified ? 'badge-external' : 'badge-unknown';
      const badgeText = isVerified ? `📦 ${escapeHtml(resolved.name)}` : '⚠ Not in verified catalog';

      if (isSelected) {
        html += `
          <li class="library-item library-selected">
            <span class="library-name">${escapeHtml(lib.header)}</span>
            <span class="library-badge ${badgeClass}">${badgeText}</span>
            <button class="btn btn-small btn-remove" data-header="${escapeHtml(lib.header)}" data-action="remove">Remove</button>
          </li>
        `;
      } else if (isVerified) {
        html += `
          <li class="library-item">
            <span class="library-name">${escapeHtml(lib.header)}</span>
            <span class="library-badge ${badgeClass}">${badgeText}</span>
            <button class="btn btn-small btn-add" data-header="${escapeHtml(lib.header)}" data-platformio="${escapeHtml(resolved.platformioName)}" data-action="add">Add</button>
          </li>
        `;
      } else {
        // No verified Registry spec for this header: no Add button, so it
        // can never enter selectedLibDeps or the /build payload.
        html += `
          <li class="library-item library-unverified">
            <span class="library-name">${escapeHtml(lib.header)}</span>
            <span class="library-badge ${badgeClass}">${badgeText}</span>
          </li>
        `;
      }
    }
    html += '</ul></div>';
  }

  list.innerHTML = html;

  list.querySelectorAll('[data-action="add"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const header = btn.dataset.header;
      const platformioName = btn.dataset.platformio;
      onAdd(header, platformioName);
    });
  });

  list.querySelectorAll('[data-action="remove"]').forEach(btn => {
    btn.addEventListener('click', () => {
      const header = btn.dataset.header;
      onRemove(header);
    });
  });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

const library = {
  detectIncludes,
  classifyHeader,
  resolveLibrary,
  renderLibraryPanel,
  CORE_HEADERS,
  LIBRARY_CATALOG,
};

export { library };
