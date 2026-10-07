import { Component, type ErrorInfo, type ReactNode } from 'react'

/**
 * A screen that throws must say so.
 *
 * React unmounts the whole tree when a render throws, which in a browser looks
 * like a blank white page and gives nobody anything to act on.  This catches
 * that, keeps the rest of the app alive, and shows what happened — which is the
 * difference between "the map is not rendering" and "the map is not rendering,
 * and here is the error".
 */
export class ErrorBoundary extends Component<
  { children: ReactNode; label?: string },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Console first: the message is more useful there than in the UI.
    console.error(
      `MoveIn ${this.props.label ?? 'screen'} failed to render`,
      error,
      info.componentStack,
    )
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="screen screen--error">
        <div className="card card--pad">
          <h2>Something broke on this screen</h2>
          <p className="muted small">
            {this.props.label ? `The ${this.props.label} screen` : 'This screen'} stopped
            rendering. The rest of MoveIn still works.
          </p>
          <pre className="error__detail">{error.message}</pre>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      </div>
    )
  }
}
