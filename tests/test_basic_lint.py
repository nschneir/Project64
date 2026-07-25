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


def test_fused_to_at_statement_start_is_an_error():
    assert rules("10 total=5\n") == [(10, "error", "E110")]


def test_fused_to_in_a_variable_list_is_an_error():
    assert rules("10 input total\n") == [(10, "error", "E111")]


def test_fused_to_in_an_expression_is_an_error():
    assert rules("10 print total\n") == [(10, "error", "E110")]


def test_fused_or_in_an_assignment_target_is_an_error():
    assert rules("10 score=score+1\n") == [(10, "error", "E111")]


def test_statement_starting_with_a_variable_needs_an_equals():
    # `paint 1,2` tokenizes as PA INT 1,2 — a guaranteed syntax error.
    assert rules("10 paint 1,2\n") == [(10, "error", "E111")]


def test_crunched_for_loop_is_not_flagged():
    assert lint_source("10 fori=1to10:printi:next\n20 end\n") == []


def test_spaced_misplacement_is_only_a_warning():
    # Reachable on purpose — an `end` on line 10 would add W70 noise.
    assert rules("10 goto 20\n20 to 30\n30 end\n") == [(20, "warning", "W110")]


def test_fusion_message_shows_the_split():
    msg = lint_source("10 total=5\n")[0].message
    assert "TO TAL" in msg and "total" in msg


def test_if_without_then_or_goto_is_an_error():
    assert rules('10 if a=1 print "hi"\n') == [(10, "error", "E120")]


def test_if_goto_is_legal():
    assert lint_source("10 if a goto 20\n20 end\n") == []


def test_then_with_nothing_after_it():
    assert rules("10 if a=1 then\n") == [(10, "error", "E122")]


def test_unbalanced_parens():
    assert rules("10 print(1+2\n") == [(10, "error", "E121")]
    assert rules("10 a=peek(53280))\n") == [(10, "error", "E121")]


def test_parens_inside_strings_do_not_count():
    assert lint_source('10 print "(:"\n') == []


def test_tab_counts_as_an_open_paren():
    assert lint_source("10 print tab(5)\n") == []


def test_unterminated_string_is_a_warning():
    assert rules('10 print "oops\n') == [(10, "warning", "W40")]


def test_data_items_are_immune_to_fusion_checks():
    assert lint_source('10 data total,score,"a:b"\n20 end\n') == []


def test_rem_text_is_immune():
    assert lint_source("10 rem total score\n20 end\n") == []
