import { Eyebrow, Card } from '../components/ui'

export default function Placeholder({ title }: { title: string }) {
  return (
    <div className="fadeup">
      <Eyebrow>Agriculture</Eyebrow>
      <h1 className="display text-3xl font-semibold mt-2 mb-1">{title}</h1>
      <p className="text-[var(--color-mute)] text-sm mb-6">Being reinvented in the new design system.</p>
      <Card className="p-8 text-center text-[var(--color-faint)] text-sm">
        This agriculture page is next in the rollout.
      </Card>
    </div>
  )
}
