import { ConfirmDialog } from '@/components/ui/confirm-dialog'
import { useI18n } from '@/i18n'
import { deleteProfile } from '@/jettstui'
import { prepareProfileFollow } from '@/store/profile'

// Thin wrapper over ConfirmDialog: owns the deleteProfile call, inherits
// Enter-to-confirm + busy/done/error from the shared dialog. The single choke
// point for every delete entry point (rail + Profiles view).
export function DeleteProfileDialog({
  profile,
  onClose,
  onDeleted,
  open
}: {
  profile: { name: string; path: string } | null
  onClose: () => void
  onDeleted?: () => Promise<void> | void
  open: boolean
}) {
  const { t } = useI18n()
  const p = t.profiles

  return (
    <ConfirmDialog
      busyLabel={p.deleting}
      confirmLabel={t.common.delete}
      description={
        profile ? (
          <>
            {p.deleteDescPrefix}
            <span className="font-medium text-foreground">{profile.name}</span>
            {p.deleteDescMid}
            <span className="font-mono text-xs">{profile.path}</span>
            {p.deleteDescSuffix}
          </>
        ) : null
      }
      destructive
      doneLabel={p.deleted}
      onClose={onClose}
      onConfirm={async () => {
        if (!profile) {
          return
        }

        // Deleting the profile the live gateway is on strands it on a dead
        // backend; follow it to default *after* the host's onDeleted refresh so
        // ours is the last write.
        const follow = prepareProfileFollow(profile.name)
        await deleteProfile(profile.name)
        await onDeleted?.()
        follow(null)
      }}
      open={open}
      title={p.deleteTitle}
    />
  )
}
