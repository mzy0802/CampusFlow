<script setup>
defineProps({ name: String, size: { type: Number, default: 22 } })
const paths = {
  search:'M21 21l-4.5-4.5M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0Z',
  map:'m3 5 6-2 6 2 6-2v16l-6 2-6-2-6 2V5Zm6-2v16m6-14v16',
  parking:'M8 20V4h6a5 5 0 0 1 0 10H8',
  bike:'M6 21a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm12 0a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM6 17l4-9 4 9h4L14 5h3M8 8h5',
  people:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2m20 0v-2a4 4 0 0 0-3-3.9M15 3.1a4 4 0 0 1 0 7.8M13 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z',
  upload:'M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4',
  layers:'m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5',
  locate:'M12 2v3m0 14v3M2 12h3m14 0h3M19 12a7 7 0 1 1-14 0 7 7 0 0 1 14 0Zm-7-2v4m-2-2h4',
  arrow:'m9 5 7 7-7 7', close:'m6 6 12 12M6 18 18 6', road:'M9 3 5 21M15 3l4 18M12 3v3m0 4v4m0 4v3',
  bus:'M5 17V6a3 3 0 0 1 3-3h8a3 3 0 0 1 3 3v11H5Zm0-7h14M7 17v4m10-4v4M8 14h1m6 0h1',
  route:'M5 5h10a4 4 0 0 1 0 8H9a4 4 0 0 0 0 8h10M3 3h4v4H3V3Zm14 16h4v4h-4v-4',
  refresh:'M20 7v5h-5M4 17v-5h5M6 6a8 8 0 0 1 13 3M5 15a8 8 0 0 0 13 3',
}
</script>
<template><svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="paths[name] || paths.map" /></svg></template>
