export type FeatureLifecycle = 'core' | 'advanced' | 'retiring'

type FeatureDefinition = Readonly<{
  lifecycle: FeatureLifecycle
  enabled: boolean
  showInNavigation: boolean
}>

// This catalog is the single source of truth for product-surface feature decisions.
// Route removal and backend/data deletion remain separate, explicitly scoped changes.
export const productFeatures = {
  dashboard: { lifecycle: 'core', enabled: true, showInNavigation: true },
  chat: { lifecycle: 'core', enabled: true, showInNavigation: true },
  knowledge: { lifecycle: 'core', enabled: true, showInNavigation: true },
  memory: { lifecycle: 'core', enabled: true, showInNavigation: true },
  memoryGraph: { lifecycle: 'core', enabled: true, showInNavigation: true },
  search: { lifecycle: 'core', enabled: true, showInNavigation: true },
  traces: { lifecycle: 'core', enabled: true, showInNavigation: true },
  modelConfig: { lifecycle: 'core', enabled: true, showInNavigation: true },
  agentConfig: { lifecycle: 'core', enabled: true, showInNavigation: true },

  scheduledTasks: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  research: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  verifier: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  skills: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  mcp: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  imageLibrary: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  complexTags: { lifecycle: 'advanced', enabled: true, showInNavigation: false },
  reportExport: { lifecycle: 'advanced', enabled: true, showInNavigation: false },

  emotion: { lifecycle: 'retiring', enabled: false, showInNavigation: false },
  music: { lifecycle: 'retiring', enabled: false, showInNavigation: false },
  groupChat: { lifecycle: 'retiring', enabled: false, showInNavigation: false },
  notifications: { lifecycle: 'retiring', enabled: false, showInNavigation: false },
  favorites: { lifecycle: 'retiring', enabled: false, showInNavigation: false },
} as const satisfies Record<string, FeatureDefinition>

export type FeatureKey = keyof typeof productFeatures

export function isFeatureEnabled(feature: FeatureKey): boolean {
  return productFeatures[feature].enabled
}

export function isFeatureVisibleInNavigation(feature: FeatureKey): boolean {
  const definition = productFeatures[feature]
  return definition.enabled && definition.showInNavigation
}
