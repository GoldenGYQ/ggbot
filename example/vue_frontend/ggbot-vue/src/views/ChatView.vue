<script setup lang="ts">
import { onMounted, ref, nextTick, watch } from 'vue';
import { chatStore } from '../stores/chat';
import { api } from '../api/client';
import MessageItem from '../components/MessageItem.vue';

const inputMessage = ref('');
const chatScroll = ref<HTMLElement | null>(null);

const scrollToBottom = async () => {
  await nextTick();
  if (chatScroll.value) {
    chatScroll.value.scrollTop = chatScroll.value.scrollHeight;
  }
};

onMounted(async () => {
  await chatStore.fetchSessions();
  api.connectWebSocket();
  api.onEvent((event) => {
    if (event.type === 'event') {
      handleGGEvent(event);
    }
  });
});

const handleGGEvent = (event: any) => {
  const { event_type, data } = event;
  
  if (event_type === 'assistant_delta') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.content += data.delta || '';
    }
  } else if (event_type === 'thinking') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.thinking = (lastMsg.thinking || '') + (data.thinking || '');
    }
  } else if (event_type === 'plan_update') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      lastMsg.plan = data.plan;
    }
  } else if (event_type === 'tool_call') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!lastMsg.tools) lastMsg.tools = [];
      lastMsg.tools.push({
        name: data.name,
        args: data.arguments,
        status: 'calling'
      });
    }
  } else if (event_type === 'tool_result') {
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant' && lastMsg.tools) {
      const tool = lastMsg.tools.find(t => t.name === data.name && t.status === 'calling');
      if (tool) {
        tool.status = data.error ? 'error' : 'done';
        tool.result = data.content;
      }
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
    const lastMsg = chatStore.messages[chatStore.messages.length - 1];
    if (lastMsg && lastMsg.role === 'assistant') {
      if (!lastMsg.tools) lastMsg.tools = [];
      lastMsg.tools.push({
        name: data.tool_name,
        args: data.arguments,
        status: 'calling',
        requires_permission: true
      });
    }
  } else if (event_type === 'session_update') {
    chatStore.fetchSessions();
  }
  
  scrollToBottom();
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
  chatStore.addMessage({
    id: (Date.now() + 1).toString(),
    role: 'assistant',
    content: '',
    status: 'pending'
  });
  
  scrollToBottom();

  try {
    const stream = await api.sendMessage(content, chatStore.currentSessionId || undefined);
    if (stream instanceof ReadableStream) {
      const reader = stream.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const event = JSON.parse(line);
            if (event.type === 'event') {
              handleGGEvent(event);
            } else if (event.type === 'complete') {
              chatStore.isTyping = false;
              if (event.data.session_id && !chatStore.currentSessionId) {
                chatStore.currentSessionId = event.data.session_id;
                chatStore.fetchSessions();
              }
            }
          } catch (e) {
            console.error('Error parsing stream line:', e, line);
          }
        }
      }
    }
  } catch (err) {
    console.error('Send message failed:', err);
    chatStore.isTyping = false;
  }
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
          <MessageItem 
            v-for="msg in chatStore.messages" 
            :key="msg.id" 
            :message="msg" 
          />
        </div>
      </div>
      
      <footer class="input-area">
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
            :disabled="!inputMessage.trim() || chatStore.isTyping"
            @click="sendMessage"
          >
            <span v-if="chatStore.isTyping" class="loading">...</span>
            <span v-else>↑</span>
          </button>
        </div>
        <div class="input-tips">
          GGbot 可能会产生错误信息，请核实重要信息。
        </div>
      </footer>
    </main>
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

.loading {
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 0.4; }
  50% { opacity: 1; }
  100% { opacity: 0.4; }
}
</style>
