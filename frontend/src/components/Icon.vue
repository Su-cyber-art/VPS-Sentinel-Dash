<script setup lang="ts">
defineProps<{ name: string }>()
const paths: Record<string, string> = {
  grid: 'M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z',
  server: 'M4 3h16v7H4z M4 14h16v7H4z M7 6.5h.01 M7 17.5h.01 M16 6.5h1 M16 17.5h1',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M3 12h18 M12 3c5 5 5 13 0 18-5-5-5-13 0-18',
  activity: 'M3 12h4l3-8 4 16 3-8h4', clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0 M12 7v5l3 2',
  list: 'M8 5h13 M8 12h13 M8 19h13 M3 5h.01 M3 12h.01 M3 19h.01',
  settings: 'M12 8a4 4 0 1 1 0 8 4 4 0 0 1 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
  plus: 'M12 5v14 M5 12h14', refresh: 'M20 7v5h-5 M4 17v-5h5 M6.1 6a8 8 0 0 1 13.1 3 M17.9 18a8 8 0 0 1-13.1-3',
  arrow: 'm9 5 7 7-7 7', close: 'm6 6 12 12 M18 6 6 18', check: 'm5 12 4 4L19 6',
  search: 'M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0 m-2 5 6 6', logout: 'M9 3H4v18h5 M9 12h12 m-5-5 5 5-5 5',
  copy: 'M8 8h12v13H8z M16 8V3H3v13h5', shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6z',
  play: 'm8 4 12 8-12 8z', bell: 'M5 17h14l-2-3V9a5 5 0 0 0-10 0v5z M10 21h4',
}
</script>
<template><svg class="icon" viewBox="0 0 24 24" aria-hidden="true"><path :d="paths[name] || paths.server" /></svg></template>
