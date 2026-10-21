"""Fixtures for `fmt/prose.py` -- the editorial keys read off a whole passage.
Longer than other fixtures on purpose: several of these rules agree on any single example,
so the passage has to carry the case that separates them."""

from whowins.checkers.core import UNRESOLVED

FIXTURES: list[tuple[str, str, str]] = [
    ("count_plural_handling", "matched_to_count", "1 draft is waiting"),
    ("count_plural_handling", "parenthesised_s", "1 draft(s) waiting"),
    ("count_plural_handling", "always_plural", "1 drafts waiting"),
    ("count_plural_handling", "slash_pair", "1 draft/drafts waiting"),
    ("count_plural_handling", "label_colon_count", "Drafts: 1"),

    # A person's surname AND an organisation's in every sample: the absolute rules and the people-only rule agree on any single example.
    ("possessive_s_style", "apostrophe_s_always",
     "Jones's report and Harper Systems's filing"),
    ("possessive_s_style", "bare_apostrophe_always",
     "Jones' report and Harper Systems' filing"),
    ("possessive_s_style", "s_for_people_only",
     "Jones's report and Harper Systems' filing"),
    ("possessive_s_style", "of_construction",
     "the report of Jones and the filing of Harper Systems"),
    ("possessive_s_style", "attributive_no_marker",
     "the Jones report and the Harper Systems filing"),

    ("serial_comma_policy", "serial_comma_always", "Fast, secure, and simple."),
    ("serial_comma_policy", "serial_comma_never", "Fast, secure and simple."),
    ("serial_comma_policy", "no_final_conjunction", "Fast, secure, simple."),
    ("serial_comma_policy", "semicolon_series", "Fast; secure; and simple."),
    ("serial_comma_policy", "broken_to_bullets", "- Fast\n- Secure\n- Simple"),

    # Each carries a quoted question, a semicolon and a comma, because the five rules are separated only by all three placements together.
    ("quote_punctuation_placement", "commas_periods_inside",
     'He said "it works," then asked "why now?" and paused "for a while"; we moved on.'),
    ("quote_punctuation_placement", "question_marks_outside",
     'He said "it works," then asked "why now"? and paused "for a while;" we moved on.'),
    ("quote_punctuation_placement", "all_inside",
     'He said "it works," then asked "why now?" and paused "for a while;" we moved on.'),
    ("quote_punctuation_placement", "all_outside",
     'He said "it works", then asked "why now"? and paused "for a while"; we moved on.'),
    ("quote_punctuation_placement", "colons_semicolons_inside",
     'He said "it works", then asked "why now"? and paused "for a while;" we moved on.'),

    ("compound_modifier_hyphenation", "always_hyphenated",
     "Use the read-only command-line tool on a 64-bit host."),
    ("compound_modifier_hyphenation", "always_open",
     "Use the read only command line tool on a 64 bit host."),
    ("compound_modifier_hyphenation", "hyphen_with_number_only",
     "Use the read only command line tool on a 64-bit host."),
    ("compound_modifier_hyphenation", "closed_single_word",
     "Use the readonly commandline tool on a 64 bit host."),
    ("compound_modifier_hyphenation", "en_dash_join",
     "Use the read–only command–line tool on a 64 bit host."),
    # Told to hyphenate only where a number leads, a writer with no number-led pair emits exactly this, and it can be scored for neither option.
    ("compound_modifier_hyphenation", UNRESOLVED,
     "Use the read only command line tool on the build host."),

    ("post_colon_capitalisation", "always_capital",
     "Simple pricing: Built for teams\nFair billing: Only what you use"),
    ("post_colon_capitalisation", "always_lowercase",
     "Simple pricing: built for teams\nFair billing: only what you use"),
    ("post_colon_capitalisation", "dash_instead",
     "Simple pricing — built for teams\nFair billing — only what you use"),
    ("post_colon_capitalisation", "line_break_instead",
     "Simple pricing\nBuilt for teams"),
    ("post_colon_capitalisation", "no_colon_period_instead",
     "Simple pricing. Built for teams\nFair billing. Only what you use"),

    ("aside_setting", "parentheses", "The build step (which runs nightly) copies the assets."),
    ("aside_setting", "comma_pair", "The build step, which runs nightly, copies the assets."),
    ("aside_setting", "dash_pair",
     "The build step — which runs nightly — copies the assets."),
    ("aside_setting", "moved_to_note",
     "The build step copies the assets.[1]\n\n[1] It runs nightly."),
    ("aside_setting", "own_sentence", "The build step copies the assets. It runs nightly."),

    ("figure_reference_style", "word_and_number",
     "Growth slowed in the second half, as Figure 3 shows."),
    ("figure_reference_style", "abbreviated_and_number",
     "Growth slowed in the second half, as Fig. 3 shows."),
    ("figure_reference_style", "bracketed_number", "Growth slowed in the second half (3)."),
    ("figure_reference_style", "positional_phrase",
     "Growth slowed in the second half, as the chart below shows."),
    ("figure_reference_style", "title_quoted",
     'Growth slowed in the second half, as "Revenue by segment" shows.'),

    ("address_line_order", "street_town_postcode_country",
     "12 Mill Street\nHarrogate\nHG1 2QT\nIreland"),
    ("address_line_order", "street_postcode_town_country",
     "12 Mill Street\nHG1 2QT\nHarrogate\nIreland"),
    ("address_line_order", "country_first_descending",
     "Ireland\nHG1 2QT\nHarrogate\n12 Mill Street"),
    ("address_line_order", "single_line_joined",
     "12 Mill Street, Harrogate, HG1 2QT, Ireland"),
    ("address_line_order", "postcode_last_line",
     "12 Mill Street\nHarrogate\nIreland\nHG1 2QT"),

    ("latin_abbreviation_policy", "periods_and_comma",
     "Samples were excluded, e.g., duplicates and blanks."),
    ("latin_abbreviation_policy", "periods_no_comma",
     "Samples were excluded, e.g. duplicates and blanks."),
    ("latin_abbreviation_policy", "no_periods_no_comma",
     "Samples were excluded, eg duplicates and blanks."),
    ("latin_abbreviation_policy", "english_equivalents",
     "Samples were excluded, for example duplicates and blanks."),
    ("latin_abbreviation_policy", "latin_in_brackets_only",
     "Samples were excluded, for example duplicates (e.g. blanks)."),
]

FIXTURES += [
    # fmt-0164: a passage carrying only a person, or only an organisation, cannot separate the people-only rule from the two absolute ones.
    ("possessive_s_style", UNRESOLVED, "Jones's report was filed on Tuesday."),
    # fmt-0166: without both a quoted question and a semicolon, three of the five rules agree and the sample decides nothing.
    ("quote_punctuation_placement", UNRESOLVED, 'He said "it works," and we moved on.'),
    # fmt-0172: an aside given its own sentence and THEN parenthesised.
    ("aside_setting", UNRESOLVED, "The build step copies the assets. (It runs nightly.)"),
    # fmt-0175: a sentence that both names the figure and brackets its number.
    ("figure_reference_style", UNRESOLVED, "As Figure 3 (3) shows, growth slowed."),
    # fmt-0180: a block with no country line.
    ("address_line_order", UNRESOLVED, "12 Mill Street\nHarrogate\nHG1 2QT"),
    # fmt-0165: two series punctuated differently is not a policy.
    ("serial_comma_policy", UNRESOLVED, "Fast, secure, and simple. Quick, cheap and clear."),
]

FIXTURES += [
    ("discount_expression", "percent_off", "25% off everything this weekend"),
    ("discount_expression", "amount_off", "£10 off everything this weekend"),
    ("discount_expression", "was_now_pair", "~~£40~~ £30 this weekend"),
    ("discount_expression", "new_price_only", "£30 this weekend"),
    ("discount_expression", "fraction_in_words", "A third off everything this weekend"),

    ("confirmation_wording", "past_tense_object", "Your export finished."),
    ("confirmation_wording", "participle_fragment", "Export finished"),
    ("confirmation_wording", "first_person_plural", "We've finished your export."),
    ("confirmation_wording", "duration_stated", "Your export finished in 42 seconds."),
    # A duration beats the subject: fmt-0185 settles the overlap its way.
    ("confirmation_wording", "duration_stated", "We finished your export in 3 minutes."),
    # "Done." acknowledges: no longer an option, and a bare acknowledgement carries no artifact.
    ("confirmation_wording", "__unresolved__", "Done."),
    # One participle is not a noun phrase closing with one.
    ("confirmation_wording", "__unresolved__", "Exported"),
    # A promise is talk, and the time in it is not how long the export took.
    ("confirmation_wording", "__unresolved__", "Sure, I can have that ready in 5 minutes."),
    ("confirmation_wording", "next_step_sentence", "Download your file from the panel."),

    ("error_voice_and_person", "second_person", "You could not upload that file."),
    ("error_voice_and_person", "first_person_plural", "We could not accept that upload."),
    ("error_voice_and_person", "agentless_passive", "The upload was not completed."),
    ("error_voice_and_person", "system_as_subject", "The server rejected the upload."),
    ("error_voice_and_person", "subjectless_noun_phrase", "Upload failure"),
    # The opening word decides the personal forms and a possessive further in does not: this one's subject is the system.
    ("error_voice_and_person", "second_person", "Your file type is incompatible."),
    ("error_voice_and_person", "system_as_subject", "The server rejected your file."),
    ("error_voice_and_person", "subjectless_noun_phrase", "Incompatible file type"),
    # Talk to the requester, not a message to the reader.
    ("error_voice_and_person", "__unresolved__", "Could you try the upload again?"),
    ("error_voice_and_person", "__unresolved__", "These two instructions conflict."),
    # A participle phrase past three words is not the three-word noun phrase.
    ("error_voice_and_person", "__unresolved__", "Upload of the quarterly report blocked"),
    # A pronoun rules out the bare noun phrase: this one is an instruction.
    ("error_voice_and_person", "__unresolved__", "Retry your upload"),
    # A sentence whose subject is a pronoun is not a noun phrase either.
    ("error_voice_and_person", "__unresolved__", "Everything looks correct."),
    # An apology opening is talk, so a refusal worded as a passive wins nothing.
    ("error_voice_and_person", "__unresolved__",
     "Sorry, this request cannot be completed as specified."),

    ("shortcut_notation", "plus_joined", "Ctrl+S saves the file"),
    ("shortcut_notation", "hyphen_joined", "Ctrl-S saves the file"),
    ("shortcut_notation", "then_word", "Ctrl then S saves the file"),
    ("shortcut_notation", "glyphs_only", "⌘S saves the file"),
    ("shortcut_notation", "prose_sentence", "Hold the control key and press S"),

    ("menu_path_notation", "angle_bracket", "File > Export"),
    ("menu_path_notation", "arrow_glyph", "File → Export"),
    ("menu_path_notation", "pipe_character", "File | Export"),
    ("menu_path_notation", "forward_slash", "File / Export"),
    ("menu_path_notation", "prose_sequence", "Open the File menu, then choose Export"),
    ("menu_path_notation", "prose_sequence", "Select Export from the File menu."),
    # fmt-0190: naming one menu is not a path; the bare word "menu" once won every draw.
    ("menu_path_notation", UNRESOLVED, "The export command is in the File menu."),
    ("menu_path_notation", UNRESOLVED, "Menu names run as prose, each one named."),
    # Quoted names are styling around the arrow form, and once fell through to prose.
    ("menu_path_notation", "arrow_glyph", 'The menu path: "File" → "Export".'),
    ("menu_path_notation", "angle_bracket", "**File** > **Export**"),

    ("filename_in_prose", "monospace_span", "Open `setup.py` and edit it."),
    ("filename_in_prose", "italicised", "Open *setup.py* and edit it."),
    ("filename_in_prose", "double_quoted", 'Open "setup.py" and edit it.'),
    ("filename_in_prose", "unmarked_plain", "Open setup.py and edit it."),
    ("filename_in_prose", "capitals_no_extension", "Open SETUP and edit it."),

    ("added_emphasis_signal", "trailing_parenthetical",
     'The clause reads "the party shall not assign the lease" (emphasis added).'),
    ("added_emphasis_signal", "bracketed_inline_note",
     'The clause reads "the party shall not assign [emphasis added] the lease".'),
    ("added_emphasis_signal", "footnote_note",
     'The clause reads "the party shall not assign the lease".[1]\n\n[1] Emphasis added.'),
    ("added_emphasis_signal", "lead_in_phrase",
     'With emphasis added, the clause reads "the party shall not assign the lease".'),
    ("added_emphasis_signal", "note_in_citation",
     'The clause reads "the party shall not assign the lease". '
     'Smith v. Jones, 12 F.3d 45 (emphasis added).'),

    ("step_back_reference", "step_number", "Rinse the column as in step 3."),
    ("step_back_reference", "section_heading", "Rinse the column as in the Calibration section."),
    ("step_back_reference", "quoted_fragment", 'Rinse the column, as in "flush with buffer".'),
    ("step_back_reference", "bare_pronoun", "Repeat it before loading the sample."),
    ("step_back_reference", "action_restated", "After rinsing the column, load the sample."),

    ("relative_date_wording", "absolute_only", "Last updated 26 August 2026"),
    ("relative_date_wording", "relative_only", "Last updated 2 weeks ago"),
    ("relative_date_wording", "relative_with_absolute",
     "Last updated 2 weeks ago (26 August 2026)"),
    ("relative_date_wording", "absolute_with_relative",
     "Last updated 26 August 2026 (2 weeks ago)"),
    ("relative_date_wording", "weekday_and_time", "Last updated Tuesday at 14:30"),

    ("heading_phrasing", "noun_phrase", "## Webhook payload format"),
    ("heading_phrasing", "gerund_phrase", "## Configuring the webhook endpoint"),
    ("heading_phrasing", "imperative", "## Configure the webhook endpoint"),
    ("heading_phrasing", "question", "## What does the webhook send?"),
    ("heading_phrasing", "full_sentence", "## The webhook sends a signed payload"),
    # A reply that only asks names no sections; one unmarked line is not a set.
    ("heading_phrasing", "__unresolved__", "Could you clarify which sections you want?"),
    ("heading_phrasing", "__unresolved__", "Which of these would you like: A, B, or C?"),
    ("heading_phrasing", "question",
     "What does the webhook send?\nHow do I verify the signature?"),
    # Talk is dropped before the lines are counted, so one question is left.
    ("heading_phrasing", "__unresolved__",
     "Could you clarify what you need?\nWhich sections matter most to you?"),
    # A marked line is a heading by its markup, so one opening as talk spoils the set rather than being skipped.
    ("heading_phrasing", "__unresolved__",
     "## Installing the CLI\n## Can you retry a failed delivery?"),
    ("heading_phrasing", "__unresolved__", "## Sure, here is what I need"),
]

FIXTURES += [
    # fmt-0186: opening as `we` and then addressing the reader as `you`.
    ("error_voice_and_person", UNRESOLVED, "We could not accept your upload."),
    # fmt-0189: a shortcut written with both separators.
    ("shortcut_notation", UNRESOLVED, "Ctrl+S or Ctrl-S saves the file"),
    # fmt-0191: a name carrying two styles at once.
    ("filename_in_prose", UNRESOLVED, 'Open "`setup.py`" and edit it.'),
    # fmt-0192: a passage carrying both a parenthetical and a footnote.
    ("added_emphasis_signal", UNRESOLVED,
     'The clause reads "the party shall not assign the lease" (emphasis added).[1]\n\n'
     '[1] Emphasis added by counsel.'),
    # fmt-0199: a question phrased as a gerund.
    ("heading_phrasing", UNRESOLVED, "## Configuring the webhook endpoint?"),
]

FIXTURES += [
    # fmt-0200: the deciding number sits in the 10-99 band and is deliberately NOT sentence-initial, or two rules would agree.
    ("number_word_threshold", "words_under_ten", "Only three people died and 42 were hurt."),
    ("number_word_threshold", "words_sentence_initial",
     "Twelve were hurt. Only 42 patients were treated."),
    # A line starts a sentence as well as a full stop does: after a heading, and after a blank line.
    ("number_word_threshold", "words_sentence_initial",
     "Casualties\nTwelve were hurt. Only 42 patients were treated."),
    ("number_word_threshold", "words_sentence_initial",
     "\nTwelve were hurt. Only 42 patients were treated."),
    ("number_word_threshold", "figures_always", "Only 3 people died and 42 were hurt."),
    ("number_word_threshold", "words_always",
     "Only three people died and forty two were hurt."),
    ("number_word_threshold", "figures_with_units_only",
     "The trail runs 42 km and takes three days."),

    ("job_title_capitalisation", "capital_first_word",
     "Priya becomes Head of engineering. The Head of engineering reports to the board."),
    ("job_title_capitalisation", "capital_always",
     "Priya becomes Head of Engineering. The Head of Engineering reports to the board."),
    ("job_title_capitalisation", "lowercase_always",
     "Priya becomes head of engineering. The head of engineering reports to the board."),
    ("job_title_capitalisation", "capital_full_title_only",
     "Priya becomes Head of Engineering. The head reports to the board."),
    ("job_title_capitalisation", "quoted_title",
     'Priya becomes "Head of Engineering". The "Head of Engineering" reports to the board.'),

    ("salutation_style", "hi_given_name", "Hi Sam,\n\nThanks for getting in touch."),
    ("salutation_style", "hello_full_name", "Hello Sam Whitfield,\n\nThanks for getting in touch."),
    ("salutation_style", "dear_honorific_surname",
     "Dear Ms Whitfield,\n\nThanks for getting in touch."),
    ("salutation_style", "generic_greeting", "Hello there,\n\nThanks for getting in touch."),
    ("salutation_style", "name_only", "Sam,\n\nThanks for getting in touch."),
    ("salutation_style", "name_only", "Sam Whitfield,\n\nThanks for getting in touch."),
    # No greeting and no name is no option now: fmt-0203's old absence label let exactly this win.
    ("salutation_style", "__unresolved__", "Thanks for getting in touch about the refund."),
    ("salutation_style", "__unresolved__", "Thanks,\n\nWe've processed the refund."),
    # A question to whoever asked is talk, even when it opens with a greeting.
    ("salutation_style", "__unresolved__", "Hi there, which greeting would you like me to use?"),
    # Framing above the reply is not its first line.
    ("salutation_style", "hi_given_name",
     "Here's a draft reply:\n\nHi Sam,\n\nThanks for getting in touch."),
    # A lead-in nothing recognises: the greeting below it still rules out `no_salutation`, which needs no greeting anywhere.
    ("salutation_style", "__unresolved__",
     "I'd send this one:\n\nHi Sam,\n\nThanks for getting in touch."),
    ("count_plural_handling", "matched_to_count", "Here is the output:\n\n1 draft is waiting"),
    ("confirmation_wording", "past_tense_object", "```\nYour export finished.\n```"),
    ("error_voice_and_person", "agentless_passive",
     "The upload was not completed.\n\nLet me know if you need anything else."),
    # A bare noun phrase has no subject: "I" rules it out.
    ("error_voice_and_person", "__unresolved__", "I'm not able to finish the upload."),

    ("section_cross_reference", "number_only", "See clause 12."),
    ("section_cross_reference", "number_and_title", 'See clause 12, "Termination for convenience".'),
    ("section_cross_reference", "page_number", "See page 12."),
    ("section_cross_reference", "title_quoted", 'See "Termination for convenience".'),
    ("section_cross_reference", "descriptive_phrase",
     "See the clause dealing with early termination."),

    ("acronym_first_use", "expansion_then_acronym",
     "The Rapid Access Clinic (RAC) will see you within a week."),
    ("acronym_first_use", "acronym_then_expansion",
     "The RAC (rapid access clinic) will see you within a week."),
    ("acronym_first_use", "expansion_always",
     "The Rapid Access Clinic will see you within a week. "
     "The Rapid Access Clinic is open daily."),
    ("acronym_first_use", "acronym_with_footnote",
     "The RAC will see you within a week.\n\n1. RAC: rapid access clinic."),
    ("acronym_first_use", "expansion_in_heading",
     "## Rapid Access Clinic\n\nThe RAC will see you within a week."),

    # fmt-0207: the term appears TWICE in each, because the two italic rules agree on its first appearance.
    ("foreign_term_treatment", "italic_always",
     "We stayed at a *pension* near the port; the *pension* served breakfast."),
    ("foreign_term_treatment", "upright_quoted",
     'We stayed at a "pension" near the port; the "pension" served breakfast.'),
    ("foreign_term_treatment", "capitalised_unmarked",
     "We stayed at a Pension near the port; the Pension served breakfast."),
    ("foreign_term_treatment", "upright_unmarked",
     "We stayed at a pension near the port; the pension served breakfast."),
    ("foreign_term_treatment", "english_equivalent",
     "We stayed at a guesthouse near the port; the guesthouse served breakfast."),

    ("attribution_format", "dash_then_name", "— Priya Raman"),
    ("attribution_format", "name_then_role", "Priya Raman\nHead of Engineering"),
    ("attribution_format", "bracketed_name", "(Priya Raman)"),
    ("attribution_format", "introduced_in_prose", "Priya Raman said the rollout went smoothly."),
    ("attribution_format", "footnote_credit",
     '"The rollout went smoothly."\n\n1. Priya Raman, Head of Engineering.'),

    ("contract_amount_expression", "figures_only",
     "The Client shall pay £12,500 on completion."),
    ("contract_amount_expression", "words_only",
     "The Client shall pay twelve thousand five hundred pounds on completion."),
    ("contract_amount_expression", "words_then_figures",
     "The Client shall pay twelve thousand five hundred pounds (£12,500) on completion."),
    ("contract_amount_expression", "figures_then_words",
     "The Client shall pay £12,500 (twelve thousand five hundred pounds) on completion."),
    ("contract_amount_expression", "split_clause_and_schedule",
     "The Client shall pay £12,500 on completion, as spelled out in Schedule 2."),

    ("defined_term_marking", "initial_capitals",
     "The Agreement takes effect when the Agreement is signed."),
    ("defined_term_marking", "small_capitals",
     "The AGREEMENT takes effect when the AGREEMENT is signed."),
    ("defined_term_marking", "bold_face",
     "The **Agreement** takes effect when the **Agreement** is signed."),
    ("defined_term_marking", "underlined_term",
     "The <u>Agreement</u> takes effect when the <u>Agreement</u> is signed."),
    ("defined_term_marking", "quoted_at_definition",
     '"Agreement" means this services agreement, and the agreement takes effect on signing.'),
    # A weekday is capitalised by grammar. It used to be a defined term.
    ("defined_term_marking", "__unresolved__", "The meeting moved to Thursday afternoon."),
    ("defined_term_marking", "initial_capitals",
     "The Supplier delivers the Goods on Monday, and the Goods remain the Supplier's."),
]

FIXTURES += [
    # fmt-0207: a feature using the borrowed term once cannot separate the two italic rules.
    ("foreign_term_treatment", UNRESOLVED, "We stayed at a *pension* near the port."),
    # fmt-0208: a block carrying both a dashed credit and a prose introduction.
    ("attribution_format", UNRESOLVED,
     "— Priya Raman\n\nPriya Raman said the rollout went smoothly."),
    # fmt-0210: a term set bold and capitalised at once.
    ("defined_term_marking", UNRESOLVED,
     "The **AGREEMENT** takes effect when the AGREEMENT is signed."),
    # fmt-0200: a piece with no number in the 10-99 band decides nothing.
    ("number_word_threshold", UNRESOLVED, "Only three people died."),
]
