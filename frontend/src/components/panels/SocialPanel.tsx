import { Bookmark, Handshake, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import {
  maxSocialMessageLength,
  useClaimInnovation,
  useCreateInteraction,
  useInteractions,
  type SocialMessage,
} from '../../api/social.ts'
import type { InnovationFull } from '../../api/types.ts'
import { usePersona } from '../../lib/persona.tsx'
import { Button, Card, ErrorNote, Field, inputClass, Loading } from '../ui.tsx'

const sectionHeading = 'technical-label'
const formatDate = new Intl.DateTimeFormat('pl-PL', { dateStyle: 'medium', timeStyle: 'short' })
const toggles = [
  { type: 'obserwuje', text: 'Obserwuj', Icon: Bookmark },
  { type: 'zainteresowany', text: 'Jestem zainteresowany', Icon: Handshake },
] as const

function MessageList({ messages }: { messages: SocialMessage[] }) {
  return (
    <ul className="divide-y divide-slate-200">
      {messages.map(({ id, user, body, created_at }) => (
        <li key={id} className="space-y-1 py-3 first:pt-0 last:pb-0">
          <p className="break-words text-sm font-medium text-slate-900">{user.name}</p>
          <p className="break-words text-xs text-slate-500">
            {[user.organization?.name, formatDate.format(new Date(created_at))].filter(Boolean).join(' · ')}
          </p>
          <p className="whitespace-pre-wrap break-words text-sm text-slate-700">{body}</p>
        </li>
      ))}
    </ul>
  )
}

function PersonaSocialPanel({ innovation, personaId }: { innovation: InnovationFull; personaId: number | null }) {
  const { data, error, isPending } = useInteractions(innovation.id, personaId)
  const interaction = useCreateInteraction(innovation.id, personaId)
  const claim = useClaimInnovation(innovation.id, personaId)
  const [showContactForm, setShowContactForm] = useState(false)
  const [contact, setContact] = useState('')
  const [contactSent, setContactSent] = useState(false)
  const [comment, setComment] = useState('')
  const disabled = personaId === null || interaction.isPending

  return (
    <>
      {!innovation.claimed && (
        <Card className="space-y-3 border-amber-300 bg-amber-50 p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-amber-900">
            <ShieldCheck className="size-4 shrink-0" aria-hidden="true" />
            Profil czeka na potwierdzenie
          </h3>
          <p className="text-sm text-amber-900">
            Ten profil założył radar na podstawie źródła publicznego. To Twoja innowacja?
          </p>
          <Button type="button" disabled={personaId === null || claim.isPending} onClick={() => claim.mutate()}>
            {claim.isPending ? 'Potwierdzanie…' : 'Potwierdź profil'}
          </Button>
          {claim.error && <ErrorNote error={claim.error} />}
        </Card>
      )}
      <Card className="space-y-5 p-5">
        <h3 className={sectionHeading}>Społeczność</h3>
        {isPending && <Loading label="Ładowanie aktywności…" />}
        {error && <ErrorNote error={error} />}
        {data && (
          <>
            <div className="grid gap-2">
              {toggles.map(({ type, text, Icon }) => {
                const active = data.mine.includes(type)
                return (
                  <Button
                    key={type}
                    type="button"
                    variant={active ? 'primary' : 'secondary'}
                    aria-pressed={active}
                    disabled={disabled}
                    className="justify-start"
                    onClick={() => interaction.mutate({ type })}
                  >
                    <Icon className="size-4 shrink-0" aria-hidden="true" />
                    {text}
                    <span className="ml-auto tabular-nums">{data.counts[type]}</span>
                  </Button>
                )
              })}
            </div>
            {personaId === null && <p className="text-sm text-slate-500">Wybierz personę, aby dołączyć.</p>}
            {interaction.error && <ErrorNote error={interaction.error} />}

            <section className="space-y-3 border-t border-slate-200 pt-4">
              <h4 className={sectionHeading}>Prośby o kontakt <span className="ml-1">{data.counts.kontakt}</span></h4>
              {data.can_read_contacts && <MessageList messages={data.contact_requests} />}
              {contactSent && <p role="status" className="text-sm text-emerald-700">Prośba o kontakt została wysłana.</p>}
              {showContactForm ? (
                <form
                  className="space-y-2"
                  onSubmit={(event) => {
                    event.preventDefault()
                    if (!disabled && contact.trim()) {
                      interaction.mutate({ type: 'kontakt', body: contact }, {
                        onSuccess: () => {
                          setContact('')
                          setShowContactForm(false)
                          setContactSent(true)
                        },
                      })
                    }
                  }}
                >
                  <Field label="Wiadomość do twórców">
                    <textarea
                      className={inputClass}
                      rows={3}
                      value={contact}
                      required
                      disabled={disabled}
                      maxLength={maxSocialMessageLength}
                      onChange={(event) => setContact(event.target.value)}
                    />
                  </Field>
                  <div className="flex flex-wrap gap-2">
                    <Button type="submit" disabled={disabled || !contact.trim()}>Wyślij prośbę</Button>
                    <Button type="button" variant="ghost" disabled={disabled} onClick={() => setShowContactForm(false)}>
                      Anuluj
                    </Button>
                  </div>
                </form>
              ) : (
                <Button
                  type="button"
                  variant="secondary"
                  disabled={disabled}
                  onClick={() => {
                    setContactSent(false)
                    setShowContactForm(true)
                  }}
                >
                  Poproś o kontakt
                </Button>
              )}
            </section>

            <section className="space-y-3 border-t border-slate-200 pt-4">
              <h4 className={sectionHeading}>Komentarze <span className="ml-1">{data.counts.komentarz}</span></h4>
              {data.comments.length ? (
                <MessageList messages={data.comments} />
              ) : (
                <p className="text-sm text-slate-500">Brak komentarzy.</p>
              )}
              <form
                className="space-y-2"
                onSubmit={(event) => {
                  event.preventDefault()
                  if (!disabled && comment.trim()) {
                    interaction.mutate({ type: 'komentarz', body: comment }, { onSuccess: () => setComment('') })
                  }
                }}
              >
                <Field label="Twój komentarz">
                  <textarea
                    className={inputClass}
                    rows={3}
                    value={comment}
                    required
                    disabled={disabled}
                    maxLength={maxSocialMessageLength}
                    onChange={(event) => setComment(event.target.value)}
                  />
                </Field>
                <Button type="submit" variant="secondary" disabled={disabled || !comment.trim()}>Dodaj komentarz</Button>
              </form>
            </section>
          </>
        )}
      </Card>
    </>
  )
}

export default function SocialPanel({ innovation }: { innovation: InnovationFull }) {
  const { persona } = usePersona()
  const personaId = persona?.id ?? null
  return <PersonaSocialPanel key={`${innovation.id}:${personaId}`} innovation={innovation} personaId={personaId} />
}
