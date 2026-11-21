import { Radar } from 'lucide-react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import { useLabel } from '../api/hooks.ts'
import { usePersona } from '../lib/persona.tsx'
import { routes } from '../routes.tsx'
import { cx } from './ui.tsx'

function PersonaSwitcher() {
  const { persona, users, choose } = usePersona()
  const label = useLabel()
  if (!persona) return null

  return (
    <div className="flex shrink-0 items-center gap-2">
      <span className="hidden max-w-40 text-right leading-tight sm:block">
        <Link to="/profil" className="block truncate text-sm font-medium text-brand-700 hover:underline">
          {persona.name}
        </Link>
        <span className="block truncate text-xs text-slate-500">
          {label('user_roles', persona.role)} · {persona.organization?.name}
        </span>
      </span>
      <Link to="/profil" className="text-sm font-medium text-brand-700 hover:underline sm:hidden">Profil</Link>
      <select
        aria-label="Zmień użytkownika"
        value={persona.id}
        onChange={(event) => choose(Number(event.target.value))}
        className="max-w-32 rounded-lg border border-slate-300 bg-white px-2 py-1.5 text-sm sm:max-w-44"
      >
        {users.map((user) => (
          <option key={user.id} value={user.id}>
            {user.name} ({label('user_roles', user.role)})
          </option>
        ))}
      </select>
    </div>
  )
}

export default function Layout() {
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-4">
          <Link to="/" className="flex shrink-0 items-center gap-2 text-lg font-semibold text-slate-900">
            <span className="grid size-9 place-items-center rounded-lg bg-brand-600 text-white">
              <Radar className="size-5" />
            </span>
            <span className="sr-only lg:not-sr-only">Radar Innowacji</span>
          </Link>
          <nav className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto">
            {routes
              .filter((route) => route.nav)
              .map(({ path, nav }) => {
                const Icon = nav!.icon
                return (
                  <NavLink
                    key={path}
                    to={path}
                    end={path === '/'}
                    className={({ isActive }) =>
                      cx(
                        'flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-2 text-sm font-medium',
                        isActive ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-100',
                      )
                    }
                  >
                    <Icon className="size-4" />
                    {nav!.label}
                  </NavLink>
                )
              })}
          </nav>
          <PersonaSwitcher />
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>
    </div>
  )
}
