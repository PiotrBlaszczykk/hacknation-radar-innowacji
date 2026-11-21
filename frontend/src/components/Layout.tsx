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
    <div className="col-span-2 flex min-w-0 items-center gap-3 sm:col-span-1 sm:col-start-3 sm:row-start-1 sm:justify-self-end lg:col-start-2">
      <label htmlFor="header-persona" className="sr-only">Persona</label>
      <select
        id="header-persona"
        value={persona.id}
        onChange={(event) => choose(Number(event.target.value))}
        className="min-h-10 min-w-0 flex-1 rounded-sm border border-white/55 bg-brand-700 px-2.5 text-sm font-semibold text-white hover:border-white focus-visible:outline-white sm:flex-none"
      >
        {users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}
      </select>
      <Link to="/profil" className="inline-flex min-h-10 shrink-0 items-center gap-1.5 rounded-sm px-1 text-sm font-semibold text-white hover:underline focus-visible:outline-white">
        <UserRound className="size-4" aria-hidden="true" /> Profil
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
        className="border-b border-slate-200 bg-surface lg:sticky lg:top-0 lg:z-10"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && menuOpen && menuButton.current?.getClientRects().length) {
            setMenuOpen(false)
            menuButton.current.focus()
          }
        }}
      >
        <div className="masthead bg-brand-600 text-white">
          <div className="mx-auto grid max-w-[78rem] grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1.5 px-4 py-2.5 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:px-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:px-10 lg:py-3">
            <Link to="/" onClick={() => setMenuOpen(false)} className="flex min-h-11 w-fit items-center gap-2 rounded-sm focus-visible:outline-white sm:gap-3">
              <span className="grid size-8 shrink-0 place-items-center border border-white/60 sm:size-9">
                <Radar className="size-5 sm:size-[1.375rem]" aria-hidden="true" strokeWidth={1.75} />
              </span>
              <span className="font-display text-[1.65rem] font-bold leading-none tracking-[.02em] uppercase max-[359px]:text-[1.35rem] sm:text-[1.875rem]">Wihajster</span>
            </Link>
            <button
              ref={menuButton}
              type="button"
              aria-expanded={menuOpen}
              aria-controls="main-navigation"
              onClick={() => setMenuOpen(!menuOpen)}
              className="inline-flex min-h-11 items-center gap-1.5 rounded-sm border border-white/55 px-2.5 text-sm font-semibold hover:bg-brand-700 focus-visible:outline-white lg:hidden"
            >
              {menuOpen ? <X className="size-4" aria-hidden="true" /> : <Menu className="size-4" aria-hidden="true" />}
              Menu
            </button>
            <PersonaSwitcher />
          </div>
        </div>
        <nav
          id="main-navigation"
          aria-label="Nawigacja główna"
          className={cx(
            'mx-auto max-w-[78rem] grid-cols-1 gap-x-5 px-4 min-[360px]:grid-cols-2 sm:px-8 lg:flex lg:items-center lg:gap-7 lg:px-10',
            menuOpen ? 'grid' : 'hidden',
          )}
        >
          {routes.filter((route) => route.nav).map(({ path, nav }) => {
            const Icon = nav!.icon
            return (
              <NavLink
                key={path}
                to={path}
                end={path === '/'}
                onClick={() => setMenuOpen(false)}
                className={({ isActive }) => cx(
                  'flex min-h-11 items-center gap-2 border-b-2 px-1 text-sm font-semibold transition-colors lg:whitespace-nowrap',
                  isActive ? 'border-brand-600 text-brand-700' : 'border-transparent text-slate-700 hover:text-brand-700',
                  path === '/zglos' && 'lg:order-last lg:ml-auto',
                )}
              >
                <Icon className="size-4 shrink-0" aria-hidden="true" />
                {path === '/zglos' ? 'Zgłoś innowację' : nav!.label}
              </NavLink>
            )
          })}
        </nav>
      </header>
      <main id="main-content" ref={main} tabIndex={-1} className="mx-auto max-w-[78rem] px-4 py-6 outline-none sm:px-8 sm:py-9 lg:px-10">
        <Outlet />
      </main>
    </div>
  )
}
