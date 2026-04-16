import axios from 'axios';
import type { StreamEvent, Session } from '../types/api';

const BASE_URL = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';

export class GGbotAPI {
  private static instance: GGbotAPI;
  private ws: WebSocket | null = null;
  private eventHandlers: ((event: any) => void)[] = [];

  private constructor() {}

  public static getInstance(): GGbotAPI {
    if (!GGbotAPI.instance) {
      GGbotAPI.instance = new GGbotAPI();
    }
    return GGbotAPI.instance;
  }

  async getSessions(): Promise<any> {
    const response = await axios.get(`${BASE_URL}/api/v1/sessions`);
    return response.data;
  }

  async getSession(sessionId: string): Promise<any> {
    const response = await axios.get(`${BASE_URL}/api/v1/sessions/${sessionId}`);
    return response.data;
  }

  async createSession(title?: string): Promise<Session> {
    const response = await axios.post(`${BASE_URL}/api/v1/sessions`, { title });
    return response.data;
  }

  async deleteSession(sessionId: string): Promise<void> {
    await axios.delete(`${BASE_URL}/api/v1/sessions/${sessionId}`);
  }

  async sendMessage(content: string, sessionId?: string, stream: boolean = true) {
    if (!stream) {
      const response = await axios.post(`${BASE_URL}/api/v1/messages`, {
        content,
        session_id: sessionId,
        stream: false
      });
      return response.data;
    }

    const response = await fetch(`${BASE_URL}/api/v1/messages`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, session_id: sessionId, stream: true })
    });

    if (!response.body) throw new Error('No response body');
    return response.body;
  }

  connectWebSocket() {
    if (this.ws) return;

    this.ws = new WebSocket(WS_URL);
    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      this.eventHandlers.forEach(handler => handler(data));
    };

    this.ws.onclose = () => {
      this.ws = null;
      setTimeout(() => this.connectWebSocket(), 3000); // Reconnect
    };
  }

  onEvent(handler: (event: any) => void) {
    this.eventHandlers.push(handler);
    return () => {
      this.eventHandlers = this.eventHandlers.filter(h => h !== handler);
    };
  }

  sendWSCommand(command: string, payload: any) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }
    this.ws.send(JSON.stringify({
      type: 'command',
      id: Math.random().toString(36).substring(7),
      command,
      payload,
      timestamp: Date.now() / 1000
    }));
  }
}

export const api = GGbotAPI.getInstance();
