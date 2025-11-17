export interface Group {
  id: string
  name: string
  color: string | null
  tags: string[]
  noteCount: number
  updatedAt: string
}

export interface GroupSuggestion {
  id: string
  name: string
  tags: string[]
  confidence: number
}
