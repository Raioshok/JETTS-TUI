import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { en } from '@/i18n/en'
import { type PetSessionFeedItem, petSessionFeedLabels } from '@/store/pet-sessions'

import { PetSessionFeed } from './pet-session-feed'

const labels = petSessionFeedLabels(en.petSessions)

const item = (id: string, patch: Partial<PetSessionFeedItem> = {}): PetSessionFeedItem => ({
  id,
  startedAt: null,
  status: 'working',
  title: `Session ${id}`,
  ...patch
})

describe('PetSessionFeed', () => {
  it('renders nothing without sessions', () => {
    const { container } = render(<PetSessionFeed items={[]} labels={labels} onOpen={() => undefined} />)

    expect(container.firstChild).toBeNull()
  })

  it('shows status per row, falls back to the untitled label, and opens on click', () => {
    const onOpen = vi.fn()

    render(
      <PetSessionFeed
        items={[item('a', { status: 'needs-input' }), item('b', { status: 'finished', title: '' })]}
        labels={labels}
        onOpen={onOpen}
      />
    )

    expect(screen.getByText(labels.status['needs-input'])).toBeTruthy()
    expect(screen.getByText(labels.untitled)).toBeTruthy()

    fireEvent.click(screen.getByText('Session a'))
    expect(onOpen).toHaveBeenCalledExactlyOnceWith('a')
  })

  it('collapses overflow into a count chip', () => {
    render(
      <PetSessionFeed items={['a', 'b', 'c', 'd', 'e'].map(id => item(id))} labels={labels} onOpen={() => undefined} />
    )

    expect(screen.getAllByRole('listitem')).toHaveLength(3)
    expect(screen.getByText(labels.more.replace('{count}', '2'))).toBeTruthy()
  })

  it('keeps a row click from starting a pet drag', () => {
    const onPointerDown = vi.fn()

    render(
      <div onPointerDown={onPointerDown}>
        <PetSessionFeed items={[item('a')]} labels={labels} onOpen={() => undefined} />
      </div>
    )

    fireEvent.pointerDown(screen.getByText('Session a'))
    expect(onPointerDown).not.toHaveBeenCalled()
  })
})
