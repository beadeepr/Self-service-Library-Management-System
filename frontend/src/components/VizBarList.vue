<script setup lang="ts">
/**
 * 单系列水平条形行：标签 · 条 · 数值。
 *
 * 为什么是「行」而不是「条形图」：这些分布（馆藏状态、分类、排行榜）在演示数据里
 * 常常只有一两项，画成图就是「一根柱子的条形图」这类反模式。
 * 行式布局在任何条数下都成立，实质是一张带单元格条形的表。
 *
 * 单系列只用一种数据色（分类身份由行标签承载，不靠颜色），因此不需要图例；
 * 数值与标签一律用文本色，不穿数据色。每行带 title，作为最轻量的悬停提示。
 */
import { computed } from 'vue'

const props = defineProps<{
  items: { label: string; value: number }[]
  /** 数值后缀，如「册」「次」 */
  unit?: string
}>()

const maxValue = computed(() => Math.max(1, ...props.items.map((item) => item.value)))

function widthOf(value: number): string {
  return `${Math.max(2, Math.round((value / maxValue.value) * 100))}%`
}
</script>

<template>
  <ul class="viz-rows">
    <li
      v-for="item in items"
      :key="item.label"
      class="viz-rows__row"
      :title="`${item.label}：${item.value}${unit ?? ''}`"
    >
      <span class="viz-rows__label">{{ item.label }}</span>
      <span class="viz-rows__track">
        <span class="viz-rows__bar" :style="{ width: widthOf(item.value) }" />
      </span>
      <span class="viz-rows__value">{{ item.value }}{{ unit ?? '' }}</span>
    </li>
  </ul>
</template>

<style scoped>
.viz-rows {
  list-style: none;
  margin: 0;
  padding: 0;
}

.viz-rows__row {
  align-items: center;
  display: grid;
  gap: 10px;
  grid-template-columns: 130px 1fr 64px;
  padding: 5px 0;
}

.viz-rows__label {
  color: var(--lib-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.viz-rows__track {
  background: var(--viz-track);
  border-radius: 2px;
  height: 10px;
  /* 细条：高度封顶，余量留白，不让条填满行高 */
  overflow: hidden;
}

.viz-rows__bar {
  background: var(--viz-series);
  /* 数据端 4px 圆角，基线端保持方角 */
  border-radius: 0 4px 4px 0;
  display: block;
  height: 100%;
}

.viz-rows__value {
  color: var(--lib-text);
  font-variant-numeric: tabular-nums;
  text-align: right;
}
</style>
