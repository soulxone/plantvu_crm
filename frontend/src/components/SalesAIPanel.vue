<template>
  <div
    class="rounded-md border border-outline-gray-2 bg-surface-gray-1 px-3 py-2.5 text-sm"
    data-build="crmsalesai-v1"
  >
    <!-- header + action buttons -->
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex items-center gap-1.5 font-medium text-ink-gray-8">
        <LucideSparkles class="h-4 w-4 shrink-0 text-ink-teal-3" />
        {{ __('Plantvu Sales AI') }}
        <span
          v-if="score !== null"
          class="ml-1 rounded-full px-2 py-0.5 text-xs font-semibold"
          :class="tierClass"
        >
          {{ score }} · {{ tier }}
        </span>
      </div>
      <div class="ml-auto flex flex-wrap items-center gap-1.5">
        <Button :loading="busy === 'score'" :label="__('Score')" @click="runScore">
          <template #prefix><LucideGauge class="h-4 w-4" /></template>
        </Button>
        <Button
          v-if="doctype === 'CRM Lead'"
          :loading="busy === 'qualify'"
          :label="__('Qualify')"
          @click="runQualify"
        >
          <template #prefix><LucideBadgeCheck class="h-4 w-4" /></template>
        </Button>
        <Button
          :loading="busy === 'compose'"
          :label="__('Draft email')"
          @click="showCompose = !showCompose"
        >
          <template #prefix><LucideMail class="h-4 w-4" /></template>
        </Button>
      </div>
    </div>

    <!-- score / qualify result -->
    <div v-if="summary" class="mt-2 text-ink-gray-7">
      <div>{{ summary }}</div>
      <ul v-if="reasons.length" class="mt-1.5 list-disc space-y-0.5 pl-5">
        <li v-for="(r, i) in reasons" :key="i">{{ r }}</li>
      </ul>
      <div v-if="nextAction" class="mt-1.5">
        <span class="font-medium text-ink-gray-8">{{ __('Next') }}:</span> {{ nextAction }}
      </div>
    </div>

    <!-- qualification block -->
    <div v-if="qualification" class="mt-2 rounded-md bg-surface-white p-2.5 text-ink-gray-7">
      <div class="font-medium text-ink-gray-8">
        {{ __('Verdict') }}: {{ qualification.verdict }}
      </div>
      <div class="mt-1 grid grid-cols-2 gap-x-4 gap-y-0.5">
        <div><b>{{ __('Budget') }}:</b> {{ qualification.budget }}</div>
        <div><b>{{ __('Authority') }}:</b> {{ qualification.authority }}</div>
        <div><b>{{ __('Need') }}:</b> {{ qualification.need }}</div>
        <div><b>{{ __('Timeline') }}:</b> {{ qualification.timeline }}</div>
      </div>
      <ul v-if="talkingPoints.length" class="mt-1.5 list-disc space-y-0.5 pl-5">
        <li v-for="(p, i) in talkingPoints" :key="i">{{ p }}</li>
      </ul>
    </div>

    <!-- compose box -->
    <div v-if="showCompose" class="mt-2 rounded-md bg-surface-white p-2.5">
      <textarea
        v-model="instruction"
        rows="2"
        class="w-full resize-y rounded border border-outline-gray-2 bg-surface-gray-1 p-2 text-sm text-ink-gray-8 focus:outline-none"
        :placeholder="__('What should this email say? e.g. follow up on the quote and propose a call next week')"
      />
      <div class="mt-1.5 flex items-center gap-1.5">
        <Button
          variant="solid"
          :loading="busy === 'compose'"
          :label="__('Generate')"
          @click="runCompose"
        />
        <Button v-if="draft" :label="__('Copy')" @click="copy(draft)">
          <template #prefix><LucideCopy class="h-4 w-4" /></template>
        </Button>
      </div>
    </div>

    <!-- draft email output (from compose or qualify) -->
    <div v-if="draft" class="mt-2 rounded-md bg-surface-white p-2.5">
      <div class="mb-1 flex items-center justify-between">
        <span class="text-xs font-medium uppercase tracking-wide text-ink-gray-5">
          {{ __('Draft email — review before sending') }}
        </span>
        <Button variant="ghost" :label="__('Copy')" @click="copy(draft)">
          <template #prefix><LucideCopy class="h-4 w-4" /></template>
        </Button>
      </div>
      <pre class="whitespace-pre-wrap break-words font-sans text-sm text-ink-gray-7">{{ draft }}</pre>
    </div>
  </div>
</template>

<script setup>
// Plantvu Sales AI panel on CRM Lead/Deal pages — Plantvu's answer to Dynamics
// 365 Sales' AI agents. Calls crm.api.sales_ai.* (which routes through the core
// plantvu call_claude choke-point). Best-effort: it must never break the page.
import { ref, computed, watch } from 'vue'
import { call, Button, toast } from 'frappe-ui'
import LucideSparkles from '~icons/lucide/sparkles'
import LucideGauge from '~icons/lucide/gauge'
import LucideBadgeCheck from '~icons/lucide/badge-check'
import LucideMail from '~icons/lucide/mail'
import LucideCopy from '~icons/lucide/copy'

const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})

const busy = ref('')
const score = ref(null)
const tier = ref('')
const summary = ref('')
const reasons = ref([])
const nextAction = ref('')
const qualification = ref(null)
const talkingPoints = ref([])
const draft = ref('')
const showCompose = ref(false)
const instruction = ref('')

const tierClass = computed(() => {
  const t = (tier.value || '').toLowerCase()
  if (t === 'hot') return 'bg-surface-red-2 text-ink-red-4'
  if (t === 'warm') return 'bg-surface-amber-2 text-ink-amber-3'
  if (t === 'cool') return 'bg-surface-blue-2 text-ink-blue-3'
  return 'bg-surface-gray-3 text-ink-gray-6'
})

function reset() {
  score.value = null; tier.value = ''; summary.value = ''
  reasons.value = []; nextAction.value = ''
  qualification.value = null; talkingPoints.value = []
  draft.value = ''; showCompose.value = false; instruction.value = ''
}
watch(() => [props.doctype, props.docname], reset)

function fail(e) {
  toast.error(e?.messages?.[0] || e?.message || __('Sales AI request failed'))
}

async function runScore() {
  busy.value = 'score'
  try {
    const r = await call('crm.api.sales_ai.score_record', {
      doctype: props.doctype,
      name: props.docname,
    })
    score.value = r.score; tier.value = r.tier
    summary.value = r.summary; reasons.value = r.reasons || []
    nextAction.value = r.next_action || ''
    qualification.value = null
  } catch (e) { fail(e) } finally { busy.value = '' }
}

async function runQualify() {
  busy.value = 'qualify'
  try {
    const r = await call('crm.api.sales_ai.qualify_lead', { name: props.docname })
    qualification.value = r.qualification
    talkingPoints.value = r.competitor_talking_points || []
    nextAction.value = r.recommended_next_action || ''
    summary.value = ''; reasons.value = []
    if (r.draft_email) {
      draft.value = `Subject: ${r.draft_email.subject}\n\n${r.draft_email.body}`
    }
  } catch (e) { fail(e) } finally { busy.value = '' }
}

async function runCompose() {
  if (!instruction.value.trim()) {
    toast.error(__('Tell the assistant what the email should say.'))
    return
  }
  busy.value = 'compose'
  try {
    const r = await call('crm.api.sales_ai.compose_email', {
      doctype: props.doctype,
      name: props.docname,
      instruction: instruction.value,
    })
    draft.value = r.draft || ''
  } catch (e) { fail(e) } finally { busy.value = '' }
}

async function copy(text) {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(__('Copied'))
  } catch (e) {
    toast.error(__('Could not copy'))
  }
}
</script>
