<script setup lang="ts">
/**
 * 单系列柱状趋势：按天的计数。
 *
 * 规格：柱宽封顶 24px（余量留白）、数据端 4px 圆角而基线端方角、
 * 数值标在柱顶、文字不用数据色。只有一条序列，所以不需要图例。
 * 天数少于 3 时不要用本组件 —— 一两根柱子的「趋势」应当改渲染为标签行。
 */
import { computed } from 'vue'

const props = defineProps<{
  items: { label: string; value: number }[]
  unit?: string
}>()

const maxValue = computed(() => Math.max(1, ...props.items.map((item) => item.value)))

function heightOf(value: number): string {
  // 最小 4% 保底，让 0 值也留下可见的基线痕迹
  return `${Math.max(4, Math.round((value / maxValue.value) * 100))}%`
}
</script>

<template>
  <div class="viz-cols">
    <div
      v-for="item in items"
      :key="item.label"
      class="viz-cols__item"
      :title="`${item.label}：${item.value}${unit ?? ''}`"
    >
      <span class="viz-cols__value">{{ item.value }}</span>
      <span class="viz-cols__slot">
        <span class="viz-cols__bar" :style="{ height: heightOf(item.value) }" />
      </span>
      <span class="viz-cols__label">{{ item.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.viz-cols {
  align-items: flex-end;
  display: flex;
  gap: 10px;
  min-height: 132px;
  overflow-x: auto;
}

.viz-cols__item {
  align-items: center;
  display: flex;
  flex: 1 0 34px;
  flex-direction: column;
  height: 132px;
  justify-content: flex-end;
  max-width: 72px;
}

.viz-cols__value {
  color: var(--lib-text);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  margin-bottom: 4px;
}

.viz-cols__slot {
  align-items: flex-end;
  display: flex;
  flex: 1;
  justify-content: center;
  width: 100%;
}

.viz-cols__bar {
  background: var(--viz-series);
  /* 数据端圆角，基线端方角 */
  border-radius: 4px 4px 0 0;
  max-width: 24px;
  width: 100%;
}

.viz-cols__label {
  color: var(--lib-text-muted);
  font-size: 12px;
  margin-top: 6px;
  white-space: nowrap;
}
</style>
