// Copy for the home page. Every number is a generated value named in double braces (site_data.py).

export const HERO = {
  eyebrow: 'A benchmark of instruction conflicts in LLM agents',
  lead: 'When an agent’s instructions disagree, which one does the model follow? WhoWins keeps the words of each instruction fixed and changes only how it arrives: its position, chat role and label.',
}

export const KPIS = [
  { value: '{{NScenarios}}', label: 'scenarios', note: '{{design:task_types}} task types' },
  { value: '{{design:seats}}', label: 'seats', note: 'operator to memory' },
  { value: '{{NExperiments}}', label: 'experiments', note: 'one change each' },
  { value: '{{NModels}}', label: 'open-weight models', note: 'Qwen 3, Qwen 3.5, gpt-oss' },
  { value: '{{NModelModes}}', label: 'model-modes', note: 'thinking off and on' },
  { value: '{{TotalDraws}}', label: 'scored replies', note: 'scored by code' },
]

export const STEPS = [
  {
    title: 'A scenario',
    text: 'A task and up to {{design:options.1:word}} options that no reply can satisfy together. In Box 1, the casings of one key.',
  },
  {
    title: 'Seats and experiments',
    text: 'Each option is placed in a seat, a message with its own position, chat role and label. Each experiment changes one thing about the delivery and keeps the text fixed.',
  },
  {
    title: 'Scored by code',
    text: '{{design:trace_checkers}} trace checkers and {{design:format_classifiers}} format classifiers turn each reply into one label: the option it chose, or why it chose none.',
  },
]

export const STUDY = {
  title: 'What the study found',
  lead: 'The winner depends on position and message boundaries as well as on the role. These are the paper’s three main results.',
}
