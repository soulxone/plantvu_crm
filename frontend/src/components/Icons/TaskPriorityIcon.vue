<template>
  <div class="grid place-items-center">
    <div
      class="h-3 w-3 rounded-full"
      :class="[
        {
          'bg-surface-red-3': priority === 'High',
          'bg-surface-amber-3': priority === 'Medium',
          'bg-surface-gray-4': priority === 'Low',
        },
        $attrs.class,
      ]"
    />
  </div>
</template>
<script setup>
defineOptions({
  inheritAttrs: false,
})

defineProps({
  priority: { type: String, required: true },
})
</script>
