import { reactive, ref } from 'vue';
import type { Session, EventType } from '../types/api';
import { api } from '../api/client';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  thinking?: string;
  plan?: { completed: boolean; text: string; tool?: string }[];
  tools?: {
    id?: string;
    name: string;
    args: any;
    raw_arguments?: string;
    result?: any;
    status: 'calling' | 'done' | 'error';
    requires_permission?: boolean;
    request_id?: string;
    session_id?: string;
  }[];
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
      const first = this.sessions[0];
      this.currentSessionId = data.current_session_id || (first ? first.id : null);
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
          content: m.content || '',
          thinking: m.thinking,
          plan: m.plan,
          tools: m.tools,
          status: m.status || 'done'
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

  async deleteSession(sessionId: string) {
    try {
      await api.deleteSession(sessionId);
      this.sessions = this.sessions.filter(s => s.id !== sessionId);
      if (this.currentSessionId === sessionId) {
        if (this.sessions.length > 0) {
          const first = this.sessions[0];
          if (first) {
            this.selectSession(first.id);
          }
        } else {
          this.currentSessionId = null;
          this.messages = [];
        }
      }
    } catch (err) {
      console.error('Delete session failed:', err);
    }
  },

  addMessage(message: Message) {
    this.messages.push(message);
  },

  updateLastMessage(updates: Partial<Message>) {
    if (this.messages.length > 0) {
      const last = this.messages[this.messages.length - 1];
      if (last) {
        Object.assign(last, updates);
      }
    }
  }
});
