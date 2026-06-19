<template>
  <div
    class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 text-sm"
    data-build="crmsequence-v1"
  >
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center gap-1.5 font-medium text-ink-gray-8">
        <LucideListChecks class="h-4 w-4 shrink-0 text-ink-teal-3" />
        {{ __('Sales Sequences') }}
      </div>
      <div class="ml-auto flex items-center gap-1.5">
        <select
          v-model="picked"
          class="rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-sm text-ink-gray-8"
        >
          <option value="">{{ __('Enroll in…') }}</option>
          <option v-for="s in sequences" :key="s.name" :value="s.name">
            {{ s.sequence_name }} ({{ s.step_count }})
          </option>
        </select>
        <Button :loading="busy === 'enroll'" :label="__('Enroll')" :disabled="!picked" @click="enroll" />
      </div>
    </div>

    <div v-if="enrollments.length" class="mt-2 flex flex-col gap-1.5">
      <div
        v-for="e in enrollments"
        :key="e.name"
        class="flex items-center gap-2 rounded-md bg-surface-white px-2.5 py-1.5 text-ink-gray-7"
      >
        <span class="font-medium text-ink-gray-8">{{ e.sequence }}</span>
        <span class="rounded-full px-2 py-0.5 text-xs font-semibold" :class="statusClass(e.status)">{{ e.status }}</span>
        <span class="text-xs text-ink-gray-5">{{ __('step') }} {{ (e.current_step_index || 0) + 1 }}</span>
        <span v-if="e.next_run" class="text-xs text-ink-gray-5">· {{ __('next') }} {{ shortDate(e.next_run) }}</span>
        <div class="ml-auto flex items-center gap-1">
          <Button v-if="e.status === 'Active'" variant="ghost" :label="__('Pause')" @click="act('pause_enrollment', e)" />
          <Button v-else-if="e.status === 'Paused'" variant="ghost" :label="__('Resume')" @click="act('resume_enrollment', e)" />
          <Button v-if="['Active','Paused'].includes(e.status)" variant="ghost" :label="__('Stop')" @click="act('unenroll_record', e)" />
        </div>
      </div>
    </div>
    <div v-else class="mt-1.5 text-xs text-ink-gray-5">{{ __('Not enrolled in any sequence.') }}</div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { call, Button, toast, dayjsLocal } from 'frappe-ui'
import LucideListChecks from '~icons/lucide/list-checks'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})

const enrollments = ref([])
const sequences = ref([])
const picked = ref('')
const busy = ref('')

function statusClass(s) {
  if (s === 'Active') return 'bg-surface-green-2 text-ink-green-3'
  if (s === 'Paused') return 'bg-surface-amber-2 text-ink-amber-3'
  if (s === 'Completed') return 'bg-surface-blue-2 text-ink-blue-3'
  return 'bg-surface-gray-3 text-ink-gray-6'
}
function shortDate(d) {
  try { return dayjsLocal(d).format('MMM D') } catch (e) { return d }
}

async function loadEnrollments() {
  try {
    enrollments.value = await call('crm.api.sequences.get_active_enrollments', {
      doctype: props.doctype, name: props.docname,
    })
  } catch (e) { /* best-effort */ }
}
async function loadSequences() {
  try {
    sequences.value = await call('crm.api.sequences.list_sequences', { only_enabled: true })
  } catch (e) { /* best-effort */ }
}

async function enroll() {
  if (!picked.value) return
  busy.value = 'enroll'
  try {
    await call('crm.api.sequences.enroll_record', {
      doctype: props.doctype, record_name: props.docname, sequence_name: picked.value,
    })
    picked.value = ''
    await loadEnrollments()
    toast.success(__('Enrolled'))
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Enroll failed'))
  } finally { busy.value = '' }
}

async function act(method, e) {
  try {
    await call(`crm.api.sequences.${method}`, { enrollment: e.name })
    await loadEnrollments()
  } catch (err) {
    toast.error(err?.messages?.[0] || err?.message || __('Action failed'))
  }
}

watch(() => [props.doctype, props.docname], () => { loadEnrollments() })
onMounted(() => { loadEnrollments(); loadSequences() })
</script>
