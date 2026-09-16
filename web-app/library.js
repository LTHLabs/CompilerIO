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

const EXTERNAL_LIBRARY_MAP = {
  'DHT.h': {
    name: 'DHT sensor library',
    platformioName: 'DHT sensor library@1.4.4',
  },
  'DHTesp.h': {
    name: 'DHTesp',
    platformioName: 'DHTesp@3.3.0',
  },
  'Adafruit_Sensor.h': {
    name: 'Adafruit Unified Sensor',
    platformioName: 'Adafruit Unified Sensor@1.1.9',
  },
  'Adafruit_BME280.h': {
    name: 'Adafruit BME280 Library',
    platformioName: 'Adafruit BME280 Library@2.2.4',
  },
  'Adafruit_SSD1306.h': {
    name: 'Adafruit SSD1306',
    platformioName: 'Adafruit SSD1306@2.5.7',
  },
  'ArduinoJson.h': {
    name: 'ArduinoJson',
    platformioName: 'ArduinoJson@7.2.1',
  },
  'PubSubClient.h': {
    name: 'PubSubClient',
    platformioName: 'PubSubClient@2.8.0',
  },
  'WebSocketsClient.h': {
    name: 'WebSockets',
    platformioName: 'WebSockets@2.4.1',
  },
  'ESPAsyncWebServer.h': {
    name: 'ESPAsyncWebServer',
    platformioName: 'ESPAsyncWebServer@1.2.3',
  },
  'AsyncTCP.h': {
    name: 'AsyncTCP',
    platformioName: 'AsyncTCP@1.1.1',
  },
  'OneWire.h': {
    name: 'OneWire',
    platformioName: 'OneWire@2.3.8',
  },
  'DallasTemperature.h': {
    name: 'DallasTemperature',
    platformioName: 'DallasTemperature@3.9.1',
  },
  'MQTT.h': {
    name: 'MQTT',
    platformioName: 'MQTT@1.0.0',
  },
  'HTTPClient.h': {
    name: 'HTTPClient',
    platformioName: 'HTTPClient@1.0.0',
  },
  'TimeLib.h': {
    name: 'Time',
    platformioName: 'Time@1.6.1',
  },
  'NTPClient.h': {
    name: 'NTPClient',
    platformioName: 'NTPClient@3.2.1',
  },
  'U8g2lib.h': {
    name: 'U8g2',
    platformioName: 'U8g2@2.35.17',
  },
  'TFT_eSPI.h': {
    name: 'TFT_eSPI',
    platformioName: 'TFT_eSPI@2.5.43',
  },
  'FastLED.h': {
    name: 'FastLED',
    platformioName: 'FastLED@3.6.0',
  },
  'Servo.h': {
    name: 'ESP32Servo',
    platformioName: 'ESP32Servo@1.1.0',
  },
};

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
  if (EXTERNAL_LIBRARY_MAP[header]) {
    return 'external';
  }
  return 'unknown';
}

function resolveLibrary(header) {
  const mapping = EXTERNAL_LIBRARY_MAP[header];
  if (mapping) {
    return {
      header,
      name: mapping.name,
      platformioName: mapping.platformioName,
      type: 'external',
    };
  }
  return {
    header,
    name: header,
    platformioName: header,
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
      const badgeClass = lib.type === 'external' ? 'badge-external' : 'badge-unknown';
      const badgeText = lib.type === 'external' ? `📦 ${escapeHtml(resolved.name)}` : '⚠ Unknown library';

      if (isSelected) {
        html += `
          <li class="library-item library-selected">
            <span class="library-name">${escapeHtml(lib.header)}</span>
            <span class="library-badge ${badgeClass}">${badgeText}</span>
            <button class="btn btn-small btn-remove" data-header="${escapeHtml(lib.header)}" data-action="remove">Remove</button>
          </li>
        `;
      } else {
        html += `
          <li class="library-item">
            <span class="library-name">${escapeHtml(lib.header)}</span>
            <span class="library-badge ${badgeClass}">${badgeText}</span>
            <button class="btn btn-small btn-add" data-header="${escapeHtml(lib.header)}" data-platformio="${escapeHtml(resolved.platformioName)}" data-action="add">Add</button>
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
  EXTERNAL_LIBRARY_MAP,
};