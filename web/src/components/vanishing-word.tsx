/*
  The word disappears the way the sentence says it does. Each letter is its own
  animated element so the fade can travel across the word instead of dropping
  it all at once — the sentence stays readable throughout, and assistive tech
  reads the plain word from the visually hidden copy.

  Shared by the dashboard hero and the login page: it is the one piece of the
  brand that moves, so both places have to move identically.
*/
export function VanishingWord({ word }: { word: string }) {
  return (
    <span className="text-brand">
      <span className="sr-only">{word}</span>
      <span aria-hidden="true" className="vanish">
        {[...word].map((letter, index) => (
          <span key={index} style={{ "--letter": index } as React.CSSProperties}>
            {letter}
          </span>
        ))}
      </span>
    </span>
  )
}
