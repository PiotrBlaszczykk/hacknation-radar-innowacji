import { Building2, ExternalLink, MapPin, Users } from 'lucide-react'
import { useParams } from 'react-router-dom'
import { useLabel } from '../api/hooks.ts'
import { useOrganization } from '../api/social.ts'
import InnovationCard from '../components/InnovationCard.tsx'
import { Badge, Card, ErrorNote, Loading } from '../components/ui.tsx'

const formatNumber = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 })

export default function OrganizationPage() {
  const id = Number(useParams().id)
  const { data: organization, error, isPending } = useOrganization(id)
  const label = useLabel()

  if (!Number.isSafeInteger(id) || id <= 0) return <ErrorNote error={new Error('Nie znaleziono organizacji')} />
  if (error) return <ErrorNote error={error} />
  if (isPending || !organization) return <Loading label="Ładowanie profilu organizacji…" />

  const { stats, innovations, needs } = organization
  const location = [organization.city, organization.region].filter(Boolean).join(' · ')
  const metrics = [
    { label: 'Innowacje', value: stats.innovation_count },
    { label: 'Ocenione', value: stats.assessed_count },
    { label: 'Średni wynik', value: stats.average_score === null ? 'Brak ocen' : `${formatNumber.format(stats.average_score)}/100` },
    { label: 'W kontakcie lub wdrażane', value: stats.in_contact_or_implementing_count },
  ]

  return (
    <div className="space-y-6">
      <Card className="space-y-6 p-6">
        <div className="flex flex-wrap items-start gap-4">
          <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-brand-50 text-brand-700">
            <Building2 className="size-6" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1 space-y-2">
            <Badge tone="brand">{label('org_kinds', organization.kind)}</Badge>
            <h1 className="page-title">{organization.name}</h1>
            <div className="flex flex-wrap gap-x-4 gap-y-2 text-sm text-slate-600">
              {location && (
                <span className="inline-flex items-center gap-1.5">
                  <MapPin className="size-4" aria-hidden="true" />{location}
                </span>
              )}
              <span className="inline-flex items-center gap-1.5">
                <Users className="size-4" aria-hidden="true" />Osoby w Radarze ({organization.people_count})
              </span>
              {organization.website && (
                /^https?:\/\//i.test(organization.website) ? (
                  <a
                    className="inline-flex items-center gap-1.5 font-medium text-brand-700 hover:underline"
                    href={organization.website}
                    target="_blank"
                    rel="noreferrer"
                  >
                    Strona internetowa <ExternalLink className="size-3.5" aria-hidden="true" />
                  </a>
                ) : <span>{organization.website}</span>
              )}
            </div>
          </div>
        </div>
        {organization.description && (
          <p className="max-w-3xl whitespace-pre-wrap text-sm leading-relaxed text-slate-700">{organization.description}</p>
        )}
        {organization.interests.length > 0 && (
          <section className="space-y-2">
            <h2 className="technical-label">Obszary zainteresowań</h2>
            <div className="flex flex-wrap gap-2">
              {organization.interests.map((key) => <Badge key={key}>{label('domains', key)}</Badge>)}
            </div>
          </section>
        )}
        <dl className="grid grid-cols-2 gap-3 border-t border-slate-200 pt-5 sm:grid-cols-4">
          {metrics.map((metric) => (
            <div key={metric.label} className="border-t border-slate-200 px-1 py-3">
              <dt className="text-sm text-slate-600">{metric.label}</dt>
              <dd className="mt-1 font-display text-2xl font-semibold tabular-nums text-slate-900">{metric.value}</dd>
            </div>
          ))}
        </dl>
      </Card>

      <section className="space-y-3">
        <h2 className="section-title">Innowacje</h2>
        {innovations.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {innovations.map((innovation) => <InnovationCard key={innovation.id} innovation={innovation} />)}
          </div>
        ) : <Card className="p-5 text-sm text-slate-500">Brak innowacji tej organizacji.</Card>}
      </section>

      <section className="space-y-3">
        <h2 className="section-title">Zapotrzebowania</h2>
        {needs.length ? (
          <div className="grid gap-4 md:grid-cols-2">
            {needs.map((need) => (
              <Card key={need.id} className="space-y-2 p-5">
                <h3 className="text-base font-semibold text-slate-900">{need.title}</h3>
                <Badge tone={need.status === 'otwarte' ? 'green' : 'slate'}>
                  {need.status === 'otwarte' ? 'Otwarte' : 'Zamknięte'}
                </Badge>
                {need.description && <p className="whitespace-pre-wrap text-sm text-slate-700">{need.description}</p>}
                {need.domains.length > 0 && (
                  <div className="flex flex-wrap gap-2">
                    {need.domains.map((key) => <Badge key={key}>{label('domains', key)}</Badge>)}
                  </div>
                )}
                {need.offers.length > 0 && (
                  <p className="text-sm text-slate-600">
                    <span className="font-medium">Organizacja oferuje </span>
                    {need.offers.map((key) => label('support_needs', key)).join(', ')}
                  </p>
                )}
              </Card>
            ))}
          </div>
        ) : <Card className="p-5 text-sm text-slate-500">Brak zapotrzebowań tej organizacji.</Card>}
      </section>
    </div>
  )
}
