<script setup lang="ts">
import { computed } from 'vue';
import type { Message } from '../stores/chat';
import ThinkingBox from './ThinkingBox.vue';
import PlanProgress from './PlanProgress.vue';
import MarkdownIt from 'markdown-it';
import hljs from 'highlight.js';
import 'highlight.js/styles/github.css';

const props = defineProps<{
  message: Message;
}>();

const md = new MarkdownIt({
  highlight: function (str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return hljs.highlight(str, { language: lang }).value;
      } catch (__) {}
    }
    return ''; // use external default escaping
  }
});

const isAssistant = computed(() => props.message.role === 'assistant');
const isUser = computed(() => props.message.role === 'user');

const formattedContent = computed(() => {
  if (!props.message.content) return '';
  const cleaned = props.message.content
    .replace(/<thinking>[\s\S]*?<\/thinking>/gi, '')
    .replace(/<plan>[\s\S]*?<\/plan>/gi, '')
    .trim();
  return md.render(cleaned);
});

</script>

<template>
  <div class="message-container" :class="{ 'user-msg': isUser, 'assistant-msg': isAssistant }">
    <div v-if="isAssistant" class="avatar">🤖</div>
    
    <div class="message-content">
      <div v-if="isAssistant && message.thinking" class="thinking-wrapper">
        <ThinkingBox :thinking="message.thinking" />
      </div>
      
      <div v-if="isAssistant && message.plan && message.plan.length > 0" class="plan-wrapper">
        <PlanProgress :plan="message.plan" />
      </div>
      
      <div v-if="message.tools && message.tools.length > 0" class="tools-wrapper">
        <div v-for="(tool, idx) in message.tools" :key="idx" class="tool-item">
          <div class="tool-header">
            <span class="tool-icon">🛠️</span>
            <span class="tool-name">{{ tool.name }}</span>
            <span class="tool-status" :class="tool.status">
              {{ tool.requires_permission ? '等待权限...' : (tool.status === 'calling' ? '执行中...' : (tool.status === 'done' ? '已完成' : '失败')) }}
            </span>
          </div>
          <div v-if="tool.args || tool.raw_arguments" class="tool-args">
            <code>{{ tool.args ? JSON.stringify(tool.args) : tool.raw_arguments }}</code>
          </div>
          <div v-if="tool.result" class="tool-result">
             <pre>{{ tool.result }}</pre>
          </div>
        </div>
      </div>

      <div class="bubble">
        <div v-if="message.content" class="text" v-html="formattedContent"></div>
        <div v-else-if="message.status === 'pending'" class="typing-indicator">
          <span></span><span></span><span></span>
        </div>
      </div>
    </div>
    
    <div v-if="isUser" class="avatar">👤</div>
  </div>
</template>

<style scoped>
.message-container {
  display: flex;
  margin-bottom: 0;
  max-width: 85%;
  gap: 12px;
}

.user-msg {
  margin-left: auto;
  justify-content: flex-end;
}

.assistant-msg {
  margin-right: auto;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  border: 1px solid #eee;
}

.message-content {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: calc(100% - 44px);
  min-width: 0;
}

.bubble {
  padding: 2px 0;
  border-radius: 0;
  font-size: 15px;
  line-height: 1.6;
  word-break: break-word;
  background: transparent;
  border: none;
  box-shadow: none;
}

.user-msg .bubble {
  background: transparent;
  color: #1a1a1a;
}

.assistant-msg .bubble {
  background: transparent;
  color: #1a1a1a;
}

:deep(.bubble p) {
  margin-bottom: 8px;
}

:deep(.bubble p:last-child) {
  margin-bottom: 0;
}

:deep(.bubble pre) {
  background: #282c34;
  color: #abb2bf;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  margin: 8px 0;
}

:deep(.bubble code) {
  font-family: 'Fira Code', monospace;
  font-size: 0.9em;
}

:deep(.bubble table) {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 14px;
}

:deep(.bubble th),
:deep(.bubble td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}

:deep(.bubble thead th) {
  background: #f7f8fa;
  font-weight: 600;
}

:deep(.bubble tbody tr:nth-child(even)) {
  background: #fafbfc;
}

.thinking-wrapper, .plan-wrapper {
  margin-bottom: 8px;
}

.tools-wrapper {
  margin-top: 8px;
}

.tool-item {
  background: #f9f9fb;
  border: 1px solid #e5e5e7;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  font-size: 13px;
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.tool-name {
  font-weight: 600;
  color: #444;
}

.tool-status {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 10px;
}

.tool-status.calling { background: #e3f2fd; color: #1976d2; }
.tool-status.done { background: #e8f5e9; color: #388e3c; }
.tool-status.error { background: #ffebee; color: #d32f2f; }

.tool-args, .tool-result {
  margin-top: 6px;
  background: #f0f0f2;
  padding: 6px;
  border-radius: 4px;
  overflow-x: auto;
}

code, pre {
  font-family: monospace;
  font-size: 12px;
}

.typing-indicator {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.typing-indicator span {
  width: 6px;
  height: 6px;
  background: #aaa;
  border-radius: 50%;
  animation: bounce 1.4s infinite ease-in-out both;
}

.typing-indicator span:nth-child(1) { animation-delay: -0.32s; }
.typing-indicator span:nth-child(2) { animation-delay: -0.16s; }

@keyframes bounce {
  0%, 80%, 100% { transform: scale(0); }
  40% { transform: scale(1.0); }
}
</style>
