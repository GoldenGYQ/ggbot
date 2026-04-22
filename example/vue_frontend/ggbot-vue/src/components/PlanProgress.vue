<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  plan: { completed: boolean; text: string; tool?: string }[];
}>();

const progress = computed(() => {
  if (!props.plan.length) return 0;
  const completed = props.plan.filter(item => item.completed).length;
  return Math.round((completed / props.plan.length) * 100);
});

const currentStepIndex = computed(() => {
  const index = props.plan.findIndex(item => !item.completed);
  return index === -1 ? props.plan.length : index;
});
</script>

<template>
  <div class="plan-container">
    <div class="plan-header">
      <div class="plan-title">
        <span class="icon">📋</span>
        <span>执行计划</span>
      </div>
      <div class="plan-percentage">{{ progress }}%</div>
    </div>
    
    <div class="progress-bar-bg">
      <div class="progress-bar-fill" :style="{ width: `${progress}%` }"></div>
    </div>

    <div class="plan-items">
      <div 
        v-for="(item, index) in plan" 
        :key="index" 
        class="plan-item"
        :class="{ 
          'completed': item.completed, 
          'active': index === currentStepIndex,
          'pending': index > currentStepIndex 
        }"
      >
        <div class="item-status">
          <span v-if="item.completed" class="check">✓</span>
          <span v-else-if="index === currentStepIndex" class="dot active-dot"></span>
          <span v-else class="dot"></span>
        </div>
        <div class="item-content">
          <span class="item-text">{{ item.text }}</span>
          <span v-if="item.tool" class="item-tool">({{ item.tool }})</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.plan-container {
  background: #f8f9fa;
  border: 1px solid #e9ecef;
  border-radius: 12px;
  padding: 12px;
  margin-bottom: 12px;
  font-size: 13px;
}

.plan-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.plan-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #495057;
}

.plan-percentage {
  color: #3478f6;
  font-weight: 700;
  font-family: monospace;
}

.progress-bar-bg {
  height: 4px;
  background: #e9ecef;
  border-radius: 2px;
  margin-bottom: 12px;
  overflow: hidden;
}

.progress-bar-fill {
  height: 100%;
  background: #3478f6;
  transition: width 0.3s ease;
}

.plan-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.plan-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  transition: all 0.2s;
}

.item-status {
  width: 16px;
  height: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-top: 2px;
}

.check {
  color: #28a745;
  font-weight: bold;
}

.dot {
  width: 6px;
  height: 6px;
  background: #dee2e6;
  border-radius: 50%;
}

.active-dot {
  background: #3478f6;
  box-shadow: 0 0 0 3px rgba(52, 120, 246, 0.2);
  animation: pulse 1.5s infinite;
}

.item-content {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  color: #adb5bd;
}

.plan-item.active .item-content {
  color: #212529;
  font-weight: 500;
}

.plan-item.completed .item-content {
  color: #6c757d;
  text-decoration: line-through opacity 0.6;
}

.item-tool {
  font-family: monospace;
  font-size: 11px;
  background: #f1f3f5;
  padding: 0 4px;
  border-radius: 4px;
  color: #6c757d;
}

@keyframes pulse {
  0% { transform: scale(1); opacity: 1; }
  50% { transform: scale(1.2); opacity: 0.7; }
  100% { transform: scale(1); opacity: 1; }
}
</style>
