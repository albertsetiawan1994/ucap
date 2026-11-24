from ucap.snippets import clean_output, expand_snippets

SNIPS = [
    {"trigger": "tanda tangan email", "expansion": "Salam,\nRina\n0812-0000-0000"},
    {"trigger": "link kalender", "expansion": "https://cal.example.com/rina"},
    {"trigger": "link", "expansion": "SHOULD-NOT-WIN"},
]


def test_whole_utterance_ignores_case_and_punctuation():
    assert expand_snippets("Tanda tangan email.", SNIPS) == SNIPS[0]["expansion"]
    assert expand_snippets("  TANDA, tangan email!", SNIPS) == SNIPS[0]["expansion"]


def test_inline_replacement_keeps_surrounding_text():
    out = expand_snippets("Silakan pilih jadwal di Link Kalender, terima kasih.", SNIPS)
    assert out == "Silakan pilih jadwal di https://cal.example.com/rina, terima kasih."


def test_longest_trigger_wins_and_partial_words_do_not_match():
    assert "SHOULD-NOT-WIN" not in expand_snippets("buka link kalender", SNIPS)
    assert expand_snippets("linked list", SNIPS) == "linked list"


def test_no_snippets_or_empty_text():
    assert expand_snippets("halo", []) == "halo"
    assert expand_snippets("", SNIPS) == ""
    assert expand_snippets("halo", [{"trigger": "", "expansion": "x"}]) == "halo"


def test_expansion_not_reexpanded():
    snips = [{"trigger": "a b", "expansion": "a b a b"}]
    assert expand_snippets("x a b y", snips) == "x a b a b y"


def test_clean_output_strips_wrappers():
    assert clean_output("```\nHalo semua\n```") == "Halo semua"
    assert clean_output('"Halo semua"') == "Halo semua"
    assert clean_output("Transkrip: Halo") == "Halo"
    assert clean_output('Dia bilang "ya" lalu "tidak"') == 'Dia bilang "ya" lalu "tidak"'
    assert clean_output(None) == ""
