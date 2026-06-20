// Lazy Google Maps JS loader + browser geocoding for the CRM map feature.
// The key comes from FCRM Settings (crm.api.maps.get_map_settings) and is
// referrer-restricted, so geocoding here runs in the browser (allowed) — no
// server-side Google calls, so a single locked-down key covers everything.
import { call } from 'frappe-ui'

let _settingsPromise = null
let _mapsPromise = null
let _geocoder = null

export function getMapSettings() {
  if (!_settingsPromise) {
    _settingsPromise = call('crm.api.maps.get_map_settings').catch((e) => {
      _settingsPromise = null
      throw e
    })
  }
  return _settingsPromise
}

export async function loadGoogleMaps() {
  if (window.google && window.google.maps) return window.google
  if (_mapsPromise) return _mapsPromise
  const settings = await getMapSettings()
  if (!settings.api_key) throw new Error('no-google-maps-key')
  _mapsPromise = new Promise((resolve, reject) => {
    window.__crmGmapsInit = () => resolve(window.google)
    const s = document.createElement('script')
    s.src =
      `https://maps.googleapis.com/maps/api/js?key=${settings.api_key}` +
      `&libraries=places,geometry&callback=__crmGmapsInit&loading=async`
    s.async = true
    s.onerror = () => { _mapsPromise = null; reject(new Error('maps-load-failed')) }
    document.head.appendChild(s)
  })
  return _mapsPromise
}

export async function geocodeAddress(address) {
  const google = await loadGoogleMaps()
  if (!_geocoder) _geocoder = new google.maps.Geocoder()
  return new Promise((resolve) => {
    _geocoder.geocode({ address }, (results, status) => {
      if (status === 'OK' && results && results[0]) {
        const loc = results[0].geometry.location
        resolve({ lat: loc.lat(), lng: loc.lng() })
      } else {
        resolve(null)
      }
    })
  })
}
