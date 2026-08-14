// Rendu lisible d'une séance. Le contenu vient du `Workout` typé (JSONB du worker) :
// on construit le JSX directement, sans passer par du markdown que rien ne convertit
// côté navigateur (issue #187).
import { cn } from '@/lib/utils'
import {
  fmtDeparture,
  fmtQuantity,
  fmtTarget,
  summaryLines,
  type Sport as CoachSport,
} from '@/lib/coach/session-templates'
import {
  isIntervalSet,
  type IntervalBlock,
  type IntervalSet,
  type MainBlock,
  type Workout,
} from '@/lib/coach/workout-types'

function TargetChip({
  block,
  sport,
}: {
  readonly block: IntervalBlock
  readonly sport: CoachSport
}) {
  const { zone, detail, rpe } = fmtTarget(block.target, sport)
  return (
    <span className="text-muted-foreground inline-flex flex-wrap items-baseline gap-x-1.5">
      <span className="bg-muted text-foreground rounded px-1.5 py-0.5 text-xs font-medium">
        {zone}
      </span>
      {detail && <span className="text-xs">{detail}</span>}
      {rpe !== null && <span className="text-xs">RPE {String(rpe)}</span>}
    </span>
  )
}

function BlockNotes({ notes }: { readonly notes: string | null | undefined }) {
  if (!notes) return null
  return <p className="text-muted-foreground mt-1 text-xs italic">{notes}</p>
}

function BlockLine({
  block,
  sport,
  reps,
  prefix,
}: {
  readonly block: IntervalBlock
  readonly sport: CoachSport
  readonly reps?: number
  readonly prefix?: string
}) {
  const { main, secondary } = fmtQuantity(block, sport)
  return (
    <div>
      <p className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        {prefix && <span className="text-muted-foreground text-xs">{prefix}</span>}
        <span className="text-foreground font-medium">
          {reps === undefined ? main : `${String(reps)} × ${main}`}
        </span>
        {secondary && <span className="text-muted-foreground text-xs">({secondary})</span>}
        <TargetChip block={block} sport={sport} />
      </p>
      <BlockNotes notes={block.notes} />
    </div>
  )
}

function SetLines({ set, sport }: { readonly set: IntervalSet; readonly sport: CoachSport }) {
  const departure = fmtDeparture(set, sport)
  return (
    <div className="space-y-1">
      <BlockLine block={set.work} sport={sport} reps={set.reps} />
      {departure ? (
        <p className="text-muted-foreground text-xs">{departure}</p>
      ) : (
        <BlockLine block={set.rest} sport={sport} prefix="Récup" />
      )}
      {/* La récup porte parfois la consigne utile (départ des séries, placement) :
          le markdown ne l'affichait jamais (issue #187). */}
      {departure ? <BlockNotes notes={set.rest.notes} /> : null}
    </div>
  )
}

function MainBlockItem({
  block,
  sport,
}: {
  readonly block: MainBlock
  readonly sport: CoachSport
}) {
  return isIntervalSet(block) ? (
    <SetLines set={block} sport={sport} />
  ) : (
    <BlockLine block={block} sport={sport} />
  )
}

function Step({ title, children }: { readonly title: string; readonly children: React.ReactNode }) {
  return (
    <div>
      <h4 className="text-muted-foreground text-xs font-semibold tracking-wide uppercase">
        {title}
      </h4>
      <div className="mt-1 space-y-2">{children}</div>
    </div>
  )
}

interface Props {
  workout: Workout
  sport: CoachSport
  className?: string
}

export function WorkoutDetail({ workout, sport, className }: Readonly<Props>) {
  const summary = summaryLines(workout.summary_md)
  return (
    <section
      aria-label="Séance détaillée"
      className={cn('space-y-3 rounded-md border p-4 text-sm', className)}
    >
      <Step title="Échauffement">
        <BlockLine block={workout.warmup} sport={sport} />
      </Step>
      <Step title="Corps de séance">
        <ul className="space-y-2">
          {/* Les blocs n'ont pas d'identifiant : leur position est leur identité. */}
          {workout.main.map((block, index) => (
            <li key={`block-${String(index)}`}>
              <MainBlockItem block={block} sport={sport} />
            </li>
          ))}
        </ul>
      </Step>
      <Step title="Retour au calme">
        <BlockLine block={workout.cooldown} sport={sport} />
      </Step>
      {summary.length > 0 && (
        <div className="space-y-1 border-t pt-3">
          {summary.map((line) => (
            <p key={line} className="text-muted-foreground text-sm">
              {line}
            </p>
          ))}
        </div>
      )}
      {workout.technical_focus && (
        <p className="border-primary/40 text-foreground border-l-2 pl-3 text-sm">
          <span className="font-medium">Focus technique : </span>
          {workout.technical_focus}
        </p>
      )}
    </section>
  )
}
