<template>
  <div class="flex h-full flex-col gap-6 px-6 py-8 text-ink-gray-8">
    <!-- Header -->
    <div class="flex justify-between px-2 text-ink-gray-8">
      <div class="flex flex-col gap-1">
        <h2 class="flex gap-2 text-xl font-semibold leading-none h-5">
          {{ __('Map Settings') }}
        </h2>
        <p class="text-p-base text-ink-gray-6">
          {{ __('Configure the Google Maps key, the default home base, and each sales rep’s map origin.') }}
        </p>
      </div>
      <div class="flex item-center space-x-2 justify-end">
        <Button
          v-if="settings.isDirty"
          :label="__('Update')"
          variant="solid"
          :loading="settings.loading"
          @click="updateSettings"
        />
      </div>
    </div>

    <div class="flex flex-1 flex-col gap-5 overflow-y-auto p-2">
      <!-- API key -->
      <div class="flex items-start justify-between gap-8">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7">{{ __('Google Maps API Key') }}</div>
          <div class="max-w-md text-p-sm text-ink-gray-5">
            {{ __('Used by the in-CRM map. Must be HTTP-referrer restricted to your CRM domain(s) in Google Cloud and limited to the Maps JavaScript, Places, and Geocoding APIs.') }}
          </div>
        </div>
        <FormControl
          v-model="settings.doc.google_maps_api_key"
          type="password"
          size="md"
          class="w-72"
          :placeholder="__('AIza…')"
        />
      </div>
      <div class="h-px border-t border-outline-gray-modals" />

      <!-- Map ID -->
      <div class="flex items-center justify-between gap-8">
        <div class="flex flex-col">
          <div class="text-p-base font-medium text-ink-gray-7">{{ __('Map ID (optional)') }}</div>
          <div class="max-w-md text-p-sm text-ink-gray-5">
            {{ __('Google Maps Map ID for vector maps / advanced markers.') }}
          </div>
        </div>
        <FormControl v-model="settings.doc.google_maps_map_id" type="text" size="md" class="w-72" />
      </div>
      <div class="h-px border-t border-outline-gray-modals" />

      <!-- Default home base -->
      <div class="flex flex-col gap-3">
        <div class="text-p-base font-medium text-ink-gray-7">{{ __('Default Home Base') }}</div>
        <div class="flex items-end gap-2">
          <FormControl
            v-model="settings.doc.map_home_address"
            type="text"
            size="md"
            class="flex-1"
            :label="__('Address')"
            :placeholder="__('123 Main St, City, State')"
          />
          <FormControl v-model.number="settings.doc.map_home_latitude" type="number" size="md" class="w-32" :label="__('Lat')" />
          <FormControl v-model.number="settings.doc.map_home_longitude" type="number" size="md" class="w-32" :label="__('Lng')" />
          <Button :label="__('Geocode')" :loading="geocoding" @click="geocodeHome" />
        </div>
      </div>
      <div class="h-px border-t border-outline-gray-modals" />

      <!-- Per-rep config -->
      <div class="flex flex-col gap-3">
        <div class="flex items-center justify-between">
          <div class="text-p-base font-medium text-ink-gray-7">{{ __('Per-Rep Map Origin') }}</div>
          <Button :label="__('Add rep')" @click="addRep">
            <template #prefix><LucidePlus class="h-4 w-4" /></template>
          </Button>
        </div>
        <div v-if="!repRows.length" class="text-p-sm text-ink-gray-5">
          {{ __('No per-rep origins yet. Reps without one use the default home base above.') }}
        </div>
        <div
          v-for="(row, i) in repRows"
          :key="i"
          class="flex items-end gap-2 rounded-lg border border-outline-gray-modals p-2"
        >
          <FormControl
            v-model="row.rep"
            type="text"
            size="sm"
            class="w-48"
            :label="__('Rep (user email)')"
            :placeholder="__('rep@company.com')"
          />
          <FormControl v-model="row.home_address" type="text" size="sm" class="flex-1" :label="__('Home address')" />
          <FormControl v-model.number="row.home_latitude" type="number" size="sm" class="w-28" :label="__('Lat')" />
          <FormControl v-model.number="row.home_longitude" type="number" size="sm" class="w-28" :label="__('Lng')" />
          <Button variant="ghost" @click="geocodeRow(row)" :loading="row._geocoding" :label="__('Geo')" />
          <Button variant="ghost" theme="red" @click="removeRep(i)">
            <LucideTrash2 class="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { FormControl, Button, call, toast } from 'frappe-ui'
import LucidePlus from '~icons/lucide/plus'
import LucideTrash2 from '~icons/lucide/trash-2'
import { getSettings } from '@/stores/settings'
import { showSettings } from '@/composables/settings'

const { _settings: settings } = getSettings()
const geocoding = ref(false)

const repRows = computed(() => {
  if (!settings.doc.map_rep_config) settings.doc.map_rep_config = []
  return settings.doc.map_rep_config
})

function addRep() {
  repRows.value.push({ rep: '', home_address: '', home_latitude: null, home_longitude: null })
}
function removeRep(i) {
  repRows.value.splice(i, 1)
}

async function geocodeOne(address) {
  const r = await call('crm.api.maps.geocode_addresses', {
    addresses: JSON.stringify([address]),
    batch: 1,
  })
  return (r.resolved || {})[address.trim()]
}

async function geocodeHome() {
  const addr = settings.doc.map_home_address
  if (!addr) return toast.warning(__('Enter an address first'))
  geocoding.value = true
  try {
    const c = await geocodeOne(addr)
    if (c) {
      settings.doc.map_home_latitude = c.lat
      settings.doc.map_home_longitude = c.lng
      toast.success(__('Geocoded'))
    } else toast.error(__('Address not found'))
  } catch (e) {
    toast.error(e?.messages?.[0] || __('Geocode failed'))
  } finally {
    geocoding.value = false
  }
}

async function geocodeRow(row) {
  if (!row.home_address) return toast.warning(__('Enter an address first'))
  row._geocoding = true
  try {
    const c = await geocodeOne(row.home_address)
    if (c) { row.home_latitude = c.lat; row.home_longitude = c.lng }
    else toast.error(__('Address not found'))
  } catch (e) {
    toast.error(__('Geocode failed'))
  } finally {
    row._geocoding = false
  }
}

function updateSettings() {
  settings.save.submit(null, {
    onSuccess: () => { showSettings.value = false },
  })
}
</script>
