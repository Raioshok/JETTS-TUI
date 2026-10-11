import { Children, createContext, type CSSProperties, isValidElement, type ReactNode } from 'react'

/**
 * True for content rendered inside a ticker row. The ticker is a one-line
 * window, so a row must stay one line there: an expanded tool row (its bordered
 * card and detail body) would be clipped mid-line into a garbled sliver. Rows
 * read this to render collapsed and non-interactive while ticking; their own
 * open state is kept and comes back once the run settles and lists in full.
 */
export const ToolTickerContext = createContext(false)

/**
 * A one-line window over a growing list of rows.
 *
 * Each new row slides the one before it up and out, so activity that would
 * otherwise grow down the page reads as a single line ticking over in place.
 * Rows are clipped to a uniform line box so the reel's offset stays exact
 * whatever a row happens to contain.
 *
 * Shared by the tool run (its calls) and a delegation card (each subagent's
 * relayed stream), which are the same thing seen from two sides.
 */
export function ToolRunTicker({ children }: { children: ReactNode }) {
  const rows = Children.toArray(children)

  return (
    <ToolTickerContext.Provider value={true}>
      <div className="tool-ticker" data-tool-ticker="">
        <div className="tool-ticker__reel" style={{ '--tool-ticker-index': rows.length - 1 } as CSSProperties}>
          {rows.map((row, index) => (
            // Inert: rows scrolled out of the window must not take clicks or
            // keyboard focus, and the visible one can't unfold in a single line.
            <div className="tool-ticker__row" inert key={isValidElement(row) ? (row.key ?? index) : index}>
              {row}
            </div>
          ))}
        </div>
      </div>
    </ToolTickerContext.Provider>
  )
}
