import { useQueryClient } from '@tanstack/react-query'
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getPersonaId, setPersonaId } from '../api/client.ts'
import { useUsers } from '../api/hooks.ts'
import type { User } from '../api/types.ts'

// Prototyp nie ma logowania. Persona to użytkownik wybrany z listy, wysyłany w nagłówku X-User-Id.
type PersonaContext = { persona: User | null; users: User[]; choose: (id: number) => void }

const Context = createContext<PersonaContext>({ persona: null, users: [], choose: () => {} })

export function PersonaProvider({ children }: { children: ReactNode }) {
  const { data } = useUsers()
  const client = useQueryClient()
  const [id, setId] = useState<number | null>(getPersonaId)
  const users = data?.items ?? []

  useEffect(() => {
    if (users.length && !users.some((user) => user.id === id)) {
      setPersonaId(users[0].id)
      setId(users[0].id)
    }
  }, [users, id])

  const choose = (next: number) => {
    setPersonaId(next)
    setId(next)
    client.invalidateQueries()
  }

  const persona = users.find((user) => user.id === id) ?? null
  return <Context.Provider value={{ persona, users, choose }}>{children}</Context.Provider>
}

export const usePersona = () => useContext(Context)
