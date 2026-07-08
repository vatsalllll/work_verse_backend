// REST client for presence + human-to-human direct messages.
import AuthService from './AuthService';

class ChatService {
  constructor() {
    const isHttps = window.location.protocol === 'https:';
    this.apiUrl = isHttps
      ? `https://${window.location.hostname.replace('8080', '8000')}`
      : 'http://localhost:8000';
  }

  _headers() {
    const token = AuthService.getToken();
    return {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {})
    };
  }

  async _get(endpoint) {
    const res = await fetch(`${this.apiUrl}${endpoint}`, { headers: this._headers() });
    if (!res.ok) throw new Error(`Request failed (${res.status})`);
    return res.json();
  }

  async ping() {
    try {
      await fetch(`${this.apiUrl}/presence/ping`, {
        method: 'POST',
        headers: this._headers()
      });
    } catch (e) { /* ignore transient ping errors */ }
  }

  async getOnlineUsers() {
    const data = await this._get('/presence/online');
    return data.users || [];
  }

  // Everyone in the workspace (each with an `online` flag). Message anyone.
  async getDirectory() {
    const data = await this._get('/users');
    return data.users || [];
  }

  async getConversation(otherUserId) {
    const data = await this._get(`/dm/with/${otherUserId}`);
    return data.messages || [];
  }

  async getUnread() {
    const data = await this._get('/dm/unread');
    return data.unread || [];
  }

  async send(toUserId, text) {
    const res = await fetch(`${this.apiUrl}/dm/send`, {
      method: 'POST',
      headers: this._headers(),
      body: JSON.stringify({ to_user_id: toUserId, text })
    });
    if (!res.ok) throw new Error(`Send failed (${res.status})`);
    return res.json();
  }
}

export default new ChatService();
