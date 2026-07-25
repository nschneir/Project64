from c64lib.basic_lint import lint_source, tokenized_bytes


def rules(text):
    return [(i.line, i.severity, i.rule) for i in lint_source(text)]


def test_clean_program_has_no_issues():
    assert lint_source('10 print "hi"\n20 goto 10\n') == []


def test_missing_line_number_is_an_error():
    assert rules('print "hi"\n') == [(None, "error", "E10")]


def test_line_number_out_of_range():
    assert rules("64000 end\n") == [(64000, "error", "E11")]


def test_duplicate_line_number():
    assert ("error", "E12") in [(s, r) for _, s, r in rules("10 end\n10 end\n")]


def test_out_of_order_is_a_warning():
    assert (5, "warning", "W20") in rules("10 end\n5 end\n")


def test_blank_lines_are_skipped():
    assert lint_source("\n\n10 end\n\n") == []


def test_long_logical_line_warns_at_81_chars():
    ok = "10 rem " + "a" * 73                 # exactly 80 counted characters
    assert len(ok) == 80
    assert lint_source(ok + "\n") == []
    assert rules(ok + "a\n") == [(10, "warning", "W30")]


def test_escapes_count_as_one_character_for_w30():
    line = "10 rem " + "{clr}" * 20           # 7 + 20 = 27 counted characters
    assert lint_source(line + "\n") == []


def test_tokenized_bytes_is_exact():
    # 10 print"a"  -> 4 text bytes; 20 end -> 1 text byte.
    assert tokenized_bytes('10 print"a"\n20 end\n') == (4 + 5) + (1 + 5) + 2


def test_oversized_program_errors():
    src = "".join(f'{n} print"{"x" * 60}"\n' for n in range(10, 10 + 700))
    assert any(r == "E160" for _, _, r in rules(src))


def test_message_text_names_the_rule_subject():
    issues = lint_source("64000 end\n")
    assert issues[0].message == "line number 64000 out of range (0-63999)"
