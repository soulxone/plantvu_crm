<template>
  <div class="flex h-full flex-col overflow-hidden" data-build="crmforecast-v1">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-2 text-lg font-semibold text-ink-gray-9">
          <LucideTrendingUp class="h-5 w-5 text-ink-teal-3" />
          {{ __('Forecast') }}
        </div>
      </template>
      <template #right-header>
        <Button :label="__('Refresh')" :loading="loading" @click="load">
          <template #prefix><LucideRefreshCcw class="h-4 w-4" /></template>
        </Button>
        <Button variant="solid" :label="__('AI narrative')" :loading="narrating" @click="narrate">
          <template #prefix><LucideSparkles class="h-4 w-4" /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto p-5">
      <div v-if="loading && !data" class="flex h-40 items-center justify-center">
        <LoadingIndicator class="h-6 w-6 text-ink-gray-5" />
      </div>

      <template v-else-if="data">
        <!-- scenario cards -->
        <div class="grid grid-cols-2 gap-3 md:grid-cols-5">
          <div v-for="c in cards" :key="c.key"
               class="rounded-lg border border-outline-gray-2 bg-surface-white p-3">
            <div class="text-xs uppercase tracking-wide text-ink-gray-5">{{ c.label }}</div>
            <div class="mt-1 text-xl font-bold" :class="c.color">{{ money(c.value) }}</div>
            <div v-if="c.sub" class="text-xs text-ink-gray-5">{{ c.sub }}</div>
          </div>
        </div>

        <div v-if="data.quota" class="mt-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-7">
          <span class="font-medium text-ink-gray-8">{{ __('Quota') }}:</span> {{ money(data.quota) }} ·
          <span class="font-medium text-ink-gray-8">{{ __('Gap (likely+won vs quota)') }}:</span>
          <span :class="data.gap_to_quota > 0 ? 'text-ink-red-4' : 'text-ink-green-3'">{{ money(data.gap_to_quota) }}</span>
        </div>

        <div v-if="narrative" class="mt-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3 text-sm text-ink-gray-7">
          <div class="mb-1 flex items-center gap-1.5 font-medium text-ink-gray-8">
            <LucideSparkles class="h-4 w-4 text-ink-teal-3" />{{ __('AI narrative') }}
          </div>
          {{ narrative }}
        </div>

        <!-- breakdowns -->
        <div class="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
          <ForecastTable :title="__('By Owner')" :rows="data.by_owner" :money="money" />
          <ForecastTable :title="__('By Stage')" :rows="data.by_stage" :money="money" />
          <ForecastTable :title="__('By Close Month')" :rows="data.by_month" :money="money" />
        </div>

        <div class="mt-4 text-xs text-ink-gray-5">
          {{ data.counts.open }} {{ __('open deals') }} · {{ data.counts.won }} {{ __('won this period') }}.
          {{ __('Likely = weighted (value × probability). Best = all open. Commit = probability ≥ 75%.') }}
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, h, onMounted } from 'vue'
import { call, Button, LoadingIndicator, toast } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LucideTrendingUp from '~icons/lucide/trending-up'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideSparkles from '~icons/lucide/sparkles'

// tiny presentational table, defined inline to avoid an extra file
const ForecastTable = (props) => h('div',
  { class: 'rounded-lg border border-outline-gray-2 bg-surface-white p-3' },
  [
    h('div', { class: 'mb-2 text-sm font-semibold text-ink-gray-8' }, props.title),
    (props.rows && props.rows.length)
      ? h('div', { class: 'flex flex-col gap-1' }, props.rows.map((r) =>
          h('div', { class: 'flex justify-between text-sm text-ink-gray-7' },
            [h('span', { class: 'truncate pr-2' }, r.key), h('span', { class: 'font-medium' }, props.money(r.value))])))
      : h('div', { class: 'text-sm text-ink-gray-5' }, '—'),
  ])

const data = ref(null)
const loading = ref(false)
const narrating = ref(false)
const narrative = ref('')

const cards = computed(() => {
  const s = data.value?.scenarios || {}
  return [
    { key: 'pipeline', label: 'Pipeline', value: s.pipeline, color: 'text-ink-gray-9' },
    { key: 'likely', label: 'Likely (weighted)', value: s.likely, color: 'text-ink-teal-3' },
    { key: 'best', label: 'Best case', value: s.best, color: 'text-ink-gray-9' },
    { key: 'commit', label: 'Commit', value: s.commit, color: 'text-ink-green-3' },
    { key: 'won', label: 'Won', value: s.won, color: 'text-ink-green-3' },
  ]
})

function money(v) {
  const cur = data.value?.currency || 'USD'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: cur, maximumFractionDigits: 0 }).format(v || 0)
  } catch (e) {
    return `${cur} ${Math.round(v || 0).toLocaleString()}`
  }
}

async function load() {
  loading.value = true
  try {
    data.value = await call('crm.api.forecast.get_forecast')
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Failed to load forecast'))
  } finally {
    loading.value = false
  }
}

async function narrate() {
  narrating.value = true
  try {
    const r = await call('crm.api.forecast.get_forecast_narrative')
    narrative.value = r.narrative
    if (r.data) data.value = r.data
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Narrative failed'))
  } finally {
    narrating.value = false
  }
}

onMounted(load)
</script>
