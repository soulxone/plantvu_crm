<template>
  <Dialog v-model="show" :options="{ size: '2xl', position: 'top' }">
    <template #body>
      <div data-build="crmsearch-v1">
        <div class="flex items-center gap-2 border-b px-4 py-3">
          <LucideSearch class="h-4 w-4 shrink-0 text-ink-gray-5" />
          <input
            ref="inputEl"
            v-model="query"
            type="text"
            class="w-full border-0 bg-transparent p-0 text-base text-ink-gray-8 placeholder-ink-gray-4 focus:ring-0"
            :placeholder="__('Search leads, deals, tasks, pages…')"
            @keydown.enter="onEnter"
            @keydown.escape="show = false"
          />
          <span class="shrink-0 rounded bg-surface-gray-2 px-1.5 py-0.5 text-xs text-ink-gray-5">esc</span>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 border-b px-4 py-2">
          <button
            v-for="chip in chips"
            :key="chip.kind"
            class="rounded-full px-2.5 py-1 text-xs font-medium transition"
            :class="
              activeKind === chip.kind
                ? 'bg-surface-gray-7 text-ink-white'
                : 'bg-surface-gray-2 text-ink-gray-6 hover:bg-surface-gray-3'
            "
            @click="activeKind = chip.kind"
          >
            {{ chip.label }}
          </button>
        </div>

        <div class="max-h-96 overflow-y-auto px-2 py-2">
          <!-- Ask lane -->
          <button
            v-if="looksLikeQuestion && !asking && !askAnswer"
            class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left hover:bg-surface-gray-1"
            @click="runAsk"
          >
            <LucideSparkles class="h-4 w-4 shrink-0 text-ink-violet-2" />
            <span class="text-base text-ink-violet-2">{{ __('Ask Plantvu') }}: “{{ query }}”</span>
          </button>
          <div v-if="asking" class="flex items-center gap-2.5 px-3 py-2.5">
            <LucideSparkles class="h-4 w-4 animate-pulse text-ink-violet-2" />
            <span class="text-base text-ink-gray-5">{{ __('Asking your workspace…') }}</span>
          </div>
          <div v-if="askAnswer" class="mb-2 rounded-lg border border-outline-violet-1 bg-surface-violet-1 px-3 py-2.5">
            <div class="whitespace-pre-wrap text-base text-ink-gray-8">{{ askAnswer }}</div>
            <div v-if="askCitations.length" class="mt-2 flex flex-wrap gap-1.5">
              <button
                v-for="(c, i) in askCitations"
                :key="i"
                class="rounded-full bg-surface-white px-2 py-0.5 text-xs font-medium text-ink-violet-2 shadow-sm"
                @click="openHit(c)"
              >
                {{ c.title }}
              </button>
            </div>
          </div>

          <!-- Result groups -->
          <template v-for="group in groups" :key="group.kind">
            <div class="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-ink-gray-4">
              {{ group.label }}
            </div>
            <button
              v-for="hit in group.items"
              :key="hit.id"
              class="flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left hover:bg-surface-gray-1"
              @click="openHit(hit)"
            >
              <component :is="kindIcon(hit.kind)" class="h-4 w-4 shrink-0 text-ink-gray-5" />
              <span class="min-w-0 truncate text-base text-ink-gray-8">{{ hit.title }}</span>
              <span v-if="hit.status" class="ml-auto shrink-0 text-xs font-medium" :class="toneClass(hit.status_tone)">
                {{ hit.status }}
              </span>
            </button>
          </template>

          <div v-if="searched && !groups.length && !asking && !askAnswer" class="px-3 py-6 text-center text-sm text-ink-gray-5">
            {{ __('No matches across the workspace.') }}
          </div>
          <div v-if="!query" class="px-3 py-6 text-center text-sm text-ink-gray-5">
            {{ __('Search everything — CRM, tasks, discussions, pages, orders.') }}
          </div>
        </div>
      </div>
    </template>
  </Dialog>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Dialog, call } from 'frappe-ui'
import { isSearchPaletteOpen } from '@/composables/useSearchPalette'
import LucideSearch from '~icons/lucide/search'
import LucideSparkles from '~icons/lucide/sparkles'
import LucideCircleCheck from '~icons/lucide/circle-check'
import LucideMessageCircle from '~icons/lucide/message-circle'
import LucideFiles from '~icons/lucide/files'
import LucideLayoutGrid from '~icons/lucide/layout-grid'
import LucideUser from '~icons/lucide/user'
import LucideBuilding from '~icons/lucide/building-2'
import LucideHandshake from '~icons/lucide/handshake'
import LucideUserPlus from '~icons/lucide/user-plus'
import LucideShoppingCart from '~icons/lucide/shopping-cart'
import LucidePackage from '~icons/lucide/package'
import LucidePaperclip from '~icons/lucide/paperclip'
import LucideTarget from '~icons/lucide/target'
import LucideBriefcase from '~icons/lucide/briefcase-business'

// Unified search palette for CRM (Tier 2 "CRM activation"): the same federated
// plantvu.search.unified backend the Connect palette uses — CRM hits route
// in-app, Connect hits jump to /g, desk hits to /app. Ctrl/Cmd+K to open.
const router = useRouter()
const show = isSearchPaletteOpen
const query = ref('')
const activeKind = ref('all')
const groups = ref([])
const searched = ref(false)
const chipData = ref(null)
const inputEl = ref(null)

const asking = ref(false)
const askAnswer = ref('')
const askCitations = ref([])

const KIND_ICONS = {
  task: LucideCircleCheck,
  discussion: LucideMessageCircle,
  page: LucideFiles,
  project: LucideLayoutGrid,
  person: LucideUser,
  customer: LucideBuilding,
  deal: LucideHandshake,
  lead: LucideUserPlus,
  order: LucideShoppingCart,
  item: LucidePackage,
  file: LucidePaperclip,
  goal: LucideTarget,
  portfolio: LucideBriefcase,
}

function kindIcon(kind) {
  return KIND_ICONS[kind] || LucideSearch
}

const chips = computed(() => {
  const enabled = (chipData.value || []).filter((k) => k.enabled)
  return [{ kind: 'all', label: __('All') }, ...enabled.map((k) => ({ kind: k.kind, label: k.label }))]
})

const looksLikeQuestion = computed(() => {
  const q = query.value.trim()
  return q.length > 12 && (q.endsWith('?') || /^(what|who|when|where|why|how|which|is|are|do|does|can|should)\b/i.test(q))
})

function toneClass(tone) {
  return (
    {
      in_progress: 'text-ink-blue-3',
      done: 'text-ink-green-3',
      canceled: 'text-ink-red-3',
    }[tone] || 'text-ink-gray-5'
  )
}

let timer = null
watch(query, () => {
  askAnswer.value = ''
  askCitations.value = []
  clearTimeout(timer)
  timer = setTimeout(search, 250)
})
watch(activeKind, search)

async function search() {
  const q = query.value.trim()
  if (q.length < 2) {
    groups.value = []
    searched.value = false
    return
  }
  const res = await call('plantvu.search.unified.unified', {
    query: q,
    kinds: activeKind.value === 'all' ? '' : activeKind.value,
    limit_per_kind: 5,
    mode: 'palette',
  })
  groups.value = res?.groups || []
  searched.value = true
}

async function runAsk() {
  asking.value = true
  askAnswer.value = ''
  askCitations.value = []
  try {
    const res = await call('plantvu.search.unified.ask', { query: query.value.trim() })
    askAnswer.value = res?.answer || __('The workspace had no content that answers this.')
    askCitations.value = res?.citations || []
  } catch (e) {
    askAnswer.value = e?.messages?.join?.('\n') || __('Ask failed — is Plantvu Assist enabled?')
  } finally {
    asking.value = false
  }
}

function onEnter() {
  if (looksLikeQuestion.value && !groups.value.length) {
    runAsk()
    return
  }
  const first = groups.value[0]?.items?.[0]
  if (first) openHit(first)
}

function openHit(hit) {
  show.value = false
  const name = hit.name
  if (hit.kind === 'lead') {
    router.push({ name: 'Lead', params: { leadId: name } })
  } else if (hit.kind === 'deal') {
    router.push({ name: 'Deal', params: { dealId: name } })
  } else if (hit.kind === 'task') {
    window.location.href = hit.project ? `/g/space/${hit.project}/tasks/${name}` : `/g/task/${name}`
  } else if (hit.kind === 'discussion') {
    window.location.href = `/g/space/${hit.project}/discussion/${name}`
  } else if (hit.kind === 'page') {
    window.location.href = `/g/page/${name}`
  } else if (hit.kind === 'project') {
    window.location.href = `/g/space/${name}`
  } else if (hit.kind === 'person') {
    window.location.href = `/g/people/${name}`
  } else if (hit.kind === 'goal') {
    window.location.href = '/g/goals'
  } else if (hit.kind === 'portfolio') {
    window.location.href = '/g/portfolios'
  } else if (hit.kind === 'file' && hit.file_url) {
    window.open(hit.file_url, '_blank')
  } else {
    const slug = (hit.doctype || '').toLowerCase().replace(/ /g, '-')
    window.location.href = `/app/${slug}/${encodeURIComponent(name)}`
  }
}

watch(show, async (open) => {
  if (open) {
    if (!chipData.value) {
      try {
        const res = await call('plantvu.search.unified.filter_options', {})
        chipData.value = res?.kinds || []
      } catch (e) {
        chipData.value = []
      }
    }
    await nextTick()
    inputEl.value?.focus()
  } else {
    query.value = ''
    groups.value = []
    askAnswer.value = ''
    askCitations.value = []
    activeKind.value = 'all'
    searched.value = false
  }
})

function onKeydown(e) {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    show.value = !show.value
  }
}
onMounted(() => window.addEventListener('keydown', onKeydown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeydown))
</script>
