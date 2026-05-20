'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerso } from '@/app/(app)/onboarding/actions'
import { COMMON_COUNTRIES } from '@/lib/onboarding/countries'
import type { PersonInput } from '@/lib/onboarding/schemas'

interface Props {
  initial: PersonInput
}

export function PersoEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [values, setValues] = useState<PersonInput>(initial)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  function handleCancel() {
    setEdit(false)
    setValues(initial)
    setErrors({})
  }

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Informations personnelles</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdit(true)
            }}
          >
            Modifier
          </Button>
        </div>
        <p className="text-muted-foreground text-sm">
          {values.first_name} · {values.dob} · {values.sex}
          {(values.city ?? values.country)
            ? ` · ${values.city ?? '—'}, ${values.country ?? '—'}`
            : ''}
        </p>
      </section>
    )
  }

  async function handleSave() {
    setLoading(true)
    setErrors({})
    const r = await saveStepPerso(values)
    setLoading(false)
    if (!r.success) {
      if ('errors' in r) setErrors(r.errors as Record<string, string[]>)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Informations personnelles</h2>

      <div className="space-y-2">
        <Label htmlFor="perso-first_name">Prénom</Label>
        <Input
          id="perso-first_name"
          value={values.first_name}
          onChange={(e) => {
            setValues((v) => ({ ...v, first_name: e.target.value }))
          }}
        />
        {errors.first_name?.[0] && (
          <p className="text-destructive text-xs">{errors.first_name[0]}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="perso-dob">Date de naissance</Label>
        <Input
          id="perso-dob"
          type="date"
          value={values.dob}
          onChange={(e) => {
            setValues((v) => ({ ...v, dob: e.target.value }))
          }}
        />
        {errors.dob?.[0] && <p className="text-destructive text-xs">{errors.dob[0]}</p>}
      </div>

      <div className="space-y-2">
        <Label htmlFor="perso-sex">Sexe</Label>
        <select
          id="perso-sex"
          value={values.sex}
          onChange={(e) => {
            setValues((v) => ({ ...v, sex: e.target.value as 'M' | 'F' | 'X' }))
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          <option value="M">M</option>
          <option value="F">F</option>
          <option value="X">X / Autre</option>
        </select>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-2">
          <Label htmlFor="perso-city">
            Ville{' '}
            <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
          </Label>
          <Input
            id="perso-city"
            value={values.city ?? ''}
            onChange={(e) => {
              setValues((v) => ({ ...v, city: e.target.value || undefined }))
            }}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="perso-country">
            Pays <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
          </Label>
          <Input
            id="perso-country"
            list="perso-edit-countries"
            value={values.country ?? ''}
            onChange={(e) => {
              setValues((v) => ({ ...v, country: e.target.value || undefined }))
            }}
            autoComplete="country-name"
          />
          <datalist id="perso-edit-countries">
            {COMMON_COUNTRIES.map((c) => (
              <option key={c} value={c} />
            ))}
          </datalist>
        </div>
      </div>

      <label className="flex items-start gap-2 text-sm">
        <input
          type="checkbox"
          checked={values.consent_data_processing}
          onChange={(e) => {
            setValues((v) => ({ ...v, consent_data_processing: e.target.checked }))
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

      <div className="flex gap-2">
        <Button
          onClick={() => {
            void handleSave()
          }}
          disabled={loading}
        >
          {loading ? 'Sauvegarde...' : 'Enregistrer'}
        </Button>
        <Button variant="outline" onClick={handleCancel} disabled={loading}>
          Annuler
        </Button>
      </div>
    </section>
  )
}
