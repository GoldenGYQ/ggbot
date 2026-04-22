import axios from 'axios';
import type { Session } from '../types/api';

const BASE_URL = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';

export class GGbotAPI {
  private static instance: GGbotAPI;
  private ws: WebSocket | null = null;
  private eventHandlers: ((event: any) => void)[] = [];
  private wsConnectWaiters: { resolve: () => void; reject: (error: Error) => void }[] = [];

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
    this.ws.onopen = () => {
      const waiters = [...this.wsConnectWaiters];
      this.wsConnectWaiters = [];
      waiters.forEach((waiter) => waiter.resolve());
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.eventHandlers.forEach((handler) => handler(data));
      } catch (error) {
        this.eventHandlers.forEach((handler) => handler({
          type: 'error',
          message: `WebSocket消息解析失败: ${String(error)}`
        }));
      }
    };

    this.ws.onclose = () => {
      const waiters = [...this.wsConnectWaiters];
      this.wsConnectWaiters = [];
      waiters.forEach((waiter) => waiter.reject(new Error('WebSocket closed before opening')));
      this.ws = null;
      setTimeout(() => this.connectWebSocket(), 3000); // Reconnect
    };

    this.ws.onerror = () => {
      const waiters = [...this.wsConnectWaiters];
      this.wsConnectWaiters = [];
      waiters.forEach((waiter) => waiter.reject(new Error('WebSocket connection error')));
    };
  }

  onEvent(handler: (event: any) => void) {
    this.eventHandlers.push(handler);
    return () => {
      this.eventHandlers = this.eventHandlers.filter(h => h !== handler);
    };
  }

  private async waitForWebSocketOpen(timeoutMs: number = 5000): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    if (!this.ws || this.ws.readyState === WebSocket.CLOSED) {
      this.connectWebSocket();
    }

    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;

    await new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.wsConnectWaiters = this.wsConnectWaiters.filter((waiter) => waiter.resolve !== wrappedResolve);
        reject(new Error('WebSocket connection timeout'));
      }, timeoutMs);

      const wrappedResolve = () => {
        clearTimeout(timer);
        resolve();
      };
      const wrappedReject = (error: Error) => {
        clearTimeout(timer);
        reject(error);
      };

      this.wsConnectWaiters.push({ resolve: wrappedResolve, reject: wrappedReject });
    });
  }

  async sendWSCommand(command: string, payload: any): Promise<string> {
    await this.waitForWebSocketOpen();
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }
    const commandId =
      (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
    this.ws.send(JSON.stringify({
      type: 'command',
      id: commandId,
      command,
      payload,
      timestamp: Date.now() / 1000
    }));
    return commandId;
  }

  async sendMessageWS(content: string, sessionId?: string): Promise<string> {
    return this.sendWSCommand('send_message', {
      content,
      session_id: sessionId
    });
  }

  async sendPermissionResponse(requestId: string, allowed: boolean, sessionId?: string, reason?: string): Promise<string> {
    return this.sendWSCommand('permission_response', {
      request_id: requestId,
      allowed,
      session_id: sessionId,
      reason: reason || ''
    });
  }
}

export const api = GGbotAPI.getInstance();
