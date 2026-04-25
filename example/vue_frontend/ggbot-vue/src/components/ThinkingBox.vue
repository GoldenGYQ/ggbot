<script setup lang="ts">
import { computed, ref } from 'vue';

const isExpanded = ref(false);
const props = defineProps<{
  thinking: string;
}>();

const previewText = computed(() => {
  const text = (props.thinking || '').trim();
  if (text.length <= 120) return text;
  return `${text.slice(0, 120)}...`;
});
</script>

<template>
  <div class="thinking-box" :class="{ expanded: isExpanded }">
    <div class="header" @click="isExpanded = !isExpanded">
      <div class="title">
        <span class="icon">🤔</span>
        <span>思考过程</span>
      </div>
      <div class="arrow" :class="{ rotated: isExpanded }">▼</div>
    </div>
    <div v-if="isExpanded" class="content">
      <pre>{{ props.thinking }}</pre>
    </div>
    <div v-else class="preview">{{ previewText }}</div>
  </div>
</template>

<style scoped>
.thinking-box {
  background: #f7f7f8;
  border-radius: 8px;
  padding: 8px 12px;
  margin: 8px 0;
  font-size: 13px;
  color: #666;
  border-left: 3px solid #ccc;
  transition: all 0.2s ease;
  max-width: 100%;
  overflow: hidden;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 500;
}

.arrow {
  font-size: 10px;
  transition: transform 0.2s;
}

.arrow.rotated {
  transform: rotate(180deg);
}

.content {
  margin-top: 8px;
  min-width: 0;
}

.content pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
  line-height: 1.5;
  font-family: inherit;
  max-width: 100%;
}

.preview {
  margin-top: 4px;
  font-style: italic;
  color: #999;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-wrap: anywhere;
}

.expanded {
  background: #f3f3f4;
}
</style>
