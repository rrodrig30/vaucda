export const CALCULATOR_CATEGORIES = {
  prostate_cancer: 'Prostate Cancer',
  kidney_cancer: 'Kidney Cancer',
  bladder_cancer: 'Bladder Cancer',
  male_voiding: 'Male Voiding',
  female_urology: 'Female Urology',
  reconstructive: 'Reconstructive Urology',
  fertility: 'Male Fertility',
  hypogonadism: 'Hypogonadism',
  stones: 'Urolithiasis',
  surgical_planning: 'Surgical Planning',
} as const

export const NOTE_TYPES = {
  clinic_note: 'Clinic Note',
  consult: 'Consult Note',
  preop: 'Pre-Op Note',
  postop: 'Post-Op Note',
} as const

export const LLM_PROVIDERS = {
  ollama: 'Ollama (Local)',
  anthropic: 'Anthropic Claude',
  openai: 'OpenAI GPT',
} as const
