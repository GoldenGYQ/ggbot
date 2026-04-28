<script setup lang="ts">
import { onMounted, onUnmounted, ref, nextTick, watch } from 'vue';
import { chatStore } from '../stores/chat';
import { api } from '../api/client';
import MessageItem from '../components/MessageItem.vue';
import DocxSidebar from '../components/DocxSidebar.vue';

const inputMessage = ref('');
const providerThinkingEnabled = ref(true);
const chatScroll = ref<HTMLElement | null>(null);
const docSidebarOpen = ref(true);
const docSidebarRef = ref<any>(null);
type PendingPermission = {
  request_id: string;
  tool_name: string;
  arguments: any;
  session_id: string;
  created_ms?: number;
  submitting?: boolean;
  error?: string;
};
const pendingPermissions = ref<PendingPermission[]>([]);

const scrollToBottom = async () => {
  await nextTick();
  if (chatScroll.value) {
    chatScroll.value.scrollTop = chatScroll.value.scrollHeight;
  }
};

onMounted(async () => {
  await chatStore.fetchSessions();
  api.connectWebSocket();
  const unsub = api.onEvent((event) => {
    if (event.type === 'response') {
      handleWSResponse(event);
      return;
    }
    if (event.type === 'error') {
      handleWSError(event);
      return;
    }
    const normalized = normalizeRuntimeEvent(event);
    if (normalized) {
      handleGGEvent(event);
    }
  });
  unsubscribeWS = unsub;
});

onUnmounted(() => {
  if (unsubscribeWS) {
    unsubscribeWS();
    unsubscribeWS = null;
  }
});

let unsubscribeWS: null | (() => void) = null;
const pendingSendCommandIds = new Set<string>();
const toolCallArgsById = new Map<string, any>();

const createAssistantMessage = () => {
  chatStore.addMessage({
    id: (Date.now() + Math.random()).toString(),
    role: 'assistant',
    content: '',
    status: 'pending'
  });
};

const getLastAssistant = () => {
  const lastMsg = chatStore.messages[chatStore.messages.length - 1];
  return lastMsg && lastMsg.role === 'assistant' ? lastMsg : null;
};

const normalizeRuntimeEvent = (event: any): { event_type: string; data: any } | null => {
  if (!event || typeof event !== 'object') return null;
  const typeCandidate = String(
    event.event_type ||
    event.eventType ||
    event._event_type ||
    event.type ||
    ''
  );
  const dataCandidate = event.data ?? event.payload ?? {};
  if (!typeCandidate) return null;
  if (typeCandidate === 'event') {
    const nestedType = String(
      dataCandidate?.event_type ||
      dataCandidate?.eventType ||
      dataCandidate?._event_type ||
      ''
    );
    const nestedData = dataCandidate?.data ?? dataCandidate?.payload ?? {};
    if (!nestedType) return null;
    return { event_type: nestedType, data: nestedData };
  }
  return { event_type: typeCandidate, data: dataCandidate };
};

const removePendingPermission = (requestId: string) => {
  if (!requestId) return;
  pendingPermissions.value = pendingPermissions.value.filter((item) => item.request_id !== requestId);
};

const applyPermissionDecisionToTools = (requestId: string, allowed: boolean, reason?: string) => {
  if (!requestId) return;
  for (let i = chatStore.messages.length - 1; i >= 0; i--) {
    const msg = chatStore.messages[i];
    if (!msg?.tools || msg.tools.length === 0) continue;
    const tool = msg.tools.find(t => t.request_id && t.request_id === requestId);
    if (!tool) continue;
    tool.requires_permission = false;
    if (allowed) {
      tool.status = 'calling';
      tool.result = tool.result || '已批准，等待执行结果...';
    } else {
      tool.status = 'error';
      tool.result = reason || '已拒绝执行';
    }
    break;
  }
};

const handleGGEvent = (event: any) => {
  const normalized = normalizeRuntimeEvent(event);
  if (!normalized) return;
  const { event_type, data } = normalized;
  
  if (event_type === 'assistant_delta') {
    let lastMsg = getLastAssistant();
    if (!lastMsg) {
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (lastMsg) {
      lastMsg.content += data.delta || '';
    }
  } else if (event_type === 'assistant_final') {
    let lastMsg = getLastAssistant();
    if (!lastMsg) {
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (lastMsg) {
      const finalText = data.content || '';
      // Some providers only emit assistant_final without assistant_delta.
      // Keep existing streamed text if present; otherwise use final content directly.
      if (!lastMsg.content || lastMsg.content.trim().length === 0) {
        lastMsg.content = finalText;
      } else if (finalText && !lastMsg.content.includes(finalText)) {
        lastMsg.content = finalText;
      }
      lastMsg.status = 'done';
    }
  } else if (event_type === 'thinking') {
    let lastMsg = getLastAssistant();
    if (!lastMsg) {
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (lastMsg) {
      lastMsg.thinking = (lastMsg.thinking || '') + (data.thinking || '');
    }
  } else if (event_type === 'plan_update') {
    let lastMsg = getLastAssistant();
    if (!lastMsg) {
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (lastMsg) {
      lastMsg.plan = data.plan;
    }
  } else if (event_type === 'tool_call') {
    let lastMsg = getLastAssistant();
    if (!lastMsg) {
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (
      lastMsg &&
      (
        (lastMsg.content && lastMsg.content.trim().length > 0) ||
        (lastMsg.thinking && lastMsg.thinking.trim().length > 0) ||
        (lastMsg.plan && lastMsg.plan.length > 0)
      ) &&
      (!lastMsg.tools || lastMsg.tools.length === 0)
    ) {
      // Entering tool stage: split into a new assistant bubble to avoid
      // pre-tool text and tool timeline accumulating in one giant bubble.
      createAssistantMessage();
      lastMsg = getLastAssistant();
    }
    if (lastMsg) {
      if (!lastMsg.tools) lastMsg.tools = [];
      const existingTool = lastMsg.tools.find(t => data.id && t.id === data.id);
      if (existingTool) {
        existingTool.name = data.name || existingTool.name;
        existingTool.args = data.arguments ?? existingTool.args;
        existingTool.raw_arguments = data.raw_arguments ?? existingTool.raw_arguments;
        existingTool.status = 'calling';
      } else {
        lastMsg.tools.push({
          id: data.id,
          name: data.name,
          args: data.arguments,
          raw_arguments: data.raw_arguments,
          status: 'calling'
        });
      }
      if (data.id) {
        toolCallArgsById.set(String(data.id), data.arguments || {});
      }
    }
  } else if (event_type === 'tool_result') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.tools) {
      const tool =
        (data.id ? lastMsg.tools.find(t => t.id === data.id) : undefined) ||
        lastMsg.tools.find(t => t.name === data.name && t.status === 'calling');
      if (tool) {
        tool.status = data.error ? 'error' : 'done';
        if (data.content !== undefined && data.content !== null) {
          tool.result = data.content;
        } else if (data.content_len !== undefined) {
          tool.result = `工具已返回结果（长度: ${data.content_len}）`;
        }
      }
    }
    if (!data.error && data.name === 'file_write') {
      const toolArgs = data.id ? toolCallArgsById.get(String(data.id)) : undefined;
      const path = typeof toolArgs?.path === 'string' ? toolArgs.path : '';
      if (path && docSidebarRef.value && typeof docSidebarRef.value.applyBackendUpdateFromTool === 'function') {
        docSidebarRef.value.applyBackendUpdateFromTool({
          path,
          source: 'tool_result:file_write'
        });
      }
    }
    if (data.id) {
      toolCallArgsById.delete(String(data.id));
    }
  } else if (event_type === 'turn_complete') {
    chatStore.isTyping = false;
  } else if (event_type === 'status') {
    console.log('Status update:', data.message);
    // Optionally show a toast
  } else if (event_type === 'error' || event_type === 'provider_error') {
    chatStore.addMessage({
      id: Date.now().toString(),
      role: 'assistant',
      content: `❌ 错误: ${data.error || data.message || '未知错误'}`,
      status: 'error'
    });
    chatStore.isTyping = false;
  } else if (event_type === 'permission_request') {
    console.info('[permission] request received', data);
    const requestId = String(data.request_id || '');
    const promptSessionId = String(data.session_id || chatStore.currentSessionId || '');
    if (requestId) {
      const existingPrompt = pendingPermissions.value.find((item) => item.request_id === requestId);
      if (!existingPrompt) {
        pendingPermissions.value.push({
          request_id: requestId,
          tool_name: String(data.tool_name || 'unknown_tool'),
          arguments: data.arguments || {},
          session_id: promptSessionId,
          created_ms: typeof data.created_ms === 'number' ? data.created_ms : undefined,
          submitting: false,
          error: '',
        });
      }
    }
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!lastMsg.tools) lastMsg.tools = [];
      const existing = lastMsg.tools.find(t =>
        t.name === data.tool_name &&
        t.status === 'calling' &&
        JSON.stringify(t.args || {}) === JSON.stringify(data.arguments || {})
      );
      if (existing) {
        existing.requires_permission = true;
        existing.request_id = data.request_id;
        existing.session_id = data.session_id;
      } else {
        lastMsg.tools.push({
          id: data.id,
          name: data.tool_name,
          args: data.arguments,
          status: 'calling',
          requires_permission: true,
          request_id: data.request_id,
          session_id: data.session_id
        });
      }
    }
  } else if (event_type === 'permission_response') {
    console.info('[permission] response received', data);
    const requestId = String(data.request_id || '');
    removePendingPermission(requestId);
    applyPermissionDecisionToTools(requestId, Boolean(data.allowed), data.reason);
  } else if (event_type === 'session_update') {
    chatStore.fetchSessions();
  }
  
  scrollToBottom();
};

const markLastAssistantAsError = (message: string) => {
  const lastMsg = chatStore.messages[chatStore.messages.length - 1];
  if (lastMsg && lastMsg.role === 'assistant') {
    lastMsg.status = 'error';
    lastMsg.content = message;
  } else {
    chatStore.addMessage({
      id: Date.now().toString(),
      role: 'assistant',
      content: message,
      status: 'error'
    });
  }
  chatStore.isTyping = false;
  scrollToBottom();
};

const handleWSError = (event: any) => {
  markLastAssistantAsError(`❌ 错误: ${event.message || 'WebSocket错误'}`);
};

const updateSessionTitleLocally = (sessionId: string, title: string) => {
  if (!sessionId || !title) return;
  const session = chatStore.sessions.find((item) => item.id === sessionId);
  if (session) {
    session.title = title;
  }
};

const handleWSResponse = (event: any) => {
  if (event.command === 'permission_response') {
    const payload = event.payload || {};
    const requestId = String(payload.request_id || '');
    if (payload.success === false) {
      if (requestId) {
        const failed = pendingPermissions.value.find((item) => item.request_id === requestId);
        if (failed) {
          failed.submitting = false;
          failed.error = payload.message || '请求不存在或已过期';
        }
      }
      chatStore.addMessage({
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ 权限确认失败: ${payload.message || '请求不存在或已过期'}`,
        status: 'error'
      });
    } else {
      removePendingPermission(requestId);
      applyPermissionDecisionToTools(requestId, Boolean(payload.allowed), payload.reason);
    }
    return;
  }
  if (event.command === 'stop_message') {
    const payload = event.payload || {};
    if (payload.success) {
      chatStore.isTyping = false;
    }
    return;
  }
  if (event.command !== 'send_message') return;
  const commandId = event.id;
  // Do not hard-fail on command id mismatch; ws message order/race may cause
  // response to arrive before local pending set update.
  if (commandId && pendingSendCommandIds.has(commandId)) {
    pendingSendCommandIds.delete(commandId);
  }

  const payload = event.payload || {};
  if (payload.success === false) {
    markLastAssistantAsError(`❌ 错误: ${payload.error || '消息发送失败'}`);
    return;
  }

  const payloadTitle = typeof payload.title === 'string' ? payload.title.trim() : '';
  const payloadSessionId = typeof payload.session_id === 'string' ? payload.session_id : '';
  if (payloadTitle && payloadSessionId) {
    updateSessionTitleLocally(payloadSessionId, payloadTitle);
  }

  // Fallback: when realtime deltas are absent, use final_response from command response.
  const finalResponse = payload.final_response;
  if (typeof finalResponse === 'string' && finalResponse.length > 0) {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!lastMsg.content || lastMsg.content.trim().length === 0) {
        lastMsg.content = finalResponse;
      }
      lastMsg.status = 'done';
    }
  }
  chatStore.isTyping = false;
};

const decidePermissionPrompt = async (item: PendingPermission, allowed: boolean) => {
  if (item.submitting) return;
  item.error = '';
  item.submitting = true;
  try {
    const sessionId = item.session_id || chatStore.currentSessionId || '';
    if (!sessionId) {
      throw new Error('缺少 session_id，无法提交权限决策');
    }
    const ack = await api.sendPermissionResponse(
      item.request_id,
      allowed,
      sessionId,
      allowed ? 'Approved from Vue permission dialog' : 'Rejected from Vue permission dialog'
    );
    if (!ack || ack.success === false) {
      throw new Error(String(ack?.message || '权限确认未被后端接受'));
    }
    // Immediate UI update based on command ack; runtime event may arrive later.
    removePendingPermission(item.request_id);
    applyPermissionDecisionToTools(item.request_id, allowed, ack.reason);
  } catch (err) {
    item.error = String(err);
    item.submitting = false;
  }
};

const sendMessage = async () => {
  if (!inputMessage.value.trim() || chatStore.isTyping) return;
  
  const content = inputMessage.value;
  inputMessage.value = '';
  
  chatStore.addMessage({
    id: Date.now().toString(),
    role: 'user',
    content: content
  });
  
  chatStore.isTyping = true;
  createAssistantMessage();
  
  scrollToBottom();

  try {
    const commandId = await api.sendMessageWS(
      content,
      chatStore.currentSessionId || undefined,
      providerThinkingEnabled.value,
      providerThinkingEnabled.value
    );
    pendingSendCommandIds.add(commandId);
  } catch (err) {
    console.error('Send message failed:', err);
    markLastAssistantAsError(`❌ 错误: ${String(err)}`);
  }
};

const stopMessage = async () => {
  if (!chatStore.isTyping) return;
  try {
    await api.stopMessageWS(chatStore.currentSessionId || undefined);
  } catch (err) {
    console.error('Stop message failed:', err);
  }
};

const sendOrStop = async () => {
  if (chatStore.isTyping) {
    await stopMessage();
    return;
  }
  await sendMessage();
};

const handleKeydown = (e: KeyboardEvent) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
};

watch(() => chatStore.messages.length, scrollToBottom);
</script>

<template>
  <div class="chat-layout">
    <!-- Sidebar -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <button class="new-chat-btn" @click="chatStore.createNewSession">
          <span class="icon">+</span>
          <span>新对话</span>
        </button>
      </div>
      
      <nav class="session-list">
        <div 
          v-for="session in chatStore.sessions" 
          :key="session.id"
          class="session-item"
          :class="{ active: session.id === chatStore.currentSessionId }"
          @click="chatStore.selectSession(session.id)"
        >
          <span class="session-icon">💬</span>
          <span class="session-title">{{ session.title || '新对话' }}</span>
          <button 
            class="delete-session-btn" 
            @click.stop="chatStore.deleteSession(session.id)"
            title="删除对话"
          >
            ×
          </button>
        </div>
      </nav>
      
      <div class="sidebar-footer">
        <div class="user-profile">
          <div class="avatar">👤</div>
          <span>GGbot User</span>
        </div>
      </div>
    </aside>

    <!-- Main Chat -->
    <main class="main-container">
      <header class="chat-header">
        <div class="current-session-info">
          <h3>{{ chatStore.sessions?.find(s => s.id === chatStore.currentSessionId)?.title || 'GGbot 智能体' }}</h3>
        </div>
      </header>
      
      <div class="messages-viewport" ref="chatScroll">
        <div class="messages-container">
          <div v-if="chatStore.messages.length === 0" class="welcome-screen">
            <div class="logo">🤖</div>
            <h2>你好，我是 GGbot</h2>
            <p>我可以帮你写代码、查资料、或者只是聊聊天。你想聊点什么？</p>
          </div>
          <div
            v-for="msg in chatStore.messages"
            :key="msg.id"
            class="message-row"
          >
            <MessageItem :message="msg" />
          </div>
        </div>
      </div>
      
      <footer class="input-area">
        <div class="chat-options">
          <label class="thinking-toggle">
            <input
              type="checkbox"
              v-model="providerThinkingEnabled"
              :disabled="chatStore.isTyping"
            />
            <span>思考模式（DeepSeek Reasoner）</span>
          </label>
        </div>
        <div class="input-container">
          <textarea 
            v-model="inputMessage" 
            placeholder="输入你的问题..."
            @keydown="handleKeydown"
            rows="1"
            :disabled="chatStore.isTyping"
          ></textarea>
          <button 
            class="send-btn" 
            :disabled="!chatStore.isTyping && !inputMessage.trim()"
            @click="sendOrStop"
          >
            <span v-if="chatStore.isTyping">■</span>
            <span v-else>↑</span>
          </button>
        </div>
        <div class="input-tips">
          GGbot 可能会产生错误信息，请核实重要信息。
        </div>
      </footer>

      <div v-if="pendingPermissions.length > 0" class="permission-float">
        <div class="permission-float-header">
          <span>权限确认</span>
          <span class="count">{{ pendingPermissions.length }}</span>
        </div>
        <div
          v-for="item in pendingPermissions"
          :key="item.request_id"
          class="permission-item"
        >
          <div class="permission-title">{{ item.tool_name }}</div>
          <div class="permission-desc">request_id: {{ item.request_id }}</div>
          <div class="permission-args">
            <code>{{ JSON.stringify(item.arguments || {}) }}</code>
          </div>
          <div class="permission-actions">
            <button
              class="allow"
              :disabled="item.submitting"
              @click="decidePermissionPrompt(item, true)"
            >
              允许
            </button>
            <button
              class="deny"
              :disabled="item.submitting"
              @click="decidePermissionPrompt(item, false)"
            >
              拒绝
            </button>
          </div>
          <div v-if="item.error" class="permission-error">{{ item.error }}</div>
        </div>
      </div>
    </main>

    <DocxSidebar
      ref="docSidebarRef"
      :open="docSidebarOpen"
      :session-id="chatStore.currentSessionId"
      @toggle="docSidebarOpen = !docSidebarOpen"
    />
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  width: 100vw;
  background-color: #fff;
  color: #1a1a1a;
  overflow: hidden;
}

/* Sidebar Styles */
.sidebar {
  width: 240px;
  background-color: #f7f7f9;
  border-right: 1px solid #f0f0f2;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 20px 16px;
}

.new-chat-btn {
  width: 100%;
  padding: 12px;
  background: #3478f6;
  color: white;
  border: none;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.2s;
}

.new-chat-btn:hover {
  background: #2860d3;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  padding: 12px;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 4px;
  transition: background 0.2s;
  color: #666;
}

.session-item:hover {
  background: #eeeef2;
}

.session-item.active {
  background: #e6e6ec;
  color: #1a1a1a;
  font-weight: 500;
}

.session-title {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  flex: 1;
}

.delete-session-btn {
  opacity: 0;
  background: transparent;
  border: none;
  color: #999;
  font-size: 18px;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
  transition: all 0.2s;
}

.session-item:hover .delete-session-btn {
  opacity: 1;
}

.delete-session-btn:hover {
  color: #ff4d4f;
}

.sidebar-footer {
  padding: 16px;
  border-top: 1px solid #f0f0f2;
}

.user-profile {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 14px;
  color: #666;
}

/* Main Container Styles */
.main-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  position: relative;
  background: #fff;
}

.chat-header {
  height: 56px;
  display: flex;
  align-items: center;
  padding: 0 24px;
  justify-content: center;
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  z-index: 10;
}

.chat-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.messages-viewport {
  flex: 1;
  overflow-y: auto;
  padding: 20px 0;
}

.messages-container {
  max-width: 760px;
  margin: 0 auto;
  padding: 0 40px;
}

.message-row {
  border-bottom: 1px solid #ececf1;
  padding: 14px 0;
}

.message-row:first-of-type {
  border-top: 1px solid #ececf1;
}

.welcome-screen {
  text-align: center;
  margin-top: 15vh;
  color: #1a1a1a;
}

.welcome-screen .logo {
  font-size: 48px;
  margin-bottom: 24px;
}

.welcome-screen h2 {
  font-size: 28px;
  margin-bottom: 16px;
}

.welcome-screen p {
  color: #666;
  font-size: 16px;
}

/* Input Area Styles */
.input-area {
  padding: 12px 0 24px;
  max-width: 760px;
  margin: 0 auto;
  width: 100%;
  padding-left: 40px;
  padding-right: 40px;
}

.chat-options {
  margin-bottom: 8px;
  display: flex;
  justify-content: flex-start;
}

.thinking-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #666;
}

.thinking-toggle input {
  cursor: pointer;
}

.input-container {
  position: relative;
  background: #f4f4f7;
  border: 1px solid transparent;
  border-radius: 20px;
  padding: 10px 16px;
  display: flex;
  align-items: flex-end;
  gap: 12px;
  transition: all 0.2s;
}

.input-container:focus-within {
  background: #fff;
  border-color: #3478f6;
  box-shadow: 0 4px 12px rgba(0,0,0,0.08);
}

textarea {
  flex: 1;
  border: none;
  outline: none;
  resize: none;
  padding: 8px 0;
  font-size: 15px;
  line-height: 1.5;
  max-height: 200px;
  background: transparent;
  color: #1a1a1a;
}

.send-btn {
  width: 36px;
  height: 36px;
  background: #3478f6;
  color: white;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  transition: all 0.2s;
  flex-shrink: 0;
  margin-bottom: 2px;
}

.send-btn:disabled {
  background: #e5e5e7;
  cursor: not-allowed;
}

.input-tips {
  text-align: center;
  font-size: 12px;
  color: #999;
  margin-top: 12px;
}

.permission-float {
  position: fixed;
  right: 20px;
  bottom: 24px;
  width: 380px;
  max-height: 55vh;
  overflow: auto;
  background: #ffffff;
  border: 1px solid #e5e7ef;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.15);
  z-index: 9999;
}

.permission-float-header {
  position: sticky;
  top: 0;
  background: #f5f7ff;
  border-bottom: 1px solid #e5e7ef;
  padding: 10px 12px;
  font-size: 13px;
  font-weight: 700;
  display: flex;
  justify-content: space-between;
}

.permission-float-header .count {
  display: inline-flex;
  min-width: 20px;
  height: 20px;
  border-radius: 999px;
  align-items: center;
  justify-content: center;
  background: #dbe5ff;
  color: #244bcf;
  font-size: 12px;
}

.permission-item {
  padding: 10px 12px;
  border-bottom: 1px solid #f0f1f6;
}

.permission-item:last-child {
  border-bottom: none;
}

.permission-title {
  font-size: 13px;
  font-weight: 600;
  color: #1a1a1a;
}

.permission-desc {
  margin-top: 4px;
  font-size: 11px;
  color: #667085;
}

.permission-args {
  margin-top: 6px;
  background: #f6f7fb;
  border-radius: 8px;
  padding: 8px;
  overflow-x: auto;
}

.permission-args code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: #334155;
}

.permission-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}

.permission-actions button {
  border: 1px solid #d8dbe7;
  border-radius: 8px;
  height: 30px;
  padding: 0 10px;
  cursor: pointer;
  font-size: 12px;
}

.permission-actions button.allow {
  color: #0f7a3a;
  background: #eefbf2;
}

.permission-actions button.deny {
  color: #b42318;
  background: #fff0f0;
}

.permission-actions button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.permission-error {
  margin-top: 6px;
  color: #b42318;
  font-size: 12px;
}

.loading {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 0.4; }
  50% { opacity: 1; }
  100% { opacity: 0.4; }
}
</style>
