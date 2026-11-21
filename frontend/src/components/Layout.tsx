import { Menu, Radar, UserRound, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom'
import { usePersona } from '../lib/persona.tsx'
import { routes } from '../routes.tsx'
import { cx } from './ui.tsx'

function PersonaSwitcher() {
  const { persona, users, choose } = usePersona()
  if (!persona) return null

  return (
    <div className="col-span-2 flex min-w-0 items-center gap-2.5 border-t border-slate-200 pt-2 lg:col-span-1 lg:justify-self-end lg:border-0 lg:pt-0">
      <label htmlFor="header-persona" className="technical-label shrink-0">Persona</label>
      <select
        id="header-persona"
        value={persona.id}
        onChange={(event) => choose(Number(event.target.value))}
        className="min-h-11 min-w-0 flex-1 rounded-sm border border-control bg-canvas px-2.5 text-sm font-semibold text-slate-900 lg:flex-none"
      >
        {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
      </select>
      <Link to="/profil" className="inline-flex min-h-11 shrink-0 items-center gap-1.5 rounded-sm px-1.5 text-sm font-semibold text-slate-700 hover:text-brand-700">
        <UserRound className="hidden size-4 sm:block" aria-hidden="true" /> Profil
      </Link>
    </div>
  )
}

export default function Layout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const menuButton = useRef<HTMLButtonElement>(null)
  const main = useRef<HTMLElement>(null)
  const { pathname, hash } = useLocation()
  const lastPath = useRef(pathname)

  useEffect(() => {
    if (lastPath.current === pathname) return
    lastPath.current = pathname
    if (!hash) {
      window.scrollTo(0, 0)
      main.current?.focus({ preventScroll: true })
    }
  }, [pathname, hash])

  return (
    <div className="min-h-screen">
      <a href="#main-content" className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-4 focus:z-30 focus:bg-canvas focus:p-2">
        Przejdź do treści
      </a>
      <header
        className="border-b border-slate-200 bg-shell lg:sticky lg:top-0 lg:z-10"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen && menuButton.current?.getClientRects().length) {
            setMenuOpen(false)
            menuButton.current.focus()
          }
        }}
      >
        <div className="mx-auto grid max-w-[90rem] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-2 px-4 pt-2 pb-2 sm:px-8 md:pt-2.5 lg:gap-y-1 lg:px-12 lg:pb-0">
          <Link to="/" onClick={() => setMenuOpen(false)} className="flex min-h-11 w-fit items-center gap-2.5 rounded-sm text-slate-900">
            <span className="grid size-8 shrink-0 place-items-center border border-brand-500/65 text-brand-600">
              <Radar className="size-5" aria-hidden="true" strokeWidth={1.5} />
            </span>
            <span className="font-display text-2xl font-semibold leading-none tracking-[.045em] uppercase sm:text-3xl">Radar Innowacji</span>
          </Link>
          <button
            ref={menuButton}
            type="button"
            aria-expanded={menuOpen}
            aria-controls="main-navigation"
            onClick={() => setMenuOpen(!menuOpen)}
            className="inline-flex min-h-11 items-center gap-1.5 rounded-sm border border-control px-2.5 text-sm font-semibold text-slate-700 hover:bg-slate-50 lg:hidden"
          >
            {menuOpen ? <X className="size-4" aria-hidden="true" /> : <Menu className="size-4" aria-hidden="true" />}
            Menu
          </button>
          <PersonaSwitcher />
          <nav
            id="main-navigation"
            aria-label="Nawigacja główna"
            className={cx(
              'col-span-2 grid-cols-1 gap-x-5 border-t border-slate-200 min-[360px]:grid-cols-2 lg:flex lg:items-center lg:gap-7',
              menuOpen ? 'grid' : 'hidden',
            )}
          >
            {routes.filter((route) => route.nav).map(({ path, nav }) => (
              <NavLink
                key={path}
                to={path}
                end={path === '/'}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) => cx(
                  'flex min-h-11 items-center border-b-2 px-1 text-sm font-semibold lg:whitespace-nowrap',
                  isActive ? 'border-brand-500 text-brand-700' : 'border-transparent text-slate-600 hover:text-slate-900',
                )}
              >
                {nav!.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main id="main-content" ref={main} tabIndex={-1} className="mx-auto max-w-[90rem] px-4 py-5 outline-none sm:px-8 sm:py-8 lg:px-12">
        <Outlet />
      </main>
    </div>
  )
}
