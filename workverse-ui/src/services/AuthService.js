// Handles login/signup, stores the auth token, and exposes the current user.
// The token is attached to every chat request by ApiService / WebSocketApiService.

const TOKEN_KEY = 'workverse_token';
const USER_KEY = 'workverse_user';

class AuthService {
  constructor() {
    const isHttps = window.location.protocol === 'https:';
    if (isHttps) {
      const host = window.location.hostname;
      this.apiUrl = `https://${host.replace('8080', '8000')}`;
    } else {
      this.apiUrl = 'http://localhost:8000';
    }

    // If we were redirected back from an OAuth provider with ?token=..., capture it.
    this.captureTokenFromUrl();
  }

  captureTokenFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (token) {
      this.setToken(token);
      // Clean the token out of the address bar.
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }

  getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  getUser() {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? JSON.parse(raw) : null;
  }

  isLoggedIn() {
    return !!this.getToken();
  }

  logout() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  }

  async _post(endpoint, body) {
    const res = await fetch(`${this.apiUrl}${endpoint}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Request failed (${res.status})`);
    }
    return data;
  }

  async register(name, email, password) {
    const data = await this._post('/auth/register', { name, email, password });
    this._store(data);
    return data.user;
  }

  async login(email, password) {
    const data = await this._post('/auth/login', { email, password });
    this._store(data);
    return data.user;
  }

  _store(data) {
    if (data.token) this.setToken(data.token);
    if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user));
  }

  // Validates the stored token against the server. Returns true if still valid.
  async verifyToken() {
    const token = this.getToken();
    if (!token) return false;
    try {
      const res = await fetch(`${this.apiUrl}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      if (!res.ok) {
        this.logout();
        return false;
      }
      const data = await res.json();
      if (data.user) localStorage.setItem(USER_KEY, JSON.stringify(data.user));
      return true;
    } catch (e) {
      // Network error — assume token is still usable so offline dev works.
      return true;
    }
  }

  // Phase B/C: kick off OAuth by navigating to the backend login URL.
  oauthLogin(provider) {
    window.location.href = `${this.apiUrl}/auth/${provider}/login`;
  }

  // Demo: list the ready-made workspace accounts.
  async getDemoUsers() {
    try {
      const res = await fetch(`${this.apiUrl}/auth/demo-users`);
      if (!res.ok) return [];
      const data = await res.json();
      return data.users || [];
    } catch (e) {
      return [];
    }
  }

  // Demo: one-click login as a given demo account.
  async demoLogin(email) {
    const data = await this._post('/auth/demo-login', { email });
    this._store(data);
    return data.user;
  }
}

export default new AuthService();
