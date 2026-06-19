<template>
  <div
    class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 text-sm"
    data-build="crmcallci-v1"
  >
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center gap-1.5 font-medium text-ink-gray-8">
        <LucideHeadphones class="h-4 w-4 shrink-0 text-ink-teal-3" />
        {{ __('Conversation Intelligence') }}
        <span
          v-if="sentiment"
          class="ml-1 rounded-full px-2 py-0.5 text-xs font-semibold"
          :class="sentimentClass"
        >
          {{ sentiment }}
        </span>
      </div>
      <Button
        class="ml-auto"
        :loading="busy"
        :label="__('Analyze call')"
        @click="analyze"
      >
        <template #prefix><LucideSparkles class="h-4 w-4" /></template>
      </Button>
    </div>

    <textarea
      v-model="transcript"
      rows="3"
      class="mt-2 w-full resize-y rounded border border-outline-gray-2 bg-surface-white p-2 text-sm text-ink-gray-8 focus:outline-none"
      :placeholder="__('Paste the call transcript here, then Analyze (or add a Note and leave this blank).')"
    />

    <div v-if="summary" class="mt-2 rounded-md bg-surface-white p-2.5 text-ink-gray-7">
      <div>{{ summary }}</div>
      <div v-if="objections.length" class="mt-1.5">
        <span class="font-medium text-ink-gray-8">{{ __('Objections') }}:</span>
        <ul class="list-disc space-y-0.5 pl-5"><li v-for="(o,i) in objections" :key="i">{{ o }}</li></ul>
      </div>
      <div v-if="competitors.length" class="mt-1.5">
        <span class="font-medium text-ink-gray-8">{{ __('Competitors') }}:</span> {{ competitors.join(', ') }}
      </div>
      <div v-if="nextStep" class="mt-1.5">
        <span class="font-medium text-ink-gray-8">{{ __('Next') }}:</span> {{ nextStep }}
      </div>
    </div>
  </div>
</template>

<script setup>
// Plantvu Conversation Intelligence panel on the Call Log detail modal.
// Calls crm.api.conversation_intelligence.analyze_call_log (core call_claude).
import { ref, computed } from 'vue'
import { call, Button, toast } from 'frappe-ui'
import LucideHeadphones from '~icons/lucide/headphones'
import LucideSparkles from '~icons/lucide/sparkles'

const props = defineProps({
  callLog: { type: String, required: true },
})

const busy = ref(false)
const transcript = ref('')
const summary = ref('')
const sentiment = ref('')
const objections = ref([])
const competitors = ref([])
const nextStep = ref('')

const sentimentClass = computed(() => {
  const s = (sentiment.value || '').toLowerCase()
  if (s === 'positive') return 'bg-surface-green-2 text-ink-green-3'
  if (s === 'negative') return 'bg-surface-red-2 text-ink-red-4'
  if (s === 'mixed') return 'bg-surface-amber-2 text-ink-amber-3'
  return 'bg-surface-gray-3 text-ink-gray-6'
})

async function analyze() {
  if (!props.callLog) {
    toast.error(__('No call selected.'))
    return
  }
  busy.value = true
  try {
    const r = await call('crm.api.conversation_intelligence.analyze_call_log', {
      call_log: props.callLog,
      transcript: transcript.value || undefined,
    })
    summary.value = r.summary
    sentiment.value = r.sentiment
    objections.value = r.objections || []
    competitors.value = r.competitor_mentions || []
    nextStep.value = r.next_step || ''
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Analysis failed'))
  } finally {
    busy.value = false
  }
}
</script>
