import { reactive, ref } from 'vue';
import type { Session, EventType } from '../types/api';
import { api } from '../api/client';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  tools?: { name: string; args: any; result?: any; status: 'calling' | 'done' | 'error' }[];
  status?: 'pending' | 'done' | 'error';
}

export const chatStore = reactive({
  sessions: [] as Session[],
  currentSessionId: null as string | null,
  messages: [] as Message[],
  isTyping: false,

  async fetchSessions() {
    const data = await api.getSessions();
    this.sessions = data.sessions || [];
    if (this.sessions.length > 0 && !this.currentSessionId) {
      this.currentSessionId = data.current_session_id || this.sessions[0].id;
    }
  },

  async selectSession(sessionId: string) {
    this.currentSessionId = sessionId;
    this.messages = [];
    try {
      const data = await api.getSession(sessionId);
      if (data.messages) {
        this.messages = data.messages.map((m: any) => ({
          id: m.timestamp || Math.random().toString(),
          role: m.role,
          content: m.content,
          status: 'done'
        }));
      }
    } catch (err) {
      console.error('Fetch session history failed:', err);
    }
  },

  async createNewSession() {
    const session = await api.createSession();
    this.sessions.unshift(session);
    this.currentSessionId = session.id;
    this.messages = [];
  },

  addMessage(message: Message) {
    this.messages.push(message);
  },

  updateLastMessage(updates: Partial<Message>) {
    if (this.messages.length > 0) {
      const last = this.messages[this.messages.length - 1];
      Object.assign(last, updates);
    }
  }
});
