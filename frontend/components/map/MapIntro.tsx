const INTRO_PARAGRAPHS = [
  `Our interactive map gives a general overview of state legislation addressing Missing and Murdered Indigenous Women, Girls, Trans, and Two-Spirit relatives (MMIWGT2S). Each state is grouped by the status of MMIWGT2S-related bills introduced since 2020: passed, failed, or still pending. A state's color reflects legislative activity, not the safety of Indigenous communities or the strength of a law's implementation. A bill that passes may still lack funding, enforcement, or tribal consultation, and a state with no legislation may still have strong community-led efforts underway.`,
  `The map is a starting point. For bill text, summaries, and UIC's analysis of each policy's strengths and gaps, see the Policy Table below. If a term is unfamiliar, our Glossary of Key Terms explains the language of this work through an Indigenous lens.`,
];

type MapIntroProps = {
  /** Footnote under intro copy — empty-state message or “Policies current as of …”. */
  statusLine?: string | null;
  statusBusy?: boolean;
};

export function MapIntro({ statusLine = null, statusBusy = false }: MapIntroProps) {
  return (
    <section className="mt-section-sm lg:mt-section-lg">
      <div className="grid gap-hero-stack sm:gap-hero-stack-sm lg:grid-cols-[var(--grid-title-col)_minmax(0,1fr)] lg:items-start lg:gap-hero-col">
        <h1 className="max-w-title font-mono text-[length:var(--text-hero-fluid)] font-bold leading-hero text-accent lg:pl-title-inset lg:text-hero">
          <span className="whitespace-nowrap">Missing &amp; Murdered</span>
          <br />
          <span className="whitespace-nowrap">Indigenous Persons</span>
          <br />
          Policies
        </h1>

        <div className="max-w-intro space-y-6 uic-body-sm text-foreground">
          {INTRO_PARAGRAPHS.map((paragraph) => (
            <p key={paragraph.slice(0, 32)}>{paragraph}</p>
          ))}
          {statusBusy ? (
            <p
              className="font-semibold text-foreground-muted"
              aria-busy="true"
            >
              Loading policy status…
            </p>
          ) : statusLine ? (
            <p className="font-semibold text-foreground-muted">{statusLine}</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
