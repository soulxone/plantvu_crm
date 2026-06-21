<template>
  <div class="flex h-full flex-col overflow-hidden" data-build="crmmap-v1">
    <LayoutHeader>
      <template #left-header>
        <div class="flex items-center gap-2 text-lg font-semibold text-ink-gray-9">
          <LucideMapPinned class="h-5 w-5 text-ink-teal-3" />
          {{ __('Map') }}
          <span v-if="scopeLabel" class="text-sm font-normal text-ink-gray-5">· {{ scopeLabel }}</span>
        </div>
      </template>
      <template #right-header>
        <!-- manager-only rep filter -->
        <select
          v-if="settings?.is_manager"
          v-model="repFilter"
          class="form-select h-8 rounded border border-outline-gray-2 bg-surface-white text-sm"
          @change="loadRecords"
        >
          <option value="">{{ __('All reps') }}</option>
          <option value="__me__">{{ __('My records') }}</option>
          <option v-for="r in settings.reps" :key="r.id" :value="r.id">{{ r.name }}</option>
        </select>
        <Button
          v-if="settings?.is_manager"
          :label="drawingZone ? (drawPoints.length >= 3 ? `${__('Finish zone')} (${drawPoints.length})` : `${__('Click corners')} (${drawPoints.length}/3)`) : __('Draw zone')"
          :variant="drawingZone ? 'solid' : 'subtle'"
          @click="toggleDrawZone"
        >
          <template #prefix><LucideShapes class="h-4 w-4" /></template>
        </Button>
        <Button v-if="drawingZone" :label="__('Cancel')" variant="ghost" @click="cancelDrawing" />
        <Button v-if="settings?.is_manager" :label="__('Coverage')" :loading="recomputing" @click="recomputeCoverage">
          <template #prefix><LucideTarget class="h-4 w-4" /></template>
        </Button>
        <Button :label="__('Plan route')" :loading="routing" @click="planRoute">
          <template #prefix><LucideRoute class="h-4 w-4" /></template>
        </Button>
        <Button :label="__('Smart route')" variant="subtle" :loading="smartRouting" @click="planSmartRoute">
          <template #prefix><LucideSparkles class="h-4 w-4 text-ink-purple-3" /></template>
        </Button>
        <Button :label="__('Fit')" @click="fitAll">
          <template #prefix><LucideMaximize class="h-4 w-4" /></template>
        </Button>
        <Button :label="__('Reload')" :loading="loading" @click="loadRecords">
          <template #prefix><LucideRefreshCcw class="h-4 w-4" /></template>
        </Button>
      </template>
    </LayoutHeader>

    <div class="flex flex-1 overflow-hidden">
      <!-- Sidebar -->
      <div class="flex w-72 shrink-0 flex-col border-r border-outline-gray-2 bg-surface-white">
        <!-- search -->
        <div class="border-b border-outline-gray-2 p-3">
          <input
            ref="searchEl"
            type="text"
            class="form-input w-full text-sm"
            :placeholder="__('Search an address…')"
          />
        </div>

        <!-- layer toggles -->
        <div class="border-b border-outline-gray-2 p-3">
          <div class="mb-2 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">
            {{ __('Layers') }}
          </div>
          <label
            v-for="(meta, kind) in kindMeta"
            :key="kind"
            class="flex cursor-pointer items-center gap-2 py-1 text-sm text-ink-gray-7"
          >
            <input type="checkbox" :checked="activeKinds.has(kind)" @change="toggleKind(kind)" />
            <span class="inline-block h-3 w-3 rounded-full" :style="{ background: meta.color }" />
            {{ __(meta.label) }}
            <span class="ml-auto rounded-full bg-surface-gray-2 px-2 text-xs text-ink-gray-6">
              {{ counts[kind] || 0 }}
            </span>
          </label>

          <!-- plants + coverage -->
          <div class="mt-2 border-t border-outline-gray-1 pt-2">
            <div class="flex items-center gap-2 py-1 text-sm text-ink-gray-7">
              <input type="checkbox" v-model="showPlants" @change="renderPlants" />
              <span class="inline-block h-3 w-3 rounded-sm" style="background:#0B9E92" />
              {{ __('Plants') }}
              <span class="rounded-full bg-surface-gray-2 px-2 text-xs text-ink-gray-6">{{ plants.length }}</span>
              <button
                v-if="plants.length"
                class="ml-auto text-xs text-ink-blue-3 hover:underline"
                @click="showPlantList = !showPlantList"
              >{{ showPlantList ? __('hide') : __('select') }}</button>
            </div>
            <div class="flex items-center gap-2 py-1 text-sm text-ink-gray-7">
              <input type="checkbox" v-model="showCoverage" @change="renderPlants" />
              <span class="inline-block h-3 w-3 rounded-full border border-dashed" style="border-color:#1FA85A" />
              {{ __('Coverage rings') }}
              <button class="ml-auto text-xs text-ink-blue-3 hover:underline" @click="showRingList = !showRingList">
                {{ showRingList ? __('hide') : __('select') }}
              </button>
            </div>
            <div v-if="showRingList" class="mb-1 ml-5 flex flex-col gap-1 border-l border-outline-gray-1 pl-2">
              <label v-for="b in ringBands" :key="b.mi" class="flex cursor-pointer items-center gap-2 text-xs text-ink-gray-7">
                <input type="checkbox" v-model="b.on" :disabled="!showCoverage" @change="renderPlants" />
                <span class="inline-block h-2.5 w-2.5 rounded-full border" :style="{ borderColor: b.color }" />
                {{ b.mi }} {{ __('mi') }}
              </label>
              <label class="flex cursor-pointer items-center gap-2 text-xs text-ink-gray-7">
                <input type="checkbox" v-model="customRing.on" :disabled="!showCoverage" @change="renderPlants" />
                <span class="inline-block h-2.5 w-2.5 rounded-full border" :style="{ borderColor: customRing.color }" />
                {{ __('Custom') }}
                <input type="number" min="1" v-model.number="customRing.mi" :disabled="!showCoverage" class="form-input h-6 w-16 text-xs" @change="renderPlants" />
                {{ __('mi') }}
              </label>
            </div>
            <label class="flex cursor-pointer items-center gap-2 py-1 text-sm text-ink-gray-7">
              <input type="checkbox" v-model="showZones" @change="renderZones" />
              <span class="inline-block h-3 w-3 rounded-sm" style="background:#3F51B5;opacity:0.4" />
              {{ __('Zones') }}
              <span class="ml-auto rounded-full bg-surface-gray-2 px-2 text-xs text-ink-gray-6">{{ zones.length }}</span>
            </label>
            <label v-if="settings?.is_manager" class="flex cursor-pointer items-center gap-2 py-1 text-sm text-ink-gray-7">
              <input type="checkbox" :checked="showCompetitors" @change="toggleCompetitors" />
              <span class="inline-block" style="color:#C62828">◆</span>
              {{ __('Competitors') }}
              <span class="ml-auto rounded-full bg-surface-gray-2 px-2 text-xs text-ink-gray-6">{{ competitors.length }}</span>
            </label>

            <!-- per-plant show/hide (like the customer list) -->
            <div v-if="showPlantList" class="mt-1 max-h-44 overflow-y-auto rounded border border-outline-gray-1">
              <div class="flex items-center gap-2 border-b border-outline-gray-1 px-2 py-1 text-xs text-ink-gray-5">
                <button class="hover:underline" @click="setAllPlants(true)">{{ __('All') }}</button>
                <span>·</span>
                <button class="hover:underline" @click="setAllPlants(false)">{{ __('None') }}</button>
              </div>
              <label
                v-for="p in plants"
                :key="p.name"
                class="flex cursor-pointer items-center gap-2 px-2 py-1 text-xs text-ink-gray-7 hover:bg-surface-gray-1"
              >
                <input type="checkbox" :checked="plantShown(p)" @change="togglePlant(p)" />
                <img v-if="p.logo" :src="p.logo" class="h-3 w-auto max-w-6 object-contain" />
                <span v-else class="h-2.5 w-2.5 rounded-sm" :style="{ background: p.color || '#0B9E92' }" />
                <span class="truncate">{{ p.plant_name }}</span>
              </label>
            </div>
          </div>
        </div>

        <!-- stats -->
        <div class="border-b border-outline-gray-2 px-3 py-2 text-xs text-ink-gray-5">
          {{ records.length }} {{ __('records') }} · {{ mappedCount }} {{ __('mapped') }}
          <span v-if="geocoding" class="text-ink-amber-3"> · {{ __('geocoding…') }}</span>
        </div>

        <!-- list -->
        <div class="flex-1 overflow-y-auto">
          <div
            v-for="rec in visibleRecords.slice(0, 400)"
            :key="rec.id"
            class="flex items-center gap-2 border-b border-outline-gray-1 px-3 py-2 hover:bg-surface-gray-1"
            :class="inRoute(rec.id) ? 'bg-surface-gray-2' : ''"
          >
            <input
              type="checkbox"
              :checked="inRoute(rec.id)"
              :disabled="rec.lat == null"
              :title="__('Add to route')"
              @click.stop="toggleRoute(rec)"
            />
            <span class="h-2.5 w-2.5 shrink-0 rounded-full" :style="{ background: kindMeta[rec.kind].color }" />
            <div class="min-w-0 cursor-pointer" @click="focusRecord(rec)">
              <div class="truncate text-sm font-medium text-ink-gray-8">{{ rec.label }}</div>
              <div class="truncate text-xs text-ink-gray-5">{{ rec.sublabel || rec.address }}</div>
            </div>
            <LucideHelpCircle
              v-if="rec.lat == null"
              class="ml-auto h-3.5 w-3.5 text-ink-amber-3"
              :title="__('No location yet')"
            />
          </div>
          <div v-if="!loading && !visibleRecords.length" class="p-6 text-center text-sm text-ink-gray-4">
            {{ __('No records') }}
          </div>
        </div>
      </div>

      <!-- Map -->
      <div class="relative flex-1">
        <div ref="mapEl" class="h-full w-full" />

        <!-- route selection bar -->
        <div
          v-if="routeStops.length"
          class="absolute bottom-4 left-1/2 z-10 flex -translate-x-1/2 items-center gap-3 rounded-full border border-outline-gray-2 bg-surface-white px-4 py-2 shadow-lg"
        >
          <span class="text-sm font-medium text-ink-gray-8">
            {{ routeStops.length === 1 ? __('1 stop selected') : `${routeStops.length} ${__('stops selected')}` }}
          </span>
          <Button variant="solid" :loading="routing" @click="planRoute">
            <template #prefix><LucideRoute class="h-4 w-4" /></template>
            {{ routeStops.length === 1 ? __('Route to stop') : __('Route selected') }}
          </Button>
          <Button v-if="routeStops.length > 1" variant="subtle" :loading="smartRouting" @click="planSmartRoute">
            <template #prefix><LucideSparkles class="h-4 w-4 text-ink-purple-3" /></template>
            {{ __('Smart route') }}
          </Button>
          <Button variant="ghost" :label="__('Clear')" @click="clearRoute" />
        </div>

        <!-- Danczyk smart-route result -->
        <div
          v-if="smartResult"
          class="absolute right-4 top-4 z-10 flex max-h-[80%] w-80 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white shadow-xl"
        >
          <div class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3">
            <LucideSparkles class="h-4 w-4 text-ink-purple-3" />
            <span class="text-sm font-semibold text-ink-gray-9">{{ __('Smart route') }}</span>
            <span v-if="smartResult.ai_used" class="rounded-full bg-surface-purple-2 px-2 py-0.5 text-xs font-medium text-ink-purple-3">Danczyk</span>
            <button class="ml-auto text-ink-gray-5 hover:text-ink-gray-8" @click="smartResult = null">✕</button>
          </div>
          <div class="flex items-center gap-4 border-b border-outline-gray-2 px-4 py-2 text-xs text-ink-gray-7">
            <span><b class="text-ink-gray-9">{{ Math.round(smartResult.total_miles) }}</b> mi</span>
            <span>≈ <b class="text-ink-gray-9">${{ smartResult.est_cost }}</b> {{ __('drive cost') }}</span>
            <span class="text-ink-gray-5">${{ smartResult.mile_rate }}/mi</span>
          </div>
          <div class="overflow-y-auto px-4 py-3">
            <p class="mb-3 text-sm leading-snug text-ink-gray-7">{{ smartResult.rationale }}</p>
            <ol class="flex flex-col gap-2">
              <li v-for="s in smartResult.stops" :key="s.id" class="flex gap-2 text-sm">
                <span class="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-surface-gray-3 text-xs font-semibold text-ink-gray-8">{{ s.n }}</span>
                <div class="min-w-0">
                  <div class="flex items-center gap-1.5">
                    <span class="truncate font-medium text-ink-gray-9">{{ s.label }}</span>
                    <span v-if="s.priority === 'high'" class="rounded bg-surface-red-2 px-1 text-xs text-ink-red-3">{{ __('high') }}</span>
                  </div>
                  <div v-if="s.note" class="text-xs leading-snug text-ink-gray-6">{{ s.note }}</div>
                </div>
              </li>
            </ol>
            <div v-if="smartResult.deferred.length" class="mt-3 border-t border-outline-gray-2 pt-2">
              <div class="mb-1 text-xs font-semibold text-ink-gray-6">{{ __('Suggested to skip this trip') }}</div>
              <div v-for="d in smartResult.deferred" :key="d.id" class="truncate text-xs text-ink-gray-5">• {{ d.label }}</div>
            </div>
          </div>
        </div>

        <!-- Territory tools: Smart Leads + Battle Cards -->
        <div
          v-if="territory.open"
          class="absolute right-4 top-4 z-20 flex max-h-[86%] w-96 flex-col overflow-hidden rounded-xl border border-outline-gray-2 bg-surface-white shadow-xl"
        >
          <div class="flex items-center gap-2 border-b border-outline-gray-2 px-4 py-3">
            <LucideSparkles class="h-4 w-4 text-ink-purple-3" />
            <span class="text-sm font-semibold text-ink-gray-9">{{ __('Territory tools') }}</span>
            <span class="truncate text-xs text-ink-gray-5">{{ territory.label }}</span>
            <button class="ml-auto text-ink-gray-5 hover:text-ink-gray-8" @click="territory.open = false">✕</button>
          </div>
          <div v-if="territory.type === 'ring'" class="flex items-center gap-1.5 border-b border-outline-gray-2 px-4 py-2 text-xs">
            <span class="text-ink-gray-5">{{ __('Radius') }}:</span>
            <button v-for="mi in [25, 50, 100, 150]" :key="mi" @click="setRingRadius(mi)"
              :class="territory.radius_mi === mi ? 'bg-ink-purple-3 text-white' : 'bg-surface-gray-2 text-ink-gray-7'"
              class="rounded px-2 py-0.5 font-medium">{{ mi }} mi</button>
          </div>
          <div class="flex border-b border-outline-gray-2 text-sm">
            <button @click="territory.tab = 'smart'" :class="territory.tab === 'smart' ? 'border-ink-purple-3 text-ink-purple-3' : 'border-transparent text-ink-gray-6'" class="flex-1 border-b-2 py-2 font-medium">✨ {{ __('Smart Leads') }}</button>
            <button @click="territory.tab = 'battle'; battle.cards.length || loadBattleInArea()" :class="territory.tab === 'battle' ? 'border-ink-purple-3 text-ink-purple-3' : 'border-transparent text-ink-gray-6'" class="flex-1 border-b-2 py-2 font-medium">⚔ {{ __('Battle Cards') }}</button>
          </div>

          <div class="overflow-y-auto px-4 py-3">
            <!-- Smart Leads -->
            <template v-if="territory.tab === 'smart'">
              <Button class="w-full" variant="solid" :loading="smartLeads.loading" :label="__('Find prospects in this area')" @click="findSmartLeads" />
              <div v-if="smartLeads.candidates.length" class="mt-3 flex flex-col gap-1.5">
                <label v-for="c in smartLeads.candidates" :key="c.place_id" class="flex cursor-pointer items-start gap-2 rounded p-1 hover:bg-surface-gray-2">
                  <input type="checkbox" class="mt-1" :checked="smartLeads.selected.includes(c.place_id)" @change="toggleCand(c.place_id)" />
                  <div class="min-w-0">
                    <div class="truncate text-sm font-medium text-ink-gray-9">{{ c.name }}</div>
                    <div class="truncate text-xs text-ink-gray-5">{{ c.address }}<span v-if="c.category"> · {{ c.category }}</span><span v-if="c.rating"> · ★{{ c.rating }}</span></div>
                  </div>
                </label>
                <Button class="mt-1" variant="solid" :loading="smartLeads.adding" :disabled="!smartLeads.selected.length"
                  :label="`${__('Add')} ${smartLeads.selected.length} ${__('as Leads')}`" @click="addSmartLeads" />
              </div>
            </template>

            <!-- Battle Cards -->
            <template v-else>
              <div class="rounded-lg border border-outline-gray-2 p-2">
                <div class="mb-1 text-xs font-semibold text-ink-gray-7">{{ __('Add competitor') }}</div>
                <input v-model="battle.form.competitor_name" :placeholder="__('Competitor name')" class="form-input mb-1 w-full text-sm" />
                <input v-model="battle.form.address_line1" :placeholder="__('Street address')" class="form-input mb-1 w-full text-sm" />
                <div class="mb-1 flex gap-1">
                  <input v-model="battle.form.city" :placeholder="__('City')" class="form-input w-full text-sm" />
                  <input v-model="battle.form.state" placeholder="ST" class="form-input w-14 text-sm" />
                  <input v-model="battle.form.pincode" placeholder="ZIP" class="form-input w-20 text-sm" />
                </div>
                <input v-model="battle.form.website" :placeholder="__('Website (optional)')" class="form-input mb-1 w-full text-sm" />
                <Button class="w-full" variant="subtle" :loading="battle.adding" :label="__('Save competitor')" @click="saveCompetitor" />
              </div>
              <div class="mt-3 mb-1 text-xs font-semibold text-ink-gray-6">{{ __('Competitors in this area') }}</div>
              <div v-if="battle.loading" class="text-xs text-ink-gray-5">{{ __('Loading…') }}</div>
              <div v-else-if="!battle.cards.length" class="text-xs text-ink-gray-5">{{ __('None yet — add one above.') }}</div>
              <div v-for="c in battle.cards" :key="c.name" class="flex items-center gap-2 border-t border-outline-gray-1 py-1.5">
                <span style="color:#C62828">◆</span>
                <span class="flex-1 truncate text-sm text-ink-gray-9">{{ c.competitor_name }}</span>
                <button v-if="!c.ai_generated" class="text-xs font-medium text-ink-purple-3 hover:underline" :disabled="battle.generating === c.name" @click="generateCard(c.name)">{{ battle.generating === c.name ? '…' : '✨ ' + __('Create card') }}</button>
                <button class="text-xs text-ink-blue-3 hover:underline" @click="viewCard(c)">{{ __('View') }}</button>
              </div>
            </template>
          </div>
        </div>

        <!-- Battle card detail -->
        <div v-if="battle.active" class="absolute inset-x-4 bottom-4 z-30 max-h-[72%] overflow-y-auto rounded-xl border border-outline-gray-2 bg-surface-white p-4 shadow-2xl">
          <div class="mb-3 flex items-center gap-2">
            <span style="color:#C62828">⚔</span>
            <span class="font-semibold text-ink-gray-9">{{ battle.active.competitor_name }}</span>
            <span v-if="battle.active.industry" class="text-xs text-ink-gray-5">{{ battle.active.industry }}</span>
            <span v-if="battle.active.ai_generated" class="rounded-full bg-surface-purple-2 px-2 py-0.5 text-xs font-medium text-ink-purple-3">Danczyk</span>
            <a v-if="battle.active.website" :href="battle.active.website" target="_blank" class="text-xs text-ink-blue-3 hover:underline">{{ __('website') }}</a>
            <button class="ml-auto text-ink-gray-5 hover:text-ink-gray-8" @click="battle.active = null">✕</button>
          </div>
          <Button v-if="!battle.active.overview && !battle.active.how_we_win" variant="solid"
            :loading="battle.generating === battle.active.name" :label="`✨ ${__('Create battle card')}`" @click="generateCard(battle.active.name)" />
          <div v-else class="grid grid-cols-2 gap-x-5 gap-y-3 text-sm text-ink-gray-7">
            <div><div class="mb-0.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __('Who they are') }}</div><p class="leading-snug">{{ battle.active.overview }}</p></div>
            <div><div class="mb-0.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __('How we win') }}</div><p class="whitespace-pre-line leading-snug">{{ battle.active.how_we_win }}</p></div>
            <div><div class="mb-0.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __("Where they're strong") }}</div><p class="whitespace-pre-line leading-snug">{{ battle.active.watch_outs }}</p></div>
            <div><div class="mb-0.5 text-xs font-semibold uppercase tracking-wide text-ink-gray-5">{{ __('Proof points / talk track') }}</div><p class="whitespace-pre-line leading-snug">{{ battle.active.proof_points }}</p></div>
          </div>
        </div>

        <div
          v-if="!mapReady"
          class="absolute inset-0 flex items-center justify-center bg-surface-white/80"
        >
          <div class="text-center text-ink-gray-5">
            <LoadingIndicator class="mx-auto mb-2 h-6 w-6" />
            <div v-if="keyMissing" class="max-w-xs text-sm">
              {{ __('No Google Maps API key. Set it in CRM Settings → Map.') }}
            </div>
            <div v-else class="text-sm">{{ __('Loading Google Maps…') }}</div>
          </div>
        </div>
      </div>
    </div>

    <!-- Zone save dialog -->
    <Dialog v-model="zoneDialog.show" :options="{ title: __('New Zone') }">
      <template #body-content>
        <div class="flex flex-col gap-3">
          <FormControl v-model="zoneDialog.zone_name" type="text" :label="__('Zone name')" :placeholder="__('e.g. Memphis Metro')" />
          <FormControl v-model="zoneDialog.territory" type="text" :label="__('Territory')" :placeholder="__('e.g. Mid-South')" />
          <div>
            <div class="mb-1 text-xs text-ink-gray-5">{{ __('Plant') }}</div>
            <select v-model="zoneDialog.plant" class="form-select w-full rounded border border-outline-gray-2 bg-surface-white text-sm">
              <option value="">{{ __('— none —') }}</option>
              <option v-for="p in plants" :key="p.name" :value="p.name">{{ p.plant_name }}</option>
            </select>
          </div>
          <div>
            <div class="mb-1 text-xs text-ink-gray-5">{{ __('Assigned rep') }}</div>
            <select v-model="zoneDialog.assigned_rep" class="form-select w-full rounded border border-outline-gray-2 bg-surface-white text-sm">
              <option value="">{{ __('— none —') }}</option>
              <option v-for="r in (settings?.reps || [])" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
          </div>
          <div class="flex items-center gap-2">
            <span class="text-xs text-ink-gray-5">{{ __('Color') }}</span>
            <input type="color" v-model="zoneDialog.color" class="h-8 w-12 rounded border border-outline-gray-2" />
            <span class="text-xs text-ink-gray-5">{{ zoneDialog.points.length }} {{ __('vertices') }}</span>
          </div>
        </div>
      </template>
      <template #actions>
        <Button variant="solid" class="w-full" :label="__('Save zone')" @click="saveZone" />
      </template>
    </Dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { call, Button, LoadingIndicator, Dialog, FormControl, toast } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LucideMapPinned from '~icons/lucide/map-pinned'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideMaximize from '~icons/lucide/maximize'
import LucideRoute from '~icons/lucide/route'
import LucideHelpCircle from '~icons/lucide/help-circle'
import LucideTarget from '~icons/lucide/target'
import LucideShapes from '~icons/lucide/shapes'
import LucideSparkles from '~icons/lucide/sparkles'

const router = useRouter()

const KIND_META = {
  lead: { label: 'Leads', color: '#FF9800' },
  customer: { label: 'Customers', color: '#0B9E92' },
  organization: { label: 'Organizations', color: '#7C4DFF' },
  deal: { label: 'Deals', color: '#3F51B5' },
}
const kindMeta = KIND_META

const mapEl = ref(null)
const searchEl = ref(null)
const settings = ref(null)
const records = ref([])
const loading = ref(false)
const routing = ref(false)
const smartRouting = ref(false)
const smartResult = ref(null) // Danczyk smart-route result panel
const geocoding = ref(false)
const mapReady = ref(false)
const keyMissing = ref(false)
const repFilter = ref('')
const activeKinds = reactive(new Set(['lead', 'customer', 'organization', 'deal']))
const counts = reactive({})
const plants = ref([])
const showPlants = ref(true)
const showCoverage = ref(true)
const showRingList = ref(false)
// selectable coverage-ring distances (miles) — toggle each on/off at will
const ringBands = reactive([
  { mi: 25, on: false, color: '#0B9E92' },
  { mi: 50, on: true, color: '#1FA85A' },
  { mi: 100, on: true, color: '#F0A000' },
  { mi: 150, on: true, color: '#E0533B' },
])
const customRing = reactive({ mi: 200, on: false, color: '#3F51B5' })
const recomputing = ref(false)
const hiddenPlants = reactive(new Set()) // plant names toggled off
const showPlantList = ref(false)
const zones = ref([])
const showZones = ref(true)
const drawingZone = ref(false)
const zoneDialog = reactive({ show: false, points: [], name: null, zone_name: '', territory: '', plant: '', assigned_rep: '', color: '#3F51B5' })
const routeStops = ref([]) // selected record ids, in pick order

/* ── Territory tools: Smart Leads + Battle Cards (off a ring/zone) ──────────── */
const showCompetitors = ref(false)
const competitors = ref([]) // all battle cards (competitor pins)
let competitorOverlays = []
const territory = reactive({ open: false, type: null, label: '', lat: null, lng: null, radius_mi: 50, points: null, tab: 'smart' })
const smartLeads = reactive({ loading: false, candidates: [], selected: [], adding: false })
const battle = reactive({ loading: false, cards: [], active: null, adding: false, generating: '',
  form: { competitor_name: '', website: '', industry: '', address_line1: '', city: '', state: '', pincode: '' } })

let map = null
let infoWindow = null
let dirService = null
let dirRenderer = null
let geocoder = null
let homeMarker = null
const markers = {} // id -> google.maps.Marker
let plantOverlays = [] // markers + circles for plants/coverage
let zoneOverlays = [] // zone polygons
const drawPoints = ref([]) // vertices while manually drawing a zone
let drawClickListener = null
let drawDblListener = null
let tempPolygon = null

const mappedCount = computed(() => records.value.filter((r) => r.lat != null).length)

const scopeLabel = computed(() => {
  if (!settings.value) return ''
  if (!settings.value.is_manager) return __('My customers')
  if (repFilter.value === '__me__') return __('My records')
  if (repFilter.value) {
    const r = settings.value.reps.find((x) => x.id === repFilter.value)
    return r ? r.name : repFilter.value
  }
  return __('All reps')
})

const visibleRecords = computed(() =>
  records.value.filter((r) => activeKinds.has(r.kind)),
)

/* ── bootstrap ─────────────────────────────────────────────────────────── */
onMounted(async () => {
  try {
    settings.value = await call('crm.api.maps.get_map_settings')
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Failed to load map settings'))
    return
  }
  if (!settings.value.api_key) {
    keyMissing.value = true
    return
  }
  try {
    await loadGoogle(settings.value.api_key)
    initMap()
    loadPlants()
    loadZones()
    if (settings.value?.is_manager) loadCompetitors()
    await loadRecords()
  } catch (e) {
    toast.error(__('Failed to load Google Maps'))
  }
})

function loadGoogle(key) {
  return new Promise((resolve, reject) => {
    if (window.google && window.google.maps) return resolve()
    window.__crmInitMap = () => resolve()
    const s = document.createElement('script')
    s.src =
      `https://maps.googleapis.com/maps/api/js?key=${key}` +
      `&libraries=places,geometry,drawing&callback=__crmInitMap&loading=async`
    s.async = true
    s.onerror = reject
    document.head.appendChild(s)
  })
}

function initMap() {
  const home = settings.value.home || {}
  const center =
    home.lat && home.lng ? { lat: home.lat, lng: home.lng } : { lat: 39.5, lng: -98.35 }
  map = new google.maps.Map(mapEl.value, {
    center,
    zoom: home.lat ? 8 : 5,
    mapTypeControl: true,
    streetViewControl: false,
    fullscreenControl: true,
    gestureHandling: 'greedy',
    styles: [{ featureType: 'poi', elementType: 'labels', stylers: [{ visibility: 'off' }] }],
  })
  infoWindow = new google.maps.InfoWindow()
  geocoder = new google.maps.Geocoder()
  dirService = new google.maps.DirectionsService()
  dirRenderer = new google.maps.DirectionsRenderer({ suppressMarkers: true, map })
  mapReady.value = true

  if (home.lat && home.lng) {
    homeMarker = new google.maps.Marker({
      map,
      position: { lat: home.lat, lng: home.lng },
      title: __('Home base'),
      icon: { path: google.maps.SymbolPath.CIRCLE, scale: 8, fillColor: '#111', fillOpacity: 1, strokeColor: '#fff', strokeWeight: 3 },
      zIndex: 9999,
    })
  }
  setupSearch()
}

/* ── plants & radius coverage (Phase 2a) ───────────────────────────────────── */
const MI_TO_M = 1609.34
async function loadPlants() {
  try {
    plants.value = await call('crm.api.maps.get_plants')
    renderPlants()
  } catch (e) { /* plants optional */ }
}

function clearPlants() {
  plantOverlays.forEach((o) => o.setMap(null))
  plantOverlays = []
}

// the enabled ring distances, largest first so smaller rings layer on top
function activeRingBands() {
  const out = ringBands.filter((b) => b.on && b.mi > 0).map((b) => ({ mi: b.mi, color: b.color }))
  if (customRing.on && customRing.mi > 0) out.push({ mi: customRing.mi, color: customRing.color })
  return out.sort((a, b) => b.mi - a.mi)
}

function renderPlants() {
  clearPlants()
  if (!showPlants.value) return
  plants.value.forEach((p) => {
    if (p.latitude == null || p.longitude == null) return
    if (hiddenPlants.has(p.name)) return
    const center = { lat: p.latitude, lng: p.longitude }
    if (showCoverage.value) {
      // draw the user-selected ring distances (largest first so smaller sit on top)
      const bands = activeRingBands()
      bands.forEach((b) => {
        const circle = new google.maps.Circle({
          map, center, radius: b.mi * MI_TO_M,
          strokeColor: b.color, strokeOpacity: 0.55, strokeWeight: 1,
          fillColor: b.color, fillOpacity: 0.05, clickable: false, zIndex: 1,
        })
        plantOverlays.push(circle)
      })
    }
    const icon = p.logo
      ? { url: p.logo, scaledSize: new google.maps.Size(52, 30), anchor: new google.maps.Point(26, 15) }
      : {
          url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(
            `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22"><rect x="3" y="3" width="16" height="16" rx="3" fill="${p.color || '#0B9E92'}" stroke="#fff" stroke-width="2"/></svg>`),
          scaledSize: new google.maps.Size(22, 22),
          anchor: new google.maps.Point(11, 11),
        }
    const marker = new google.maps.Marker({
      map, position: center, title: `${p.plant_name} (plant)`,
      zIndex: 8000, icon,
    })
    marker.addListener('click', () => {
      infoWindow.setContent(
        `<div style="min-width:180px">` +
        (p.logo ? `<img src="${escapeHtml(p.logo)}" alt="" style="height:30px;max-width:150px;object-fit:contain;display:block;margin:0 0 6px" />` : '') +
        `<strong>${escapeHtml(p.plant_name)}</strong>` +
        (p.company ? `<div style="font-size:12px;color:#666">${escapeHtml(p.company)}</div>` : '') +
        (p.address ? `<div style="font-size:12px;color:#444;margin:4px 0">${escapeHtml(p.address)}</div>` : '') +
        `<div style="font-size:12px;color:#555">Coverage: ${p.radius_green_mi||0}/${p.radius_yellow_mi||0}/${p.radius_red_mi||0} mi</div>` +
        (settings.value?.is_manager
          ? `<div style="margin-top:6px"><a href="#" id="crm-terr-plant" style="font-size:12px;font-weight:600;color:#7C4DFF">✨ Territory tools</a></div>` : '') +
        `</div>`)
      infoWindow.open(map, marker)
      google.maps.event.addListenerOnce(infoWindow, 'domready', () => {
        const a = document.getElementById('crm-terr-plant')
        if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); infoWindow.close(); openTerritoryRing(p, p.radius_red_mi || 50) })
      })
    })
    plantOverlays.push(marker)
  })
}

function plantShown(p) { return !hiddenPlants.has(p.name) }
function togglePlant(p) {
  if (hiddenPlants.has(p.name)) hiddenPlants.delete(p.name)
  else hiddenPlants.add(p.name)
  renderPlants()
}
function setAllPlants(show) {
  hiddenPlants.clear()
  if (!show) plants.value.forEach((p) => hiddenPlants.add(p.name))
  renderPlants()
}

/* ── zones (drawn territory polygons, Phase 2b) ────────────────────────────── */
async function loadZones() {
  try { zones.value = await call('crm.api.maps.get_zones'); renderZones() }
  catch (e) { /* zones optional */ }
}
function clearZones() { zoneOverlays.forEach((o) => o.setMap(null)); zoneOverlays = [] }
function renderZones() {
  clearZones()
  if (!showZones.value) return
  zones.value.forEach((z) => {
    if (!z.points || z.points.length < 3) return
    const poly = new google.maps.Polygon({
      map,
      paths: z.points.map((pt) => ({ lat: pt[0], lng: pt[1] })),
      strokeColor: z.color || '#3F51B5', strokeOpacity: 0.8, strokeWeight: 2,
      fillColor: z.color || '#3F51B5', fillOpacity: 0.12, zIndex: 2,
    })
    poly.addListener('click', (e) => {
      const plantName = (plants.value.find((p) => p.name === z.plant) || {}).plant_name || z.plant || '—'
      const rep = (settings.value?.reps || []).find((r) => r.id === z.assigned_rep)
      infoWindow.setContent(
        `<div style="min-width:180px"><strong>${escapeHtml(z.zone_name)}</strong>` +
        (z.territory ? `<div style="font-size:12px;color:#666">${escapeHtml(z.territory)}</div>` : '') +
        `<div style="font-size:12px;color:#555;margin-top:3px">Plant: <b>${escapeHtml(plantName)}</b></div>` +
        (rep ? `<div style="font-size:12px;color:#555">Rep: <b>${escapeHtml(rep.name)}</b></div>` : '') +
        (settings.value?.is_manager
          ? `<div style="margin-top:6px;display:flex;gap:12px">` +
            `<a href="#" id="crm-terr-zone" style="font-size:12px;font-weight:600;color:#7C4DFF">✨ Territory tools</a>` +
            `<a href="#" id="crm-zone-del" style="font-size:12px;font-weight:600;color:#E0533B">Delete zone</a></div>` : '') +
        `</div>`)
      infoWindow.setPosition(e.latLng)
      infoWindow.open(map)
      google.maps.event.addListenerOnce(infoWindow, 'domready', () => {
        const a = document.getElementById('crm-zone-del')
        if (a) a.addEventListener('click', (ev) => { ev.preventDefault(); deleteZone(z) })
        const t = document.getElementById('crm-terr-zone')
        if (t) t.addEventListener('click', (ev) => { ev.preventDefault(); infoWindow.close(); openTerritoryZone(z) })
      })
    })
    zoneOverlays.push(poly)
  })
}

// Google removed DrawingManager in Maps JS v3.65, so draw polygons manually with
// core map click events: each click drops a vertex, "Finish zone" closes it.
function toggleDrawZone() {
  if (drawingZone.value) finishDrawing()
  else startDrawing()
}

function startDrawing() {
  drawingZone.value = true
  drawPoints.value = []
  if (tempPolygon) tempPolygon.setMap(null)
  tempPolygon = new google.maps.Polygon({
    map, paths: [], fillColor: '#3F51B5', fillOpacity: 0.15,
    strokeColor: '#3F51B5', strokeWeight: 2, clickable: false, zIndex: 5,
  })
  map.setOptions({ disableDoubleClickZoom: true })
  drawClickListener = map.addListener('click', (e) => {
    drawPoints.value.push({ lat: e.latLng.lat(), lng: e.latLng.lng() })
    tempPolygon.setPath(drawPoints.value)
  })
  drawDblListener = map.addListener('dblclick', () => finishDrawing())
  toast.info(__('Click the map to add corners, then "Finish zone" (or double-click).'))
}

function cancelDrawing() {
  drawingZone.value = false
  if (drawClickListener) { drawClickListener.remove(); drawClickListener = null }
  if (drawDblListener) { drawDblListener.remove(); drawDblListener = null }
  if (tempPolygon) { tempPolygon.setMap(null); tempPolygon = null }
  drawPoints.value = []
  if (map) map.setOptions({ disableDoubleClickZoom: false })
}

function finishDrawing() {
  const pts = drawPoints.value.map((p) => [p.lat, p.lng])
  cancelDrawing()
  if (pts.length < 3) { toast.warning(__('A zone needs at least 3 corners')); return }
  Object.assign(zoneDialog, { show: true, points: pts, name: null, zone_name: '', territory: '', plant: '', assigned_rep: '', color: '#3F51B5' })
}

async function saveZone() {
  if (!zoneDialog.zone_name) { toast.warning(__('Zone name is required')); return }
  try {
    await call('crm.api.maps.save_zone', { zone: JSON.stringify({
      name: zoneDialog.name, zone_name: zoneDialog.zone_name, territory: zoneDialog.territory,
      plant: zoneDialog.plant || null, assigned_rep: zoneDialog.assigned_rep || null,
      color: zoneDialog.color, points: zoneDialog.points,
    }) })
    zoneDialog.show = false
    toast.success(__('Zone saved'))
    loadZones()
  } catch (e) { toast.error(e?.messages?.[0] || __('Save failed')) }
}

async function deleteZone(z) {
  try { await call('crm.api.maps.delete_zone', { name: z.name }); infoWindow.close(); loadZones() }
  catch (e) { toast.error(__('Delete failed')) }
}

async function recomputeCoverage() {
  recomputing.value = true
  try {
    const r = await call('crm.api.maps.recompute_assignments')
    if (r.error) toast.warning(r.error)
    else toast.success(`${__('Coverage')}: ${r.assigned} ${__('assigned')}, ${r.gaps} ${__('gaps')} (${r.plants} ${__('plants')})`)
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Recompute failed'))
  } finally {
    recomputing.value = false
  }
}

function setupSearch() {
  if (!searchEl.value || !google.maps.places) return
  const ac = new google.maps.places.Autocomplete(searchEl.value, { fields: ['geometry', 'name', 'formatted_address'] })
  ac.addListener('place_changed', () => {
    const place = ac.getPlace()
    if (!place.geometry) return
    if (place.geometry.viewport) map.fitBounds(place.geometry.viewport)
    else { map.setCenter(place.geometry.location); map.setZoom(15) }
    infoWindow.setContent(`<strong>${place.name || ''}</strong><br>${place.formatted_address || ''}`)
    infoWindow.setPosition(place.geometry.location)
    infoWindow.open(map)
  })
}

/* ── data ──────────────────────────────────────────────────────────────── */
async function loadRecords() {
  loading.value = true
  try {
    const rep = repFilter.value === '__me__' ? settings.value.current_user : repFilter.value
    const d = await call('crm.api.maps.get_map_records', {
      rep: rep || undefined,
      kinds: Array.from(activeKinds).join(','),
    })
    records.value = d.records || []
    updateCounts()
    renderMarkers()
    if (d.pending_geocode) geocodeLoop()
    else fitAll()
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Failed to load records'))
  } finally {
    loading.value = false
  }
}

function updateCounts() {
  for (const k of Object.keys(KIND_META)) counts[k] = 0
  records.value.forEach((r) => { counts[r.kind] = (counts[r.kind] || 0) + 1 })
}

// Geocode in the BROWSER (runs under the referrer-restricted key), then persist
// the results so a single, fully-locked-down key covers everything.
async function geocodeLoop() {
  const pending = records.value.filter(
    (r) => !r._geo && (r.address || '').trim() && r.lat == null,
  )
  if (!pending.length) { geocoding.value = false; fitAll(); return }
  geocoding.value = true
  const batch = pending.slice(0, 12)
  const resolved = {}
  for (const rec of batch) {
    const addr = rec.address.trim()
    rec._geo = true
    if (resolved[addr]) { applyCoords(addr, resolved[addr]); continue }
    const c = await geocodeOne(addr)
    if (c) { resolved[addr] = c; applyCoords(addr, c) }
  }
  renderMarkers()
  const found = Object.keys(resolved).length
  if (found) {
    call('crm.api.maps.save_geocodes', { resolved: JSON.stringify(resolved) }).catch(() => {})
  }
  const stillPending = records.value.some(
    (r) => !r._geo && (r.address || '').trim() && r.lat == null,
  )
  if (stillPending) setTimeout(geocodeLoop, 150)
  else { geocoding.value = false; fitAll() }
}

function applyCoords(addr, c) {
  records.value.forEach((r) => {
    if ((r.address || '').trim() === addr) { r.lat = c.lat; r.lng = c.lng; r._geo = true }
  })
}

function geocodeOne(addr, tries = 0) {
  return new Promise((resolve) => {
    geocoder.geocode({ address: addr }, (results, status) => {
      if (status === 'OK' && results && results[0]) {
        const loc = results[0].geometry.location
        resolve({ lat: loc.lat(), lng: loc.lng() })
      } else if (status === 'OVER_QUERY_LIMIT' && tries < 3) {
        setTimeout(() => geocodeOne(addr, tries + 1).then(resolve), 500 * (tries + 1))
      } else {
        resolve(null)
      }
    })
  })
}

/* ── markers ───────────────────────────────────────────────────────────── */
function pinIcon(kind, selected) {
  const color = KIND_META[kind]?.color || '#666'
  const sel = !!selected
  // selected stops get a dark selection ring so they stand out for routing
  const ring = sel ? `<circle cx="13" cy="13" r="12" fill="none" stroke="#111" stroke-width="2.5"/>` : ''
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="38" viewBox="0 0 26 38">` +
    `<path d="M13 0C5.8 0 0 5.8 0 13c0 9 13 25 13 25s13-16 13-25C26 5.8 20.2 0 13 0z" fill="${color}"/>` +
    `<circle cx="13" cy="13" r="7.5" fill="#fff"/>${ring}</svg>`
  return {
    url: 'data:image/svg+xml;charset=UTF-8,' + encodeURIComponent(svg),
    scaledSize: new google.maps.Size(26, 38),
    anchor: new google.maps.Point(13, 38),
  }
}

function renderMarkers() {
  Object.values(markers).forEach((m) => m.setMap(null))
  for (const id of Object.keys(markers)) delete markers[id]
  records.value.forEach((rec) => {
    if (!activeKinds.has(rec.kind) || rec.lat == null || rec.lng == null) return
    const order = routeStops.value.indexOf(rec.id)
    const marker = new google.maps.Marker({
      map,
      position: { lat: rec.lat, lng: rec.lng },
      title: rec.label,
      icon: pinIcon(rec.kind, order >= 0),
      zIndex: order >= 0 ? 6000 : 100,
      label: order >= 0 ? { text: String(order + 1), color: '#111', fontSize: '10px', fontWeight: '700' } : undefined,
    })
    marker.addListener('click', () => openInfo(rec, marker))
    markers[rec.id] = marker
  })
}

function openInfo(rec, marker) {
  const color = KIND_META[rec.kind]?.color || '#666'
  const rawRoute = rec.route || ''
  // CRM SPA routes (/crm/...) navigate in-app; desk routes (/app/...) open a tab.
  const isCrm = rawRoute.startsWith('/crm')
  const route = isCrm ? rawRoute.replace(/^\/crm/, '') : rawRoute
  const html =
    `<div style="min-width:200px;font-family:inherit">` +
    `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">` +
    `<span style="background:${color};color:#fff;font-size:10px;font-weight:700;border-radius:4px;padding:1px 6px;text-transform:uppercase">${KIND_META[rec.kind]?.label || rec.kind}</span>` +
    `<strong>${escapeHtml(rec.label || '')}</strong></div>` +
    (rec.sublabel ? `<div style="font-size:12px;color:#666">${escapeHtml(rec.sublabel)}</div>` : '') +
    (rec.address ? `<div style="font-size:12px;color:#444;margin:4px 0">${escapeHtml(rec.address)}</div>` : '') +
    (rec.status ? `<div style="font-size:12px;color:#555">Status: <b>${escapeHtml(rec.status)}</b></div>` : '') +
    `<div style="display:flex;gap:10px;align-items:center;margin-top:4px;flex-wrap:wrap">` +
    `<a href="#" id="crm-map-route" style="font-size:12px;font-weight:600;color:${inRoute(rec.id) ? '#E0533B' : '#3F51B5'}">${inRoute(rec.id) ? '− Remove from route' : '+ Add to route'}</a>` +
    (route ? `<a href="#" id="crm-map-open" style="font-size:12px;font-weight:600;color:#0B9E92">Open record →</a>` : '') +
    (canEnrich(rec) ? `<a href="#" id="crm-map-enrich" style="font-size:12px;font-weight:600;color:#7C4DFF">✨ Enrich</a>` : '') +
    `</div></div>`
  infoWindow.setContent(html)
  infoWindow.open(map, marker)
  google.maps.event.addListenerOnce(infoWindow, 'domready', () => {
    const a = document.getElementById('crm-map-open')
    if (a) a.addEventListener('click', (e) => {
      e.preventDefault()
      if (isCrm) router.push(route)
      else window.open(route, '_blank')
    })
    const rt = document.getElementById('crm-map-route')
    if (rt) rt.addEventListener('click', (e) => { e.preventDefault(); toggleRoute(rec); infoWindow.close() })
    const en = document.getElementById('crm-map-enrich')
    if (en) en.addEventListener('click', (e) => { e.preventDefault(); enrichRecord(rec) })
  })
}

function canEnrich(rec) {
  return settings.value?.is_manager && ['customer', 'lead', 'organization'].includes(rec.kind) && rec.ref?.name
}

async function enrichRecord(rec) {
  toast.info(`${__('Enriching')} ${rec.label}…`)
  try {
    const r = await call('crm.api.enrichment.enrich_record', {
      reference_doctype: rec.ref.doctype, reference_name: rec.ref.name,
    })
    if (r.error) return toast.warning(r.error)
    if (!r.found) return toast.warning(`${rec.label}: ${__('no Google listing found')}`)
    const d = r.data || {}
    toast.success(`${d.business_name || rec.label}: ${[d.phone, d.category, d.rating && d.rating + '★'].filter(Boolean).join(' · ') || __('enriched')}`)
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Enrich failed (set the server key in Settings → Map)'))
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))
}

/* ── interactions ──────────────────────────────────────────────────────── */
function toggleKind(kind) {
  if (activeKinds.has(kind)) activeKinds.delete(kind)
  else activeKinds.add(kind)
  renderMarkers()
}

/* ── route stop selection ──────────────────────────────────────────────────── */
function inRoute(id) { return routeStops.value.includes(id) }
function toggleRoute(rec) {
  if (rec.lat == null) { toast.warning(`${rec.label}: ${__('no map location yet')}`); return }
  const i = routeStops.value.indexOf(rec.id)
  if (i >= 0) routeStops.value.splice(i, 1)
  else routeStops.value.push(rec.id)
  renderMarkers()
}
function clearRoute() {
  routeStops.value = []
  if (dirRenderer) dirRenderer.set('directions', null)
  renderMarkers()
}
const routeRecords = computed(() =>
  routeStops.value.map((id) => records.value.find((r) => r.id === id)).filter(Boolean),
)

function focusRecord(rec) {
  const m = markers[rec.id]
  if (m) { map.panTo(m.getPosition()); map.setZoom(13); openInfo(rec, m) }
  else toast.warning(`${rec.label}: ${__('no map location yet')}`)
}

function fitAll() {
  const list = Object.values(markers)
  if (!list.length) return
  const b = new google.maps.LatLngBounds()
  list.forEach((m) => b.extend(m.getPosition()))
  if (homeMarker) b.extend(homeMarker.getPosition())
  map.fitBounds(b)
  if (list.length === 1) map.setZoom(13)
}

/* Optimized travel route from home base through the SELECTED stops (or, if none
 * are selected, all visible mapped records). Select one for a point-to-point route. */
async function planRoute() {
  const home = settings.value?.home
  if (!home?.lat || !home?.lng) {
    toast.warning(__('Set a home base in CRM Settings → Map to plan a route'))
    return
  }
  const selected = routeRecords.value.filter((r) => r.lat != null)
  const stops = (selected.length ? selected : visibleRecords.value.filter((r) => r.lat != null)).slice(0, 24)
  if (stops.length < 1) { toast.warning(__('Select stops (pin → Add to route) or load mapped records')); return }
  routing.value = true
  try {
    const origin = { lat: home.lat, lng: home.lng }
    const waypoints = stops.slice(0, -1).map((s) => ({ location: { lat: s.lat, lng: s.lng }, stopover: true }))
    const destination = { lat: stops[stops.length - 1].lat, lng: stops[stops.length - 1].lng }
    const result = await dirService.route({
      origin,
      destination,
      waypoints,
      optimizeWaypoints: true,
      travelMode: google.maps.TravelMode.DRIVING,
    })
    dirRenderer.setDirections(result)
    const legs = result.routes[0].legs
    const miles = legs.reduce((a, l) => a + l.distance.value, 0) / 1609.34
    const mins = legs.reduce((a, l) => a + l.duration.value, 0) / 60
    toast.success(`${__('Route')}: ${stops.length} ${__('stops')} · ${miles.toFixed(0)} mi · ${(mins / 60).toFixed(1)} h`)
  } catch (e) {
    toast.error(__('Could not compute route'))
  } finally {
    routing.value = false
  }
}

/* Danczyk smart route: geo-optimal order (Directions) → AI re-ranks by deal
 * value/urgency vs drive cost → re-draw in the AI order + show rationale + cost. */
async function planSmartRoute() {
  const home = settings.value?.home
  const selected = routeRecords.value.filter((r) => r.lat != null)
  const pool = (selected.length ? selected : visibleRecords.value.filter((r) => r.lat != null)).slice(0, 24)
  if (pool.length < 2) { toast.warning(__('Pick at least 2 stops (pin → Add to route) for a smart route')); return }
  smartRouting.value = true
  try {
    const hasHome = !!(home?.lat && home?.lng)
    const origin = hasHome ? { lat: home.lat, lng: home.lng } : { lat: pool[0].lat, lng: pool[0].lng }
    const routeStopsArr = hasHome ? pool : pool.slice(1)
    const destStop = routeStopsArr[routeStopsArr.length - 1]
    const wpStops = routeStopsArr.slice(0, -1)
    let geoOrdered = pool
    let miles = 0
    try {
      const r = await dirService.route({
        origin, destination: { lat: destStop.lat, lng: destStop.lng },
        waypoints: wpStops.map((s) => ({ location: { lat: s.lat, lng: s.lng }, stopover: true })),
        optimizeWaypoints: true, travelMode: google.maps.TravelMode.DRIVING,
      })
      const wo = r.routes[0].waypoint_order || wpStops.map((_, i) => i)
      const head = hasHome ? [] : [pool[0]]
      geoOrdered = [...head, ...wo.map((i) => wpStops[i]), destStop].filter(Boolean)
      miles = r.routes[0].legs.reduce((a, l) => a + l.distance.value, 0) / 1609.34
    } catch (e) { geoOrdered = pool }

    const payload = geoOrdered.map((s) => ({ id: s.id, kind: s.kind, label: s.label, lat: s.lat, lng: s.lng }))
    const res = await call('crm.api.routing.plan_smart_route', { stops: JSON.stringify(payload), total_miles: miles.toFixed(1) })

    const byId = Object.fromEntries(pool.map((s) => [s.id, s]))
    const deferred = new Set(res.deferred || [])
    const finalStops = (res.order || []).map((id) => byId[id]).filter((s) => s && !deferred.has(s.id))

    // draw the AI-recommended order (no re-optimize)
    if (finalStops.length >= 1) {
      const o = hasHome ? { lat: home.lat, lng: home.lng } : { lat: finalStops[0].lat, lng: finalStops[0].lng }
      const body = hasHome ? finalStops : finalStops.slice(1)
      if (body.length >= 1) {
        try {
          const dr = await dirService.route({
            origin: o, destination: { lat: body[body.length - 1].lat, lng: body[body.length - 1].lng },
            waypoints: body.slice(0, -1).map((s) => ({ location: { lat: s.lat, lng: s.lng }, stopover: true })),
            optimizeWaypoints: false, travelMode: google.maps.TravelMode.DRIVING,
          })
          dirRenderer.setDirections(dr)
        } catch (e) { /* keep geo route drawn */ }
      }
    }

    const noteById = Object.fromEntries((res.stops || []).map((s) => [s.id, s]))
    smartResult.value = {
      ai_used: res.ai_used,
      rationale: res.rationale,
      est_cost: res.est_cost, total_miles: res.total_miles, mile_rate: res.mile_rate,
      stops: finalStops.map((s, i) => ({ n: i + 1, id: s.id, label: s.label, kind: s.kind, note: noteById[s.id]?.note || '', priority: noteById[s.id]?.priority || '' })),
      deferred: (res.deferred || []).map((id) => byId[id]).filter(Boolean).map((s) => ({ id: s.id, label: s.label })),
    }
    toast.success(res.ai_used ? __('Danczyk planned your route') : __('Route planned'))
  } catch (e) {
    toast.error(__('Smart route failed: ') + (e?.messages?.[0] || e?.message || e))
  } finally {
    smartRouting.value = false
  }
}

/* ── Territory tools ───────────────────────────────────────────────────────── */
async function loadCompetitors() {
  try { competitors.value = await call('crm.api.battlecards.list_battlecards') }
  catch (e) { competitors.value = [] }
  renderCompetitors()
}
function clearCompetitors() { competitorOverlays.forEach((o) => o.setMap(null)); competitorOverlays = [] }
function renderCompetitors() {
  clearCompetitors()
  if (!showCompetitors.value || !map) return
  const icon = {
    path: 'M 0,-10 L 8,0 L 0,10 L -8,0 Z', fillColor: '#C62828', fillOpacity: 0.95,
    strokeColor: '#fff', strokeWeight: 1.5, scale: 1,
  }
  competitors.value.forEach((c) => {
    if (c.latitude == null || c.longitude == null) return
    const m = new google.maps.Marker({ map, position: { lat: c.latitude, lng: c.longitude },
      title: `${c.competitor_name} (competitor)`, zIndex: 7000, icon })
    m.addListener('click', () => viewCard(c))
    competitorOverlays.push(m)
  })
}
function toggleCompetitors() { showCompetitors.value = !showCompetitors.value; if (showCompetitors.value && !competitors.value.length) loadCompetitors(); else renderCompetitors() }

function openTerritoryRing(p, radius) {
  Object.assign(territory, { open: true, type: 'ring', label: `${radius} mi · ${p.plant_name}`,
    lat: p.latitude, lng: p.longitude, radius_mi: radius, points: null, tab: 'smart' })
  smartLeads.candidates = []; smartLeads.selected = []; battle.cards = []; battle.active = null
}
function openTerritoryZone(z) {
  Object.assign(territory, { open: true, type: 'zone', label: `Zone · ${z.zone_name}`,
    points: z.points, lat: null, lng: null, tab: 'smart' })
  smartLeads.candidates = []; smartLeads.selected = []; battle.cards = []; battle.active = null
}
function setRingRadius(mi) { territory.radius_mi = mi; territory.label = territory.label.replace(/^\d+ mi/, `${mi} mi`); smartLeads.candidates = []; battle.cards = [] }
function _scopeArg() {
  return territory.type === 'ring'
    ? { scope_type: 'ring', scope: JSON.stringify({ lat: territory.lat, lng: territory.lng, radius_mi: territory.radius_mi }) }
    : { scope_type: 'zone', scope: JSON.stringify({ points: territory.points }) }
}

async function findSmartLeads() {
  smartLeads.loading = true
  try {
    const r = await call('crm.api.smart_leads.discover', _scopeArg())
    smartLeads.candidates = r.candidates || []; smartLeads.selected = []
    if (!smartLeads.candidates.length) toast.info(__('No new prospects found in this area'))
  } catch (e) { toast.error(__('Smart Leads failed: ') + (e?.messages?.[0] || e?.message || e)) }
  finally { smartLeads.loading = false }
}
function toggleCand(id) {
  const i = smartLeads.selected.indexOf(id)
  if (i >= 0) smartLeads.selected.splice(i, 1); else smartLeads.selected.push(id)
}
async function addSmartLeads() {
  const chosen = smartLeads.candidates.filter((c) => smartLeads.selected.includes(c.place_id))
  if (!chosen.length) { toast.warning(__('Select at least one prospect')); return }
  smartLeads.adding = true
  try {
    const r = await call('crm.api.smart_leads.create_leads', { candidates: JSON.stringify(chosen) })
    toast.success(`${r.count} ${__('Smart Leads added')}`)
    smartLeads.candidates = smartLeads.candidates.filter((c) => !smartLeads.selected.includes(c.place_id))
    smartLeads.selected = []
    loadRecords()
  } catch (e) { toast.error(__('Could not add leads')) }
  finally { smartLeads.adding = false }
}

async function loadBattleInArea() {
  battle.loading = true
  try { battle.cards = await call('crm.api.battlecards.list_in_area', _scopeArg()) }
  catch (e) { battle.cards = [] }
  finally { battle.loading = false }
}
async function saveCompetitor() {
  if (!battle.form.competitor_name) { toast.warning(__('Enter a competitor name')); return }
  battle.adding = true
  try {
    const payload = Object.assign({}, battle.form, { territory: territory.label })
    const r = await call('crm.api.battlecards.save_battlecard', { payload: JSON.stringify(payload) })
    toast.success(r.geocoded ? __('Competitor saved + located') : __('Competitor saved (address not geocoded)'))
    battle.form = { competitor_name: '', website: '', industry: '', address_line1: '', city: '', state: '', pincode: '' }
    await loadCompetitors()
    if (territory.open) loadBattleInArea()
  } catch (e) { toast.error(__('Could not save competitor')) }
  finally { battle.adding = false }
}
async function generateCard(name) {
  battle.generating = name
  try {
    const r = await call('crm.api.battlecards.generate_battlecard', { name })
    if (r.error) { toast.error(r.error) }
    else { toast.success(__('Battle card generated')); await viewCard({ name }); loadCompetitors() }
  } catch (e) { toast.error(__('Generation failed')) }
  finally { battle.generating = '' }
}
async function viewCard(card) {
  try { battle.active = await call('crm.api.battlecards.get_battlecard', { name: card.name }) }
  catch (e) { toast.error(__('Could not open card')) }
}
</script>
