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


def test_clean_output_keeps_only_final_text_of_heard_answer():
    assert clean_output("<heard>eh gua ai khi</heard>\n<text>Gua ai khi.</text>") == "Gua ai khi."
    assert clean_output("<heard></heard><text></text>") == ""                 # no speech
    assert clean_output("<heard>gua ai khi</heard>\nGua ai khi.") == "Gua ai khi."   # forgot <text>
    assert clean_output("<heard>gua ai khi") == "gua ai khi"                  # cut off: exact words beat nothing
    assert clean_output("<heard>a</heard><text>Halo") == "Halo"


def test_romanization_of_latin_text_is_dropped():
    assert clean_output("Lu tàng e lak bui.(Lú-tàng e lak-bué.)") == "Lu tàng e lak bui."
    assert clean_output("Gua ai khi. (Guá ài khì.) Lu le?") == "Gua ai khi. Lu le?"
    assert clean_output("我们明天开会。(Wǒmen míngtiān kāihuì.)") == "我们明天开会。(Wǒmen míngtiān kāihuì.)"
    assert clean_output("Rapat jam 5 (lihat lampiran).") == "Rapat jam 5 (lihat lampiran)."
    assert clean_output("Pakai API (Application Programming Interface).") == \
        "Pakai API (Application Programming Interface)."
