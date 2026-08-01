// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { canSharePng, canvasToPngBlob, downloadBlob, sharePng } from '@/lib/share/export-png'

function canvasReturning(blob: Blob | null): HTMLCanvasElement {
  return {
    toBlob: (callback: BlobCallback) => {
      callback(blob)
    },
  } as unknown as HTMLCanvasElement
}

describe('canvasToPngBlob', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('résout le blob produit par le canvas', async () => {
    const blob = new Blob(['x'], { type: 'image/png' })
    await expect(canvasToPngBlob(canvasReturning(blob))).resolves.toBe(blob)
  })

  it('résout null si l’encodage échoue', async () => {
    await expect(canvasToPngBlob(canvasReturning(null))).resolves.toBeNull()
  })
})

describe('downloadBlob', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  function stubUrl() {
    const createObjectURL = vi.fn(() => 'blob:fake')
    const revokeObjectURL = vi.fn()
    vi.stubGlobal('URL', { ...URL, createObjectURL, revokeObjectURL })
    const click = vi.fn()
    const anchor = document.createElement('a')
    anchor.click = click
    vi.spyOn(document, 'createElement').mockReturnValue(anchor)
    return { createObjectURL, revokeObjectURL, click, anchor }
  }

  it('crée un lien, le clique et libère l’URL', () => {
    vi.useFakeTimers()
    const { createObjectURL, revokeObjectURL, click, anchor } = stubUrl()

    downloadBlob(new Blob(['x']), 'calque.png')

    expect(createObjectURL).toHaveBeenCalledOnce()
    expect(anchor.download).toBe('calque.png')
    expect(click).toHaveBeenCalledOnce()
    expect(document.body.contains(anchor)).toBe(false)

    vi.runAllTimers()
    expect(revokeObjectURL).toHaveBeenCalledWith('blob:fake')
  })

  it('ne libère pas l’URL avant que le téléchargement ait pu démarrer', () => {
    vi.useFakeTimers()
    const { revokeObjectURL } = stubUrl()

    downloadBlob(new Blob(['x']), 'calque.png')

    // Safari annule un téléchargement dont l'URL objet est révoquée dans la foulée du clic.
    expect(revokeObjectURL).not.toHaveBeenCalled()
  })
})

describe('canSharePng', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renvoie false sans Web Share API', () => {
    expect(canSharePng()).toBe(false)
  })

  it('renvoie false quand canShare refuse les fichiers', () => {
    vi.stubGlobal('navigator', { share: vi.fn(), canShare: () => false })
    expect(canSharePng()).toBe(false)
  })

  it('renvoie false quand canShare lève', () => {
    vi.stubGlobal('navigator', {
      share: vi.fn(),
      canShare: () => {
        throw new Error('nope')
      },
    })
    expect(canSharePng()).toBe(false)
  })

  it('renvoie true quand le navigateur accepte un fichier', () => {
    vi.stubGlobal('navigator', { share: vi.fn(), canShare: () => true })
    expect(canSharePng()).toBe(true)
  })
})

describe('sharePng', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renvoie unsupported quand l’API manque', async () => {
    await expect(sharePng(new Blob(['x']), 'a.png', 'Titre')).resolves.toBe('unsupported')
  })

  it('renvoie shared quand le partage aboutit', async () => {
    const share = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { share, canShare: () => true })
    await expect(sharePng(new Blob(['x']), 'a.png', 'Titre')).resolves.toBe('shared')
    expect(share).toHaveBeenCalledOnce()
  })

  it('renvoie cancelled quand l’utilisateur ferme la feuille', async () => {
    const error = new Error('cancelled')
    error.name = 'AbortError'
    vi.stubGlobal('navigator', { share: vi.fn().mockRejectedValue(error), canShare: () => true })
    await expect(sharePng(new Blob(['x']), 'a.png', 'Titre')).resolves.toBe('cancelled')
  })

  it('renvoie failed sur toute autre erreur', async () => {
    vi.stubGlobal('navigator', {
      share: vi.fn().mockRejectedValue(new Error('boom')),
      canShare: () => true,
    })
    await expect(sharePng(new Blob(['x']), 'a.png', 'Titre')).resolves.toBe('failed')
  })
})

describe('canSharePng — capacité partielle', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renvoie false quand share existe mais pas canShare', () => {
    vi.stubGlobal('navigator', { share: vi.fn() })
    expect(canSharePng()).toBe(false)
  })
})
