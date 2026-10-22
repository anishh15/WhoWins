// Copy for the seat matchups page. Numbers are generated values named in double braces.

export const MATCHUPS = {
  lead: 'How often one seat’s line beats another’s in the Ladder pairs, for one model-mode at a time.',
  gridNote: 'Each cell is a share of decided replies, with its {{IntervalLevel}} interval. [[S1]] and [[S2]] always come first, in the system (or developer) message, so they count together as the operator line.',
  secondLine: 'second line of the system (or developer) message wins',
  opFirst: 'the operator line, sent first, beats a later user, tool or memory line',
  laterOp: 'a later user, tool or memory line beats the operator line',
  layouts: 'The operator line in the real system (or developer) message or as the same labelled text in a user message, first or last.',
  noLate: 'Not possible: the template rejects a late system message.',
  reading: 'Darker red means a larger share; grey italic means the {{IntervalLevel}} interval includes {{ShareNull}}. Pairwise results alone cannot determine what a model does when three or more instructions conflict.',
  pairsLead: 'The three free pairs for all model-modes, as in Figure 7 of the paper: decided free Ladder pairs, both orders weighted equally.',
}
