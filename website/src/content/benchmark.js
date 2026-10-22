// What the benchmark is made of, as the paper and the README describe it. Numbers are generated values
// named in double braces; scenario, trial and reply counts are in site.json.

export const TASK_TYPES = {
  tool: { title: 'Tool', scores: 'which tool is called first', detail: 'Five stub tools; the code reads which one the model calls first.' },
  'file-write': { title: 'File write', scores: 'where the first file is written', detail: 'Five destinations inside a sandbox; the code reads where the first write goes.' },
  format: { title: 'Format', scores: 'one property of the output’s format', detail: 'Key casing, delimiters, date encodings, list styles, units and more, each with its own classifier.' },
  ordering: { title: 'Ordering', scores: 'the order of three steps', detail: 'The order in which three marked steps are first performed.' },
  refusal: { title: 'Refusal', scores: 'whether a gated action is refused or run', detail: 'Two options, run the gated action or decline it, so refusal enters only two-way conflicts.' },
}

export const SEAT_INFO = {
  S1: { source: 'Operator', where: 'the system message (the developer message on gpt-oss)' },
  S2: { source: 'Repository configuration', where: 'the same system message, under its own label' },
  S3: { source: 'User', where: 'a plain user message' },
  S4: { source: 'Tool result', where: 'the result of a `config_read` call already in the transcript' },
  S5: { source: 'Memory note', where: 'a user message with its own label' },
}

export const EXPERIMENT_INFO = {
  ladder: { moves: 'which seats compete ({{design:ladder_sizes:words}} at a time) and their order', fixed: 'the text; the system seats come first; each option is also asked alone' },
  operator: { moves: 'the operator line in the real system message or as the same labelled text in a user message; first or last', fixed: 'the text; the opposing seat (user, tool or memory)' },
  message: { moves: 'the user line and the memory note in separate messages or inside the task’s message; their order', fixed: 'the text; the roles' },
  realism: { moves: 'instructions bare or placed inside realistic text, such as an operator prompt; their order', fixed: 'the text; {{design:context_scenarios}} tool and file-write scenarios' },
  free: { moves: 'two or more seats ask for the same option ({{design:agreement_seats:range}} seats)', fixed: 'the text; seats dealt as in the Ladder' },
  load: { moves: 'the number of instructions ({{design:load_instructions:range}}) and, at a fixed length, the number of conflicts', fixed: 'the length at each number; one operator message' },
  tier: { moves: 'each instruction carries a declared priority from {{design:tiers:range}}, and the lower number wins', fixed: 'the text; one draw per trial' },
}

export const OUTCOMES = [
  ['chose', 'exactly one value among the options shown in the trial'],
  ['unresolved', 'an artifact no classifier could label'],
  ['off-menu', 'a clean value no option in the trial asked for'],
  ['multiple', 'two or more options’ values, for example two fenced answers'],
  ['no action', 'the trace holds no action of the kind the task is scored on'],
]

export const TRIAL_NOTE =
  'Each trial is shown exactly as the code builds it for Qwen3-8B with thinking off. Underlined text is an option; the chip names the seat that carries it. On gpt-oss the system message is sent as the developer message.'
