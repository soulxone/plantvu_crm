import { ref } from 'vue'

// Shared open-state for the unified search palette (Ctrl/Cmd+K), so the
// sidebar link and the global shortcut drive the same dialog.
export const isSearchPaletteOpen = ref(false)

export function openSearchPalette() {
  isSearchPaletteOpen.value = true
}

export function closeSearchPalette() {
  isSearchPaletteOpen.value = false
}
