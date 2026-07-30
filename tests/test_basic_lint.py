from c64lib.basic_lint import lint_source, tokenized_bytes


def rules(text):
    return [(i.line, i.severity, i.rule) for i in lint_source(text)]


def test_clean_program_has_no_issues():
    assert lint_source('10 print "hi"\n20 goto 10\n') == []


def test_missing_line_number_is_a_warning():
    # Verified on x64sc: petcat invents a number rather than failing.
    assert rules('print "hi"\n') == [(None, "warning", "E10")]


def test_unnumbered_line_among_numbered_ones_does_not_crash_the_graph():
    # An unnumbered line must not reach _check_reach or _check_subroutines,
    # which compare and index by line number. It is dropped at parse time
    # (E10) and never enters prog.lines, so the graph stays all-int.
    src = ('10 gosub 100\n'
           'print "no number"\n'
           '20 goto 10\n'
           '100 return\n')
    assert rules(src) == [(None, "warning", "E10")]


def test_line_number_above_the_editor_limit_is_a_warning():
    # Verified on x64sc: `64000 end` loads and runs; only the editor refuses it.
    assert rules("64000 end\n") == [(64000, "warning", "E11")]


def test_line_number_that_does_not_fit_the_word_is_an_error():
    # Verified: petcat wrapped `70000 print "hi"` to line 4464.
    assert rules('70000 print "hi"\n') == [(70000, "error", "E11")]


def test_duplicate_line_number():
    # Verified on x64sc: both copies run in order; goto reaches only the first.
    assert ("warning", "E12") in [(s, r) for _, s, r in rules("10 end\n10 end\n")]


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
    issues = lint_source('70000 print "hi"\n')
    assert issues[0].message == "line number 70000 exceeds 65535 and wraps to 4464"


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
    # Warning, not error: verified on x64sc — a taken `IF ... THEN` with
    # nothing after it falls through to the next line without faulting.
    assert rules("10 if a=1 then\n") == [(10, "warning", "E122")]


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


def test_goto_to_a_missing_line():
    assert rules("10 goto 999\n") == [(10, "error", "E20")]


def test_then_number_is_a_jump_target():
    assert rules("10 ifathen999\n") == [(10, "error", "E20")]


def test_on_goto_checks_every_target():
    # Line 20 returns, so the ON list entry is a well-formed subroutine.
    src = "10 on a gosub 20,999\n20 return\n"
    assert rules(src) == [(10, "error", "E20")]


def test_goto_without_a_target():
    assert rules("10 goto\n") == [(10, "error", "E21")]


def test_on_without_goto_or_gosub():
    assert rules("10 on a print 5\n") == [(10, "error", "E22")]


def test_negative_constant_selector():
    assert rules("10 on -1 goto 20\n20 end\n") == [(10, "error", "E23")]


def test_selector_beyond_the_target_list():
    assert rules("10 on 4 goto 20,30\n20 end\n30 end\n") == [(10, "warning", "W50")]


def test_next_without_for():
    assert rules("10 next\n") == [(10, "error", "E130")]


def test_for_without_next():
    assert rules("10 fori=1to10\n20 end\n") == [(10, "warning", "W131")]


def test_next_variable_mismatch():
    src = "10 fori=1to2\n20 forj=1to2\n30 nexti\n40 nextj\n"
    assert (30, "warning", "W130") in rules(src)


def test_return_with_no_gosub():
    assert (10, "warning", "W140") in rules("10 return\n")


def test_gosub_target_with_no_return():
    src = '10 gosub 100\n20 end\n100 print "x"\n110 end\n'
    assert (100, "warning", "W141") in rules(src)


def test_unreachable_line():
    assert rules('10 goto 30\n20 print "dead"\n30 end\n') == [(20, "warning", "W70")]


def test_gosub_falls_through():
    assert lint_source('10 gosub 100\n20 print "back"\n30 end\n'
                       '100 x=1:return\n') == []


def test_trailing_if_never_terminates_the_line():
    # `130 if k$="q" then end` must not make the next line unreachable.
    assert lint_source('10 get k$\n20 if k$="q" then end\n30 goto 10\n') == []


def test_data_after_end_is_not_unreachable():
    assert lint_source('10 read a:print a\n20 end\n30 data 1,2,3\n') == []


def test_poke_value_out_of_range():
    assert rules("10 poke 53280,300\n") == [(10, "error", "E150")]


def test_poke_address_out_of_range():
    assert rules("10 poke 70000,0\n") == [(10, "error", "E150")]


def test_chr_and_sys_ranges():
    assert rules("10 print chr$(300)\n") == [(10, "error", "E150")]
    assert rules("10 sys 70000\n") == [(10, "error", "E150")]


def test_range_boundaries_are_legal():
    assert lint_source("10 poke 65535,255:poke 0,0\n20 print chr$(0)chr$(255)\n"
                       "30 print tab(255)spc(0)\n40 end\n") == []


def test_expressions_are_not_range_checked():
    assert lint_source("10 poke 53280,c\n20 poke 1024+40*5,42\n30 end\n") == []


def test_float_literal_overflow():
    assert rules("10 a=1e39\n") == [(10, "error", "E151")]


def test_assignment_to_reserved_variables():
    assert rules("10 ti=0\n") == [(10, "error", "E152")]
    assert rules("10 st=1\n") == [(10, "error", "E152")]


def test_ti_string_assignment_is_legal():
    assert lint_source('10 ti$="000000"\n20 t=ti:s=st\n30 end\n') == []


def test_for_variable_must_be_plain_numeric():
    assert rules("10 for a$=1 to 5:next\n") == [(10, "error", "E153")]
    assert rules("10 for i%=1 to 5:next\n") == [(10, "error", "E153")]


def test_simple_operand_type_mismatch():
    assert rules("10 a$=5\n") == [(10, "error", "E154")]
    assert rules('10 b="x"\n') == [(10, "error", "E154")]
    assert rules("10 if n$<3 then 20\n20 end\n") == [(10, "error", "E154")]


def test_compound_expressions_are_never_type_checked():
    assert lint_source('10 s=142\n20 s$=str$(s)\n30 print s$\n40 end\n') == []


def test_fn_used_without_def():
    assert rules("10 print fn f(2)\n") == [(10, "error", "E140")]


def test_def_fn_satisfies_the_use():
    assert lint_source("10 def fn sq(x)=x*x\n20 print fn sq(9)\n30 end\n") == []


def test_read_with_no_data():
    assert (10, "warning", "W80") in rules("10 read a:print a\n")


def test_array_dimensioned_twice():
    assert (20, "warning", "W81") in rules("10 dim a(5)\n20 dim a(9)\n30 end\n")


def test_subscript_beyond_the_default_bound():
    assert (10, "warning", "W82") in rules("10 a(15)=1\n20 end\n")


def test_dimensioned_array_allows_big_subscripts():
    assert lint_source("10 dim a(20)\n20 a(15)=1\n30 end\n") == []


# E131 — the demo-05 shape. Everything below it pins the rule's narrowness:
# each negative case must stay silent rather than guess.
_E131 = ("10 dim v(4)\n20 for i=1 to 5: read v(i): next\n"
         "30 data 12,9,17,4,11\n40 end\n")


def e131(text):
    return [i for i in lint_source(text) if i.rule == "E131"]


def test_literal_dim_and_for_bound_overflow_is_an_error():
    assert (20, "error", "E131") in rules(_E131)


def test_bad_subscript_message_names_the_use_and_the_dim():
    assert e131(_E131)[0].message == (
        "?bad subscript: v(5) at line 20 exceeds dim v(4) (line 10)")


def test_bad_subscript_spans_lines_between_for_and_next():
    src = ("10 dim v(4)\n20 for i=1 to 5\n30 read v(i)\n40 next\n"
           "50 data 12,9,17,4,11\n60 end\n")
    assert (30, "error", "E131") in rules(src)


def test_bad_subscript_ignores_a_computed_dim_bound():
    assert e131("10 n=4\n20 dim v(n)\n30 for i=1 to 5: v(i)=0: next\n"
                "40 end\n") == []


def test_bad_subscript_ignores_a_computed_for_bound():
    assert e131("10 dim v(4)\n20 n=5\n30 for i=1 to n: v(i)=0: next\n"
                "40 end\n") == []


def test_bad_subscript_ignores_a_computed_subscript():
    assert e131("10 dim v(4)\n20 for i=1 to 5: v(i+1)=0: next\n40 end\n") == []


def test_bad_subscript_ignores_a_different_subscript_variable():
    assert e131("10 dim v(4)\n20 j=0\n30 for i=1 to 5: v(j)=0: next\n"
                "40 end\n") == []


def test_bad_subscript_counts_dim_as_zero_based():
    # dim v(4) allocates v(0)..v(4), so `to 4` fits exactly.
    assert lint_source("10 dim v(4)\n20 for i=1 to 4: v(i)=0: next\n"
                       "30 end\n") == []


def test_bad_subscript_skips_loops_with_a_step():
    assert e131("10 dim v(4)\n20 for i=1 to 5 step 2: v(i)=0: next\n"
                "30 end\n") == []


def test_bad_subscript_skips_a_redimensioned_array():
    assert e131("10 dim v(4)\n20 dim v(3)\n30 for i=1 to 5: v(i)=0: next\n"
                "40 end\n") == []


def test_bad_subscript_ignores_uses_outside_the_loop():
    assert e131("10 dim v(4)\n20 for i=1 to 5: next\n30 v(i)=0\n"
                "40 end\n") == []


def test_new_list_cont_inside_a_program():
    got = rules('10 print "hi":new\n20 list\n30 cont\n')
    assert got == [(10, "warning", "W90"), (20, "warning", "W90"),
                   (30, "warning", "W90")]


def test_later_basic_keywords_warn():
    assert (20, "warning", "W60") in rules("10 end\n20 sound 1,100\n")


def test_two_character_aliasing_warns():
    assert any(r == "W61" for _, _, r in rules("10 speed=1\n20 spent=2\n30 end\n"))


def test_aliasing_respects_separate_namespaces():
    assert lint_source('10 spa=1\n20 spa$="x"\n30 end\n') == []
