export type ShareResult = 'shared' | 'cancelled' | 'unsupported' | 'failed'

/** `canvas.toBlob()` en promesse. Résout `null` si l'encodage échoue. */
export async function canvasToPngBlob(canvas: HTMLCanvasElement): Promise<Blob | null> {
  return new Promise((resolve) => {
    canvas.toBlob((blob) => {
      resolve(blob)
    }, 'image/png')
  })
}

/**
 * Délai avant de libérer l'URL objet. Révoquer dans la foulée du `click()` annule le
 * téléchargement sur les navigateurs qui ne l'ont pas encore démarré (Safari en tête).
 */
const REVOKE_DELAY_MS = 1000

/** Déclenche un téléchargement navigateur pour un blob déjà encodé. */
export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  document.body.append(link)
  link.click()
  link.remove()
  setTimeout(() => {
    URL.revokeObjectURL(url)
  }, REVOKE_DELAY_MS)
}

/** `true` si le navigateur sait partager un fichier image (Web Share API niveau 2). */
export function canSharePng(): boolean {
  if (typeof navigator === 'undefined' || typeof File === 'undefined') return false
  if (typeof navigator.share !== 'function' || typeof navigator.canShare !== 'function') {
    return false
  }
  try {
    return navigator.canShare({ files: [new File([], 'probe.png', { type: 'image/png' })] })
  } catch {
    return false
  }
}

/**
 * Partage le PNG via la feuille de partage native (Instagram, Messages…).
 * Sur desktop, l'API n'accepte pas les fichiers : l'appelant retombe sur le téléchargement.
 *
 * IMPORTANT : `navigator.share()` doit être atteint sans `await` intermédiaire depuis le
 * gestionnaire de clic — Safari iOS révoque l'activation utilisateur dès le premier await et
 * rejette alors avec `NotAllowedError`. La fonction est bien `async`, mais son corps s'exécute
 * de façon synchrone jusqu'à l'appel ; c'est à l'appelant de ne pas encoder le blob avant.
 */
export async function sharePng(blob: Blob, fileName: string, title: string): Promise<ShareResult> {
  if (!canSharePng()) return 'unsupported'
  const file = new File([blob], fileName, { type: 'image/png' })
  try {
    await navigator.share({ files: [file], title })
    return 'shared'
  } catch (error) {
    // L'utilisateur qui ferme la feuille de partage renvoie AbortError : ce n'est pas une erreur.
    if (error instanceof Error && error.name === 'AbortError') return 'cancelled'
    return 'failed'
  }
}
