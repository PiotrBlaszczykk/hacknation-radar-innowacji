const PERSONA_KEY = 'radar.persona'

export function getPersonaId(): number | null {
  const raw = localStorage.getItem(PERSONA_KEY)
  return raw ? Number(raw) : null
}

export function setPersonaId(id: number) {
  localStorage.setItem(PERSONA_KEY, String(id))
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  if (init.body) headers.set('Content-Type', 'application/json')
  const persona = getPersonaId()
  if (persona && !headers.has('X-User-Id')) headers.set('X-User-Id', String(persona))

  const response = await fetch(`/api${path}`, { ...init, headers })
  const data = await response.json().catch(() => null)
  if (!response.ok) {
    throw new ApiError(response.status, data?.error ?? `Błąd serwera (${response.status})`)
  }
  return data as T
}

export const post = <T>(path: string, body: unknown) => api<T>(path, { method: 'POST', body: JSON.stringify(body) })
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: 'PATCH', body: JSON.stringify(body) })

export function query(params: Record<string, string | number | undefined | null>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== null && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
