// The paper's insights (Section 4), word for word where the paper allows, with every number named as a
// numbers.tex macro in double braces. [[S1]] marks a seat chip, **x** bold and *x* italic.

export const DEFINITIONS =
  'A reply is **usable** when it was not cut off and carries no recorded fault, and a usable reply is **decided** when it chose an option that a seat asked for. Rates are shares of decided replies. A difference between two rates is absolute and written with a percent sign. Intervals are 95% bootstrap intervals over scenarios.'

export const INSIGHTS = [
  {
    id: 'boundary',
    section: 'Position and message boundaries',
    claim: 'The first line of a message wins.',
    bold: 'When two conflicting lines share one message, the first wins {{MergedFirstAllRange}} of decided replies, and in two messages that share falls by {{BoundaryAllRangeAbs}}.',
    evidence:
      'This holds on both halves of the scenarios. Across two messages the first line keeps {{SeparateFirstAllRange}}, and the later message wins in {{SeparateFirstAllDown}} of {{SeparateFirstAllN}} model-modes.',
    details:
      'The first line also wins inside the system message. When [[S1]] and [[S2]] share it, the second line wins only {{SysSecondAllRange}} of the time, below half in all {{SysSecondAllN}} model-modes. Across messages the families differ. On Qwen 3 the first of two messages keeps only {{SeparateFirstQwenThreeRange}}, while gpt-oss is close to even ({{SeparateFirstGptOssRange}}).',
    chart: 'boundary',
    figure: '2_message_boundary',
  },
  {
    id: 'order',
    section: 'Order against the operator line',
    claim: 'Whether order or the operator line wins depends on the family.',
    bold: 'Qwen 3 follows the later message, gpt-oss follows the developer message, and Qwen 3.5 is in between.',
    evidence:
      'When the user, tool and memory seats meet in both orders, the later line wins {{LaterWinsQwenThreeRange}} on Qwen 3, {{LaterWinsQwenThreeFiveRange}} on Qwen 3.5 and {{LaterWinsGptOssRange}} on gpt-oss. The operator line, always first in the Ladder, wins {{OpPinnedQwenThreeRange}} of its conflicts on Qwen 3, {{OpPinnedQwenThreeFiveRange}} on Qwen 3.5, and {{OpPinnedGptOssTwentyBOn}} and {{OpPinnedGptOssOneTwentyBOn}} on gpt-oss.',
    details:
      'Every Qwen 3 point lies below the dashed line, so on Qwen 3 the operator line wins less often than an early user, tool or memory line does against a later one. At a similar total size with the same serving software, gpt-oss-120b keeps its operator line {{OpPinnedGptOssOneTwentyBOn}} of the time, against {{OpPinnedQwenThreeFiveOneTwentyTwoBATenBOff}} and {{OpPinnedQwenThreeFiveOneTwentyTwoBATenBOn}} for Qwen3.5-122B-A10B. Counting every usable reply, including those in which gpt-oss takes no action, gpt-oss-120b is still higher, at {{OpPinnedAllDrawsGptOssOneTwentyBOn}} against {{OpPinnedAllDrawsQwenThreeFiveOneTwentyTwoBATenBOff}} and {{OpPinnedAllDrawsQwenThreeFiveOneTwentyTwoBATenBOn}}, while gpt-oss-20b falls to {{OpPinnedAllDrawsGptOssTwentyBOn}}. This matches how gpt-oss was trained, to rank system over developer over user messages, although its chat format and serving release also differ, and the family has only two models.',
    chart: 'order',
    figure: '3_order_vs_authority',
  },
  {
    id: 'role',
    section: 'Chat role against text label',
    claim: 'In tool and file-write tasks the system message lowers operator wins.',
    bold: 'When the task is to call a tool or write a file, an operator line sent first wins less often in the real system message than as the same labelled text in a user message, in every model-mode, by {{RoleLabelToolPathAllRangeAbs}}.',
    evidence:
      'The cost is {{RoleLabelToolPathQwenThreeRangeAbs}} on Qwen 3, {{RoleLabelToolPathQwenThreeFiveRangeAbs}} on Qwen 3.5 and {{RoleLabelToolPathGptOssRangeAbs}} on gpt-oss. All three chat formats write the tool definitions into the system or developer turn, so the real role places the operator line beside them and the labelled text after them, and this contrast does not separate the two.',
    details: [
      'On both halves it holds in {{RepRolelabelTpQwenThreeBoth}} of {{RepRolelabelTpQwenThreeN}} Qwen 3, {{RepRolelabelTpQwenThreeFiveBoth}} of {{RepRolelabelTpQwenThreeFiveN}} Qwen 3.5 and {{RepRolelabelTpGptOssBoth}} of {{RepRolelabelTpGptOssN}} gpt-oss model-modes. Over all task types the real role still lowers the operator line’s wins in every Qwen model-mode, by {{RoleLabelFirstQwenThreeRangeAbs}} on Qwen 3 and {{RoleLabelFirstQwenThreeFiveRangeAbs}} on Qwen 3.5, whereas on gpt-oss it helps in the other task types, by {{RoleLabelFormatGptOssRange}} in format and {{RoleLabelOrdRefGptOssRange}} in ordering and refusal.',
      'In format tasks, which offer no task tools, the drop appears in {{RoleLabelFormatAllDown}} of {{RoleLabelFormatAllN}} model-modes. Sent last, a gpt-oss developer message wins {{OpRealLastGptOssRange}} against {{OpLabelLastGptOssRange}} for the same labelled text. On Qwen 3, which accepts a late system message, sending the policy last raises the operator line’s wins by {{LateOpQwenThreeRangeAbs}}, to a majority in {{OpRealLastQwenThreeUp}} of {{OpRealLastQwenThreeN}} model-modes. In the Context set, where each line is placed inside realistic text, the gpt-oss operator line sent first falls by {{CtxOpGainGptOssRangeAbs}}, and on Qwen the change goes both ways.',
    ],
    chart: 'role',
    figure: '4_role_vs_label',
  },
  {
    id: 'task',
    section: 'Forecasting larger conflicts from pairs',
    claim: 'Knowing where the task line is improves the forecast in every model-mode.',
    bold: 'The task-aware fit forecasts larger conflicts better than the position fit in all {{TaskGainAllN}} model-modes, by {{TaskGainAllRangeAbs}} nats per reply.',
    evidence:
      'In the pairs, the later line on Qwen 3 wins less when both lines come before the task line than when the task comes first or between them, by {{TaskPosQwenThreeRangeAbs}}. A line after the task may read as a correction to it.',
    chart: 'forecast',
    figure: '5_prediction',
  },
  {
    id: 'seats',
    claim: 'Seat strengths help on Qwen 3.5 and gpt-oss but rarely on Qwen 3.',
    bold: 'Adding one strength per seat to the position fit improves the forecast in {{SrcGainQwenThreeFiveUp}} of {{SrcGainQwenThreeFiveN}} Qwen 3.5 model-modes and both gpt-oss models, but in only {{SrcGainQwenThreeUp}} of {{SrcGainQwenThreeN}} on Qwen 3.',
    evidence:
      'The gain reaches {{SrcGainQwenThreeFiveMax}} nats per reply on Qwen 3.5 and is {{SrcGainGptOssRangeAbs}} on gpt-oss.',
    details:
      'Added to the task-aware fit instead, seat strengths still help in {{SrcTaskGainQwenThreeFiveUp}} of {{SrcTaskGainQwenThreeFiveN}} Qwen 3.5 model-modes, both gpt-oss models and {{SrcTaskGainQwenThreeUp}} of {{SrcTaskGainQwenThreeN}} on Qwen 3. How much of the gap the position fit recovers still differs by family, with {{PosShareQwenThreeRange}} on Qwen 3, {{PosShareQwenThreeFiveRange}} on Qwen 3.5 and {{PosShareGptOssRange}} on gpt-oss.',
    chart: 'seatGain',
  },
  {
    id: 'tiers',
    section: 'Thinking, tiers, flagging and load',
    claim: 'Thinking helps follow declared tiers.',
    bold: 'With thinking on, Qwen models follow an explicit priority rule more often, at every Qwen 3 size from 4B up and every Qwen 3.5 size from 2B up.',
    evidence:
      'When each line carries a tier from 1 to 6, thinking raises the share of decided replies that follow the rule by up to {{ThinkTierQwenThreeFiveMax}} on Qwen 3.5, and Qwen3.5-122B-A10B goes from {{TierRuleQwenThreeFiveOneTwentyTwoBATenBOff}} to {{TierRuleQwenThreeFiveOneTwentyTwoBATenBOn}}. However, in all {{TierCapacityUpperAllN}} model-modes the data rule out that even two declared tiers are followed in 95% of usable replies.',
    details:
      'Here a reply that acts on neither option counts as a failure, so Qwen3.5-27B with thinking on follows the rule in {{TierRuleQwenThreeFiveTwentySevenBOn}} of decided replies but {{TierRuleAllDrawsQwenThreeFiveTwentySevenBOn}} of usable ones.',
    chart: 'thinkTier',
    figure: '6_thinking',
  },
  {
    id: 'thinkop',
    claim: 'Thinking raises the operator line on Qwen 3.',
    bold: 'With the operator line first in the real system message, thinking raises its wins at {{ThinkOpQwenThreeUp}} of {{ThinkOpQwenThreeN}} Qwen 3 sizes ({{ThinkOpQwenThreeRange}}), {{RepThinkopupQwenThreeBoth}} of them on both halves.',
    evidence:
      'On Qwen 3.5 it lowers them at {{ThinkOpQwenThreeFiveDown}} of {{ThinkOpQwenThreeFiveN}} sizes (over all of them, {{ThinkOpQwenThreeFiveRange}}), but only {{RepThinkopdownQwenThreeFiveBoth}} of these hold on both halves.',
    chart: 'thinkOp',
    figure: '6_thinking',
  },
  {
    id: 'flags',
    claim: 'Models rarely say there is a conflict.',
    bold: 'In every model-mode, at most {{FlagShareAllMax}} of decided pair replies flag the conflict or hedge by our keyword patterns, so a decided reply rarely tells the user that an instruction was dropped.',
    evidence: 'The number of instructions in a prompt shows no consistent effect across families in the Load bundles.',
    chart: 'flags',
  },
]

export const IMPLICATIONS = [
  'For tool and file-write tasks, test where a policy is placed instead of assuming the system prompt protects it, since a policy sent first there wins less often than the same words in a user turn in all {{RoleLabelToolPathAllN}} model-modes.',
  'On Qwen 3 and gpt-oss, test sending the policy after the competing line, which raises its wins by {{LateOpQwenThreeRangeAbs}} on Qwen 3 and {{LateOpGptOssRangeAbs}} on gpt-oss, although on Qwen 3 it then wins a majority in only {{OpRealLastQwenThreeUp}} of {{OpRealLastQwenThreeN}} model-modes and recency also favours injected lines.',
  'Test conflicts across messages as well as inside one, because the first line’s advantage shrinks across messages.',
  'Before ranking seats, model where the task line is, since doing so improves the forecast of larger conflicts in all {{TaskGainAllN}} model-modes.',
  'Test each conflict on several scenarios and replies, since even the empirical reference names the winner in only {{CeilTopOneAllRange}} of replies.',
  'Do not count on declared tiers or on a warning, since no model keeps even two tiers in order in 95% of usable replies and few replies mention the conflict.',
]

// The Conclusion's three results, with one generated number each for the home page.
export const HEADLINES = [
  {
    to: 'boundary',
    text: 'In every model the first of two lines in one message wins most decided replies, and on Qwen the later line often wins across messages.',
    stat: '{{MergedFirstAllRange}}',
    statLabel: 'of decided replies go to the first line inside one message',
  },
  {
    to: 'role',
    text: 'A policy sent first in the system message wins most of its decided conflicts with later lines only on gpt-oss, and in tool and file-write tasks it wins less often than the same text sent first as a labelled user message, in every model-mode.',
    stat: '{{RoleLabelToolPathAllRangeAbs}}',
    statLabel: 'fewer operator wins in the real system message than as labelled user text, in tool and file-write tasks',
  },
  {
    to: 'task',
    text: 'Pair forecasts of larger conflicts improve in all model-modes once they model where the task line is in the prompt.',
    stat: '{{TaskGainAllRangeAbs}}',
    statLabel: 'nats per reply gained by knowing where the task line is',
  },
]
