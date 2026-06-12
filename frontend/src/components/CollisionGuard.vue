<template>
  <div
    v-if="activity.length"
    class="rounded-md border bg-surface-amber-1 border-outline-gray-2 px-3 py-2.5 text-sm"
    data-build="crmguard-v1"
  >
    <div class="flex items-center gap-1.5 font-medium text-ink-amber-3">
      <LucideUsers class="h-4 w-4 shrink-0" />
      {{ activity.length }} {{ __('recent touches on') }} {{ customerName }}
      {{ __('by others — coordinate before you act') }}
    </div>
    <ul class="mt-1.5 space-y-1 text-ink-gray-7">
      <li v-for="t in activity.slice(0, 6)" :key="t.doctype + t.name">
        <span class="font-medium">{{ shortUser(t.actor) }}</span>
        · {{ t.source }} · {{ fromNow(t.when) }} — {{ t.summary }}
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { call, dayjsLocal } from 'frappe-ui'
import LucideUsers from '~icons/lucide/users'

// Collision Guard (doc 20) on CRM lead/deal pages: shows what OTHER reps have
// recently done around this record's customer (tasks, emails, orders, other
// deals/leads on the same organization). Renders nothing when there is nothing.
const props = defineProps({
  doctype: { type: String, required: true },
  docname: { type: String, required: true },
})

const activity = ref([])
const customerName = ref('')

async function load() {
  activity.value = []
  customerName.value = ''
  try {
    const r = await call('plantvu.collision.aggregator.activity_for_crm', {
      doctype: props.doctype,
      name: props.docname,
    })
    customerName.value = r?.customer_name || ''
    activity.value = r?.activity || []
  } catch (e) {
    // best-effort — the guard must never break the page it sits on
  }
}

watch(() => [props.doctype, props.docname], load, { immediate: true })

function fromNow(w) {
  return dayjsLocal(w).fromNow()
}
function shortUser(u) {
  return (u || '').split('@')[0]
}
</script>
