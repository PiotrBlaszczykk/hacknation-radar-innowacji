import { Compass, KanbanSquare, Lightbulb, PlusCircle, Radar, Rss, Scale } from 'lucide-react'
import type { ComponentType, ReactElement } from 'react'
import Broker from './pages/Broker.tsx'
import Criteria from './pages/Criteria.tsx'
import Feed from './pages/Feed.tsx'
import IdeaCheck from './pages/IdeaCheck.tsx'
import InnovationDetail from './pages/InnovationDetail.tsx'
import Needs from './pages/Needs.tsx'
import OrganizationPage from './pages/OrganizationPage.tsx'
import Profile from './pages/Profile.tsx'
import Sources from './pages/Sources.tsx'
import Submit from './pages/Submit.tsx'

// Nowa strona = nowy plik w pages/ i jeden wpis tutaj. `nav` dodaje pozycję do menu.
export type AppRoute = {
  path: string
  element: ReactElement
  nav?: { label: string; icon: ComponentType<{ className?: string }> }
}

export const routes: AppRoute[] = [
  { path: '/', element: <Feed />, nav: { label: 'Radar', icon: Radar } },
  { path: '/sprawdz-pomysl', element: <IdeaCheck />, nav: { label: 'Sprawdź pomysł', icon: Lightbulb } },
  { path: '/zglos', element: <Submit />, nav: { label: 'Zgłoś', icon: PlusCircle } },
  { path: '/zapotrzebowania', element: <Needs />, nav: { label: 'Zapotrzebowania', icon: Compass } },
  { path: '/broker', element: <Broker />, nav: { label: 'Panel brokera', icon: KanbanSquare } },
  { path: '/kryteria', element: <Criteria />, nav: { label: 'Kryteria', icon: Scale } },
  { path: '/zrodla', element: <Sources />, nav: { label: 'Źródła', icon: Rss } },
  { path: '/innowacje/:id', element: <InnovationDetail /> },
  { path: '/organizacje/:id', element: <OrganizationPage /> },
  { path: '/profil', element: <Profile /> },
]
