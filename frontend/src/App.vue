<template>
  <header class="app-header">
    <RouterLink to="/" class="brand">🥬 LemmaVeggies</RouterLink>
    <span class="subtitle">Frutas e Legumes</span>
  </header>
  <main class="app-main" :class="{ wide: $route.meta.wide }">
    <RouterView />
  </main>
</template>
