'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { toast } from 'sonner'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { addAllowedEmail, removeAllowedEmail } from '../actions'
import type { AllowedEmailRow } from '@/lib/admin/types'

export function AllowlistTable({ rows }: { readonly rows: AllowedEmailRow[] }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [email, setEmail] = useState('')
  const [note, setNote] = useState('')

  function handleAdd() {
    startTransition(async () => {
      const result = await addAllowedEmail({ email, note: note || null })
      if (!result.success) {
        toast.error("Ajout impossible. Vérifie l'email ou réessaie plus tard.")
        return
      }
      setEmail('')
      setNote('')
      router.refresh()
    })
  }

  function handleRemove(target: string) {
    startTransition(async () => {
      const result = await removeAllowedEmail(target)
      if (!result.success) {
        toast.error('Suppression impossible.')
        return
      }
      router.refresh()
    })
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label="Email à ajouter à l'allowlist"
          placeholder="ami@example.com"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
          }}
          className="max-w-xs"
        />
        <Input
          aria-label="Note (optionnel)"
          placeholder="Note (optionnel)"
          value={note}
          onChange={(e) => {
            setNote(e.target.value)
          }}
          className="max-w-xs"
        />
        <Button disabled={pending || !email} onClick={handleAdd}>
          Ajouter
        </Button>
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Email</TableHead>
            <TableHead>Statut</TableHead>
            <TableHead>Note</TableHead>
            <TableHead>
              <span className="sr-only">Actions</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row) => (
            <TableRow key={row.email}>
              <TableCell>{row.email}</TableCell>
              <TableCell>
                <Badge variant={row.status === 'active' ? 'default' : 'secondary'}>
                  {row.status === 'active' ? 'Actif' : 'En attente'}
                </Badge>
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">{row.note ?? '—'}</TableCell>
              <TableCell>
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button size="sm" variant="outline" aria-label={`Retirer ${row.email}`}>
                      Retirer
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Retirer {row.email} ?</AlertDialogTitle>
                      <AlertDialogDescription>
                        Bloque toute future inscription avec cet email. Si {row.email} a déjà un
                        compte actif, son accès n&rsquo;est pas révoqué.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Annuler</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => {
                          handleRemove(row.email)
                        }}
                      >
                        Retirer
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
