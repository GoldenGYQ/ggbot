<script setup lang="ts">
import { ref } from 'vue';

defineProps<{
  thinking: string;
}>();

const isExpanded = ref(false);
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
      <pre>{{ thinking }}</pre>
    </div>
    <div v-else class="preview">
      {{ thinking.slice(0, 100) }}...
    </div>
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
  cursor: pointer;
  transition: all 0.2s ease;
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
  white-space: pre-wrap;
  line-height: 1.5;
}

.preview {
  margin-top: 4px;
  font-style: italic;
  color: #999;
}

.expanded {
  background: #f3f3f4;
}
</style>
