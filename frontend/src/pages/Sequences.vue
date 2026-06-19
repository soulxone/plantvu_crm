<template>
  <div class="flex h-full flex-col overflow-hidden" data-build="crmsequences-page-v1">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-2 text-lg font-semibold text-ink-gray-9">
          <LucideListChecks class="h-5 w-5 text-ink-teal-3" />
          {{ __('Sequences') }}
        </div>
      </template>
      <template #right-header>
        <Button variant="solid" :label="__('New sequence')" @click="newSequence">
          <template #prefix><LucidePlus class="h-4 w-4" /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex-1 overflow-y-auto p-5">
      <!-- editor -->
      <div v-if="editing" class="mb-5 rounded-lg border border-outline-gray-2 bg-surface-white p-4">
        <div class="flex flex-wrap items-center gap-3">
          <input v-model="form.sequence_name" :placeholder="__('Sequence name')"
                 class="flex-1 rounded border border-outline-gray-2 px-2 py-1.5 text-sm" />
          <label class="flex items-center gap-1.5 text-sm text-ink-gray-7">
            <input type="checkbox" v-model="form.enabled" /> {{ __('Enabled') }}
          </label>
        </div>
        <input v-model="form.description" :placeholder="__('Description')"
               class="mt-2 w-full rounded border border-outline-gray-2 px-2 py-1.5 text-sm" />

        <div class="mt-3 flex flex-col gap-2">
          <div v-for="(s, i) in form.steps" :key="i"
               class="rounded-md border border-outline-gray-2 bg-surface-gray-1 p-2.5">
            <div class="flex flex-wrap items-center gap-2 text-sm">
              <span class="font-medium text-ink-gray-8">{{ i + 1 }}.</span>
              <select v-model="s.action_type" class="rounded border border-outline-gray-2 px-2 py-1">
                <option>Email</option><option>Task</option><option>Call</option>
              </select>
              <label class="text-ink-gray-6">{{ __('wait') }}</label>
              <input type="number" min="0" v-model.number="s.wait_days" class="w-16 rounded border border-outline-gray-2 px-2 py-1" />
              <span class="text-ink-gray-6">{{ __('days') }}</span>
              <Button variant="ghost" class="ml-auto" :label="__('Remove')" @click="form.steps.splice(i, 1)" />
            </div>
            <template v-if="s.action_type === 'Email'">
              <input v-model="s.subject" :placeholder="__('Email subject')"
                     class="mt-2 w-full rounded border border-outline-gray-2 px-2 py-1 text-sm" />
              <textarea v-model="s.email_body" rows="2" :placeholder="__('Email body (supports {{ doc.first_name }})')"
                     class="mt-1 w-full rounded border border-outline-gray-2 px-2 py-1 text-sm"></textarea>
            </template>
            <template v-else>
              <input v-model="s.task_title" :placeholder="__('Task title')"
                     class="mt-2 w-full rounded border border-outline-gray-2 px-2 py-1 text-sm" />
              <input v-model="s.task_description" :placeholder="__('Task description')"
                     class="mt-1 w-full rounded border border-outline-gray-2 px-2 py-1 text-sm" />
            </template>
          </div>
        </div>

        <div class="mt-3 flex items-center gap-2">
          <Button :label="__('Add step')" @click="addStep">
            <template #prefix><LucidePlus class="h-4 w-4" /></template>
          </Button>
          <Button variant="solid" class="ml-auto" :loading="saving" :label="__('Save sequence')" @click="save" />
          <Button :label="__('Cancel')" @click="editing = false" />
        </div>
      </div>

      <!-- list -->
      <div class="flex flex-col gap-2">
        <div v-for="s in sequences" :key="s.name"
             class="flex items-center gap-3 rounded-lg border border-outline-gray-2 bg-surface-white px-4 py-3">
          <LucideListChecks class="h-4 w-4 text-ink-gray-5" />
          <div>
            <div class="font-medium text-ink-gray-8">{{ s.sequence_name }}</div>
            <div class="text-xs text-ink-gray-5">{{ s.description || '—' }}</div>
          </div>
          <span class="ml-2 text-xs text-ink-gray-5">{{ s.step_count }} {{ __('steps') }}</span>
          <span class="rounded-full px-2 py-0.5 text-xs font-semibold"
                :class="s.enabled ? 'bg-surface-green-2 text-ink-green-3' : 'bg-surface-gray-3 text-ink-gray-6'">
            {{ s.enabled ? __('Enabled') : __('Disabled') }}
          </span>
          <Button variant="ghost" class="ml-auto" :label="__('Edit')" @click="edit(s.name)" />
        </div>
        <div v-if="!sequences.length && !editing" class="text-sm text-ink-gray-5">
          {{ __('No sequences yet. Create one to start enrolling leads and deals.') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { call, Button, toast } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LucideListChecks from '~icons/lucide/list-checks'
import LucidePlus from '~icons/lucide/plus'

const sequences = ref([])
const editing = ref(false)
const saving = ref(false)
const form = ref({ name: null, sequence_name: '', description: '', enabled: true, steps: [] })

async function load() {
  try { sequences.value = await call('crm.api.sequences.list_sequences') } catch (e) { /* */ }
}
function newSequence() {
  form.value = { name: null, sequence_name: '', description: '', enabled: true, steps: [
    { action_type: 'Email', wait_days: 0, subject: '', email_body: '' },
  ] }
  editing.value = true
}
function addStep() {
  form.value.steps.push({ action_type: 'Email', wait_days: 2, subject: '', email_body: '' })
}
async function edit(name) {
  try {
    const d = await call('crm.api.sequences.get_sequence_details', { sequence_name: name })
    form.value = { name, sequence_name: d.sequence_name, description: d.description,
                   enabled: !!d.enabled, steps: d.steps?.length ? d.steps : [] }
    editing.value = true
  } catch (e) { toast.error(e?.messages?.[0] || __('Could not load')) }
}
async function save() {
  if (!form.value.sequence_name.trim()) { toast.error(__('Name required')); return }
  saving.value = true
  try {
    await call('crm.api.sequences.save_sequence', {
      name: form.value.name || undefined,
      sequence_name: form.value.sequence_name,
      description: form.value.description,
      enabled: form.value.enabled ? 1 : 0,
      steps: JSON.stringify(form.value.steps),
    })
    editing.value = false
    await load()
    toast.success(__('Saved'))
  } catch (e) {
    toast.error(e?.messages?.[0] || e?.message || __('Save failed'))
  } finally { saving.value = false }
}

onMounted(load)
</script>
