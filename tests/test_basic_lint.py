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


# --- W150 / W160: the two timing footguns ----------------------------------

def _rule(text, code):
    return [(i.line, i.severity, i.rule) for i in lint_source(text)
            if i.rule == code]


def test_wait_pair_on_the_raster_is_flagged():
    """`wait d,128 : wait d,128,128` reads as "wait for the raster msb, then
    wait for it to clear", and it does not give you a frame boundary: $D011
    bit 7 is set for seven lines (0.44 ms) and the second WAIT's own statement
    setup costs about 3 ms, so it overshoots and returns mid-frame. Measured
    2026-08-06 on NTSC: raster line 120-190, under 8 ms of budget left."""
    src = "10 wait 53265,128 : wait 53265,128,128\n20 end\n"
    assert _rule(src, "W150") == [(10, "warning", "W150")]
    # the message has to point somewhere, or the reader learns only that
    # something is wrong
    text = next(i.message for i in lint_source(src) if i.rule == "W150")
    # names the recipe by its heading — "pace a loop to the frame" is the
    # rem line inside its block, which is not what a reader searches for
    assert "single" in text
    assert "Pace a BASIC loop to the frame" in text


def test_wait_pair_through_a_named_register_is_flagged():
    """W160 resolved a WAIT's register through _literal_scalars while W150
    resolved it through _literal alone, so the two warnings disagreed about
    what a resolvable address is: the same `d=53265` that makes a SID loop
    count as frame-synced left the double-WAIT invisible. Holding the
    register in a variable is what the cookbook recipe itself does — a
    literal address costs about 4.7 ms per statement — so this is the
    spelling the rule most needs to see."""
    src = "5 d=53265\n10 wait d,128 : wait d,128,128\n20 end\n"
    assert _rule(src, "W150") == [(10, "warning", "W150")]


def test_a_wait_pair_on_an_unresolvable_register_is_not_flagged():
    """The resolver may not start guessing: a swept or twice-assigned name
    has no provable value, and W150 stays quiet rather than warn about a
    register it cannot name."""
    src = "5 d=53265\n6 d=53266\n10 wait d,128 : wait d,128,128\n20 end\n"
    assert _rule(src, "W150") == []


def test_wait_pair_is_flagged_across_two_lines():
    """Adjacency is in statement order, not within a line: splitting the pair
    over two lines changes nothing about why it fails."""
    src = "10 wait 53266,128\n20 wait 53266,128,128\n30 end\n"
    assert _rule(src, "W150") == [(20, "warning", "W150")]


def test_a_single_wait_on_the_raster_is_not_flagged():
    """The fix the rule points at must not itself be flagged."""
    src = "10 for k=1 to 300 : wait 53265,128 : next k\n20 end\n"
    assert _rule(src, "W150") == []


def test_a_wait_pair_on_a_non_raster_address_is_not_flagged():
    """$DC01 is the keyboard port; waiting twice on it is an ordinary idiom
    and has nothing to do with the raster's seven-line window."""
    src = "10 wait 56321,16 : wait 56321,16,16\n20 end\n"
    assert _rule(src, "W150") == []


def test_two_waits_on_different_raster_registers_are_not_flagged():
    """The rule is about polling ONE window twice, so the addresses have to
    match. $D011 then $D012 is two different reads."""
    src = "10 wait 53265,128 : wait 53266,128,128\n20 end\n"
    assert _rule(src, "W150") == []


TI_DELAY = "10 t=ti\n20 if ti-t<480 goto 20\n"


def test_ti_paced_sid_loop_is_flagged():
    """TI runs at exactly 60.00 Hz and an NTSC frame at 59.826, and the sid
    log counts FRAMES — so a sequencer paced on TI drifts about one frame
    every 340. Measured on the 05-bach-invention run: 2190 jiffies over 2184
    frames."""
    src = TI_DELAY + "30 for i=0 to 100 : poke 54273,i : next i\n40 end\n"
    assert _rule(src, "W160") == [(30, "warning", "W160")]
    text = next(i.message for i in lint_source(src) if i.rule == "W160")
    assert "59.826" in text and "60.00" in text


def test_ti_paced_sid_loop_through_a_named_address_is_flagged():
    """Step 3c's case, and the reason the resolver earns its place: a poke's
    address resolves only when it is written as a literal, but a well-written
    player holds its SID addresses in variables because a literal address
    costs +4.7 ms. Without _literal_scalars this rule would go quiet exactly
    as authors improve."""
    src = (TI_DELAY + "25 f1=54272\n"
           "30 for i=0 to 100 : poke f1,i : next i\n40 end\n")
    assert _rule(src, "W160") == [(30, "warning", "W160")]


def test_a_sid_loop_with_no_ti_delay_is_not_flagged():
    """The TI delay is what says the program is pacing itself on the jiffy
    clock. Without one there is nothing to warn about."""
    src = "30 for i=0 to 100 : poke 54273,i : next i\n40 end\n"
    assert _rule(src, "W160") == []


def test_a_ti_delay_outside_a_loop_is_not_flagged():
    """A gosub'd beep — the cookbook's own — legitimately paces on TI: it is
    one-shot, so there is no drift to accumulate. The `for` qualifier is what
    keeps it out."""
    src = ("10 gosub 900\n20 end\n"
           "900 poke 54296,15 : poke 54273,17 : poke 54276,17\n"
           "910 t=ti\n920 if ti-t<30 goto 920\n"
           "930 poke 54276,16 : return\n")
    assert _rule(src, "W160") == []


def test_the_sid_clear_idiom_is_not_flagged():
    """`for m=54272 to 54296 : poke m,0 : next m` sweeps the whole register
    file, and its address is a `for` control variable — which no resolver may
    treat as a constant. This is the false positive the fourth condition of
    _literal_scalars exists to prevent."""
    src = TI_DELAY + "30 for m=54272 to 54296 : poke m,0 : next m\n40 end\n"
    assert _rule(src, "W160") == []


def test_a_reassigned_address_does_not_resolve():
    """Two assignments and the value is a guess, so the name is simply absent
    from the map — conditions 1 and 2 of _literal_scalars."""
    src = (TI_DELAY + "25 f1=54272\n26 f1=54279\n"
           "30 for i=0 to 100 : poke f1,i : next i\n40 end\n")
    assert _rule(src, "W160") == []


def test_an_address_assigned_inside_a_loop_does_not_resolve():
    """Condition 3: a swept address is not a constant, whatever its RHS."""
    src = (TI_DELAY + "30 for i=0 to 100 : f1=54272 : poke f1,i : next i\n"
           "40 end\n")
    assert _rule(src, "W160") == []


def test_a_computed_address_does_not_resolve():
    """Condition 2: `c1=b+4` is not a bare numeric literal."""
    src = (TI_DELAY + "24 b=54272\n25 c1=b+4\n"
           "30 for i=0 to 100 : poke c1,i : next i\n40 end\n")
    assert _rule(src, "W160") == []


def test_a_named_address_reaches_the_range_check():
    """Step 3b: _check_ranges only ever saw literal arguments, so an
    out-of-range poke through a named ADDRESS was invisible. (The value
    argument was always visible — `poke sc,300` fires with or without the
    resolver, which is why the address is what this pins.)"""
    assert _rule("10 sc=70000\n20 poke sc,32\n30 end\n", "E150") == \
        [(20, "error", "E150")]


def test_a_variable_rebound_without_an_equals_does_not_resolve():
    """INPUT, READ and GET rebind a name with no `=` in sight, so the single
    literal assignment the resolver saw is not the value the program holds —
    and a READ-driven table is the idiom the resolver exists for. A hard
    E150 on a value the program never necessarily holds fails the lint of a
    correct program."""
    for rebind in ("20 input n", "20 read n", "20 get n",
                   "20 input#1,n", "20 print: input \"how many\";n"):
        src = f"10 n=1000\n{rebind}\n30 poke 1024,n\n40 end\n"
        assert _rule(src, "E150") == [], src


def test_reading_an_array_element_also_drops_the_same_named_scalar():
    """`read a(1)` fills the ARRAY a, which V2 keeps in a namespace of its
    own, so the scalar `a` is untouched and could in principle still resolve.
    The resolver drops it anyway rather than reason about subscripts — it
    under-reports by design, and silence on `a` costs nothing while a wrong
    E150 costs a correct program its exit code. Pinned so the choice is a
    decision and not an accident."""
    src = ("10 a=70000\n20 dim a(3)\n30 read a(1)\n40 poke a,0\n"
           "50 data 1\n60 end\n")
    assert _rule(src, "E150") == []
    # …and DIM alone, which binds nothing, does not drop it.
    assert _rule("10 a=70000\n20 dim a(3)\n30 poke a,0\n40 end\n",
                 "E150") == [(30, "error", "E150")]


def test_the_range_check_still_ignores_an_unresolvable_address():
    """It must not start guessing. A swept name has no constant value, and a
    name assigned twice has no provable one — a false ?illegal quantity on a
    correct program is worse than silence."""
    assert _rule("10 for m=1024 to 2023 : poke m,32 : next m\n20 end\n",
                 "E150") == []
    assert _rule("10 sc=53281\n20 sc=70000\n30 poke sc,32\n40 end\n",
                 "E150") == []


def test_a_raster_synced_sid_loop_is_not_flagged():
    """The narrowing the corpus forced, and the case W160 exists to spare:
    `demos/05-bach-invention/bach-invention.bas` holds its SID addresses in
    variables AND opens with an `if ti` delay — but its play loop syncs on
    $D011 every slice, and its TI delay is a one-shot lead-in before the music
    starts. A loop holding a raster WAIT is paced by the frame whatever else
    the program does."""
    src = (TI_DELAY + "25 d=53265 : mk=128 : c1=54276\n"
           "30 for i=0 to 100 : wait d,mk : poke c1,i : next i\n40 end\n")
    assert _rule(src, "W160") == []


def test_an_outer_raster_sync_covers_an_inner_loop():
    """The sync need not be in the same loop as the poke: an inner loop inside
    a frame-synced outer one is still frame-paced."""
    src = (TI_DELAY + "25 d=53265 : mk=128 : c1=54276\n"
           "30 for i=0 to 9 : wait d,mk\n"
           "35 for j=0 to 2 : poke c1,j : next j\n"
           "36 next i\n40 end\n")
    assert _rule(src, "W160") == []
