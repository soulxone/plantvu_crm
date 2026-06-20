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
        <Button :label="__('Plan route')" :loading="routing" @click="planRoute">
          <template #prefix><LucideRoute class="h-4 w-4" /></template>
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
            class="flex cursor-pointer items-center gap-2 border-b border-outline-gray-1 px-3 py-2 hover:bg-surface-gray-1"
            @click="focusRecord(rec)"
          >
            <span class="h-2.5 w-2.5 shrink-0 rounded-full" :style="{ background: kindMeta[rec.kind].color }" />
            <div class="min-w-0">
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { call, Button, LoadingIndicator, toast } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
import LucideMapPinned from '~icons/lucide/map-pinned'
import LucideRefreshCcw from '~icons/lucide/refresh-ccw'
import LucideMaximize from '~icons/lucide/maximize'
import LucideRoute from '~icons/lucide/route'
import LucideHelpCircle from '~icons/lucide/help-circle'

const router = useRouter()

const KIND_META = {
  lead: { label: 'Leads', color: '#FF9800' },
  organization: { label: 'Customers', color: '#0B9E92' },
  deal: { label: 'Deals', color: '#3F51B5' },
}
const kindMeta = KIND_META

const mapEl = ref(null)
const searchEl = ref(null)
const settings = ref(null)
const records = ref([])
const loading = ref(false)
const routing = ref(false)
const geocoding = ref(false)
const mapReady = ref(false)
const keyMissing = ref(false)
const repFilter = ref('')
const activeKinds = reactive(new Set(['lead', 'organization', 'deal']))
const counts = reactive({})

let map = null
let infoWindow = null
let dirService = null
let dirRenderer = null
let homeMarker = null
const markers = {} // id -> google.maps.Marker

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
      `&libraries=places,geometry&callback=__crmInitMap&loading=async`
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

async function geocodeLoop() {
  const pending = records.value
    .filter((r) => !r._geo && (r.address || '').trim() && r.lat == null)
    .map((r) => r.address.trim())
  const unique = [...new Set(pending)].slice(0, 25)
  if (!unique.length) { geocoding.value = false; fitAll(); return }
  geocoding.value = true
  try {
    const r = await call('crm.api.maps.geocode_addresses', { addresses: JSON.stringify(unique), batch: 25 })
    const resolved = r.resolved || {}
    let any = false
    records.value.forEach((rec) => {
      const c = resolved[(rec.address || '').trim()]
      if (c) { rec.lat = c.lat; rec.lng = c.lng; rec._geo = true; any = true }
      else if (unique.includes((rec.address || '').trim())) rec._geo = true
    })
    if (any) renderMarkers()
    const stillPending = records.value.some((rec) => !rec._geo && (rec.address || '').trim() && rec.lat == null)
    if (stillPending) setTimeout(geocodeLoop, 250)
    else { geocoding.value = false; fitAll() }
  } catch (e) {
    geocoding.value = false
  }
}

/* ── markers ───────────────────────────────────────────────────────────── */
function pinIcon(kind) {
  const color = KIND_META[kind]?.color || '#666'
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="38" viewBox="0 0 26 38">` +
    `<path d="M13 0C5.8 0 0 5.8 0 13c0 9 13 25 13 25s13-16 13-25C26 5.8 20.2 0 13 0z" fill="${color}"/>` +
    `<circle cx="13" cy="13" r="7.5" fill="#fff"/></svg>`
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
    const marker = new google.maps.Marker({
      map,
      position: { lat: rec.lat, lng: rec.lng },
      title: rec.label,
      icon: pinIcon(rec.kind),
    })
    marker.addListener('click', () => openInfo(rec, marker))
    markers[rec.id] = marker
  })
}

function openInfo(rec, marker) {
  const color = KIND_META[rec.kind]?.color || '#666'
  const route = (rec.route || '').replace(/^\/crm/, '')
  const html =
    `<div style="min-width:200px;font-family:inherit">` +
    `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px">` +
    `<span style="background:${color};color:#fff;font-size:10px;font-weight:700;border-radius:4px;padding:1px 6px;text-transform:uppercase">${KIND_META[rec.kind]?.label || rec.kind}</span>` +
    `<strong>${escapeHtml(rec.label || '')}</strong></div>` +
    (rec.sublabel ? `<div style="font-size:12px;color:#666">${escapeHtml(rec.sublabel)}</div>` : '') +
    (rec.address ? `<div style="font-size:12px;color:#444;margin:4px 0">${escapeHtml(rec.address)}</div>` : '') +
    (rec.status ? `<div style="font-size:12px;color:#555">Status: <b>${escapeHtml(rec.status)}</b></div>` : '') +
    (route ? `<a href="#" id="crm-map-open" style="font-size:12px;font-weight:600;color:#0B9E92">Open record →</a>` : '') +
    `</div>`
  infoWindow.setContent(html)
  infoWindow.open(map, marker)
  google.maps.event.addListenerOnce(infoWindow, 'domready', () => {
    const a = document.getElementById('crm-map-open')
    if (a) a.addEventListener('click', (e) => { e.preventDefault(); router.push(route) })
  })
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

/* Optimized travel route from home base through the visible customers. */
async function planRoute() {
  const home = settings.value?.home
  if (!home?.lat || !home?.lng) {
    toast.warning(__('Set a home base in CRM Settings → Map to plan a route'))
    return
  }
  const stops = visibleRecords.value.filter((r) => r.lat != null).slice(0, 24)
  if (stops.length < 1) { toast.warning(__('No mapped stops to route')); return }
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
</script>
