import React from 'react';

/**
 * A release-safe empty state until Jetts-TUI users submit verifiable examples.
 * The previous collage depended on a gitignored, upstream-only JSON file and
 * made clean-checkout documentation builds fail.
 */
export default function UserStoriesCollage(): React.JSX.Element {
  return (
    <main className="container margin-vert--lg">
      <h1>Community stories</h1>
      <div className="alert alert--info" role="status">
        We are collecting the first verified Jetts-TUI stories. This page will
        show examples once contributors have approved their publication.
      </div>
      <p>
        Built something useful with Jetts-TUI? Share what you made, the features
        you used, and a public link or reproducible example in a{' '}
        <a href="https://github.com/Raioshok/JETTS-TUI/issues/new">
          GitHub issue
        </a>
        . Please do not include API keys, private prompts, or personal data.
      </p>
    </main>
  );
}
