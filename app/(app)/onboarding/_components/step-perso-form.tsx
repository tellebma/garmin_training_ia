'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerso } from '../actions'
import { COMMON_COUNTRIES } from '@/lib/onboarding/countries'
import type { PersonInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: PersonInput | null
  onDone: (nextStep: Step | null) => void
}

/** Petit label "(optionnel)" en couleur muted — pas de validation = mis en évidence visuel. */
function OptionalHint() {
  return <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
}

export function StepPersoForm({ defaultValues, onDone }: Readonly<Props>) {
  const [firstName, setFirstName] = useState(defaultValues?.first_name ?? '')
  const [dob, setDob] = useState(defaultValues?.dob ?? '')
  const [sex, setSex] = useState<'M' | 'F' | 'X'>(defaultValues?.sex ?? 'M')
  const [city, setCity] = useState(defaultValues?.city ?? '')
  const [country, setCountry] = useState(defaultValues?.country ?? '')
  const [consent, setConsent] = useState<boolean>(defaultValues?.consent_data_processing ?? false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Partial<Record<string, string[]>>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepPerso({
      first_name: firstName,
      dob,
      sex,
      city: city || undefined,
      country: country || undefined,
      consent_data_processing: consent,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) {
        setErrors(result.errors)
        toast.error('Corrige les erreurs avant de continuer.')
      } else {
        toast.error('Erreur de sauvegarde, réessaye.')
      }
      return
    }
    onDone(result.nextStep)
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
      noValidate
    >
      <div className="space-y-2">
        <Label htmlFor="first_name">Prénom</Label>
        <Input
          id="first_name"
          value={firstName}
          onChange={(e) => {
            setFirstName(e.target.value)
          }}
          aria-invalid={Boolean(errors.first_name?.[0])}
        />
        {errors.first_name?.[0] && (
          <p className="text-destructive text-xs">{errors.first_name[0]}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="dob">Date de naissance</Label>
        <Input
          id="dob"
          type="date"
          value={dob}
          onChange={(e) => {
            setDob(e.target.value)
          }}
          aria-invalid={Boolean(errors.dob?.[0])}
        />
        {errors.dob?.[0] && <p className="text-destructive text-xs">{errors.dob[0]}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="sex">Sexe</Label>
        <select
          id="sex"
          value={sex}
          onChange={(e) => {
            setSex(e.target.value as 'M' | 'F' | 'X')
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          <option value="M">M</option>
          <option value="F">F</option>
          <option value="X">X / Autre</option>
        </select>
        {errors.sex?.[0] && <p className="text-destructive text-xs">{errors.sex[0]}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="city">
            Ville
            <OptionalHint />
          </Label>
          <Input
            id="city"
            value={city}
            onChange={(e) => {
              setCity(e.target.value)
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="country">
            Pays
            <OptionalHint />
          </Label>
          <Input
            id="country"
            list="countries-list"
            value={country}
            onChange={(e) => {
              setCountry(e.target.value)
            }}
            autoComplete="country-name"
          />
          <datalist id="countries-list">
            {COMMON_COUNTRIES.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => {
            setConsent(e.target.checked)
          }}
          className="mt-0.5"
        />
        <span>
          J&apos;accepte le traitement de mes données fitness pour générer un plan personnalisé.
          (RGPD)
        </span>
      </label>
      {errors.consent_data_processing?.[0] && (
        <p className="text-destructive text-xs">{errors.consent_data_processing[0]}</p>
      )}

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
