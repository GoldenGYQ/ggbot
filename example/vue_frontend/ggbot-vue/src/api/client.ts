import axios from 'axios';
import type { Session } from '../types/api';

const BASE_URL = 'http://127.0.0.1:8000';
const WS_URL = 'ws://127.0.0.1:8000/ws';

export class GGbotAPI {
  private static instance: GGbotAPI;
  private ws: WebSocket | null = null;
  private eventHandlers: ((event: any) => void)[] = [];
  private wsConnectWaiters: { resolve: () => void; reject: (error: Error) => void }[] = [];
  private wsResponseWaiters = new Map<
    string,
    { resolve: (payload: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }
  >();

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
        if (data?.type === 'response' && typeof data.id === 'string') {
          const waiter = this.wsResponseWaiters.get(data.id);
          if (waiter) {
            clearTimeout(waiter.timer);
            this.wsResponseWaiters.delete(data.id);
            waiter.resolve(data.payload);
          }
        }
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
      this.wsResponseWaiters.forEach((waiter) => {
        clearTimeout(waiter.timer);
        waiter.reject(new Error('WebSocket closed before receiving command response'));
      });
      this.wsResponseWaiters.clear();
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

  async sendWSCommandAndWait(command: string, payload: any, timeoutMs: number = 20000): Promise<any> {
    await this.waitForWebSocketOpen();
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket not connected');
    }
    const commandId =
      (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function')
        ? crypto.randomUUID()
        : `${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;

    const responsePromise = new Promise<any>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.wsResponseWaiters.delete(commandId);
        reject(new Error(`命令超时: ${command}`));
      }, timeoutMs);
      this.wsResponseWaiters.set(commandId, { resolve, reject, timer });
    });

    this.ws.send(JSON.stringify({
      type: 'command',
      id: commandId,
      command,
      payload,
      timestamp: Date.now() / 1000
    }));

    return responsePromise;
  }

  async sendMessageWS(
    content: string,
    sessionId?: string,
    providerThinking?: boolean,
    thinkingEnabled?: boolean
  ): Promise<string> {
    return this.sendWSCommand('send_message', {
      content,
      session_id: sessionId,
      provider_thinking: providerThinking,
      thinking_enabled: thinkingEnabled
    });
  }

  async stopMessageWS(sessionId?: string): Promise<string> {
    return this.sendWSCommand('stop_message', {
      session_id: sessionId
    });
  }

  async runDocxBuildWS(payload: {
    manifest_path: string;
    session_id?: string;
    only_section_id?: string;
    resume?: boolean;
    write_state?: boolean;
    state_path?: string;
  }): Promise<string> {
    return this.sendWSCommand('run_docx_build', payload);
  }

  async sendPermissionResponse(requestId: string, allowed: boolean, sessionId?: string, reason?: string): Promise<any> {
    return this.sendWSCommandAndWait('permission_response', {
      request_id: requestId,
      allowed,
      session_id: sessionId,
      reason: reason || ''
    });
  }

  async executeToolWS(name: string, argumentsPayload: any, sessionId?: string): Promise<any> {
    return this.sendWSCommandAndWait('execute_tool', {
      name,
      arguments: argumentsPayload,
      session_id: sessionId
    });
  }

  async buildDocumentChangeSetWS(before: string, after: string, documentId?: string, source?: string): Promise<any> {
    return this.sendWSCommandAndWait('build_document_change_set', {
      before,
      after,
      document_id: documentId,
      source
    });
  }

  getWorkspaceDocxUrl(path: string, cacheBust: boolean = true): string {
    const url = new URL(`${BASE_URL}/api/v1/workspace/file`);
    url.searchParams.set('path', path);
    if (cacheBust) {
      url.searchParams.set('_t', String(Date.now()));
    }
    return url.toString();
  }
}

export const api = GGbotAPI.getInstance();
