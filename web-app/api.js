const API_BASE = 'http://127.0.0.1:8765';
const TOKEN_KEY = 'compilerio_token';
const AGENT_URL_KEY = 'compilerio_agent_url';

function getHeaders(token = null) {
  const headers = {
    'Origin': window.location.origin,
    'Content-Type': 'application/json'
  };
  if (token) {
    headers['x-local-agent-token'] = token;
  }
  return headers;
}

async function request(path, options = {}) {
  const token = options.token ?? getStoredToken();
  const base = getStoredAgentUrl();
  const url = `${base}${path}`;

  const res = await fetch(url, {
    ...options,
    headers: {
      ...getHeaders(token),
      ...options.headers
    }
  });

  if (res.status === 401 || res.status === 403) {
    clearToken();
    throw new Error('AUTH_REQUIRED');
  }

  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {}
    throw new Error(detail);
  }

  const contentType = res.headers.get('content-type');
  if (contentType?.includes('application/json')) {
    return res.json();
  }
  if (contentType?.includes('application/octet-stream') || contentType?.includes('binary')) {
    return res.blob();
  }
  return res.text();
}

function getStoredToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

function setStoredToken(token) {
  sessionStorage.setItem(TOKEN_KEY, token);
}

function clearToken() {
  sessionStorage.removeItem(TOKEN_KEY);
}

function getStoredAgentUrl() {
  return sessionStorage.getItem(AGENT_URL_KEY) || API_BASE;
}

function setStoredAgentUrl(url) {
  sessionStorage.setItem(AGENT_URL_KEY, url);
}

export const api = {
  async getStatus() {
    return request('/environment/status');
  },

  async prepare(token) {
    return request('/environment/prepare', { method: 'POST', token });
  },

  async pair(code, agentUrl) {
    const base = agentUrl || API_BASE;
    const res = await fetch(`${base}/session/pair`, {
      method: 'POST',
      headers: {
        'Origin': window.location.origin,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ code })
    });

    if (res.status === 401 || res.status === 403) {
      throw new Error('AUTH_REQUIRED');
    }

    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const data = await res.json();
        detail = data.detail || detail;
      } catch {}
      throw new Error(detail);
    }

    const data = await res.json();
    setStoredToken(data.token);
    if (agentUrl) setStoredAgentUrl(agentUrl);
    return data.token;
  },

  async getBoards() {
    return request('/boards');
  },

  async getFrameworks() {
    return request('/frameworks');
  },

  async build(sourceCode, libDeps = [], board = 'esp32dev', framework = 'arduino', projectName = null) {
    const body = { source_code: sourceCode, board, framework, lib_deps: libDeps };
    if (projectName) body.project_name = projectName;
    return request('/build', {
      method: 'POST',
      body: JSON.stringify(body)
    });
  },

  async getBuildStatus(buildId, token) {
    return request(`/build/${buildId}/status`, { token });
  },

  async getBuildLog(buildId, token) {
    return request(`/build/${buildId}/log`, { token });
  },

  async downloadFirmware(buildId, artifactName = 'wokwi-firmware.bin', token) {
    const token_ = token ?? getStoredToken();
    const base = getStoredAgentUrl();
    const url = `${base}/build/${buildId}/firmware/${artifactName}`;
    const res = await fetch(url, {
      headers: getHeaders(token_)
    });

    if (res.status === 401 || res.status === 403) {
      clearToken();
      throw new Error('AUTH_REQUIRED');
    }

    if (!res.ok) {
      throw new Error(`Download failed: HTTP ${res.status}`);
    }

    return res.blob();
  },

  getStoredToken,
  setStoredToken,
  clearToken,
  getStoredAgentUrl,
  setStoredAgentUrl
};