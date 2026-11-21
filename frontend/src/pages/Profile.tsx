import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MAX_ABOUT, useMe, useSaveProfile } from '../api/feed.ts'
import { useLabel, useMeta } from '../api/hooks.ts'
import type { User } from '../api/types.ts'
import { Button, Card, ChipSelect, ErrorNote, Field, Loading, inputClass } from '../components/ui.tsx'
import { usePersona } from '../lib/persona.tsx'

function ProfileForm({ profile }: { profile: User }) {
  const [about, setAbout] = useState(profile.about ?? '')
  const [interests, setInterests] = useState(profile.interests)
  const { data: meta, error: metaError } = useMeta()
  const label = useLabel()
  const save = useSaveProfile()

  return (
    <div className="space-y-4">
      <Card className="p-5 sm:p-6">
        <h1 className="page-title">Mój profil</h1>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          {[
            ['Imię i nazwisko', profile.name],
            ['Stanowisko', profile.title],
            ['Organizacja', profile.organization?.name],
            ['Rola', label('user_roles', profile.role)],
          ].map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-medium text-slate-500">{key}</dt>
              <dd className="mt-1 text-sm text-slate-900">{value || '—'}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card className="p-5 sm:p-6">
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault()
            save.mutate({ personaId: profile.id, input: { about, interests } })
          }}
        >
          <p className="text-sm text-slate-600">Na podstawie opisu i wybranych obszarów radar dobiera innowacje do Twojego feedu.</p>
          <Field label="Czego szukam">
            <textarea
              className={inputClass}
              rows={4}
              value={about}
              maxLength={MAX_ABOUT}
              onChange={(event) => { setAbout(event.target.value); save.reset() }}
            />
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-slate-800">Moje obszary</legend>
            {meta && <ChipSelect options={meta.domains} value={interests} onChange={(next) => { setInterests(next); save.reset() }} />}
            {metaError && <ErrorNote error={metaError} />}
          </fieldset>
          {save.error && <ErrorNote error={save.error} />}
          {save.isSuccess && <p role="status" className="text-sm text-emerald-700">Profil zapisany.</p>}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" disabled={save.isPending}>{save.isPending ? 'Zapisywanie…' : 'Zapisz profil'}</Button>
            <Link to="/" className="text-sm font-medium text-brand-700 hover:underline">Wróć do feedu</Link>
          </div>
        </form>
      </Card>
    </div>
  )
}

export default function Profile() {
  const { persona } = usePersona()
  const profile = useMe(persona?.id ?? null)

  return (
    <div className="mx-auto max-w-3xl">
      {!persona && <Card className="p-6 text-sm text-slate-600">Wybierz personę w nagłówku, aby przejść do profilu.</Card>}
      {persona && profile.isPending && <Loading label="Ładowanie profilu…" />}
      {profile.error && <ErrorNote error={profile.error} />}
      {profile.data && <ProfileForm key={profile.data.id} profile={profile.data} />}
    </div>
  )
}
