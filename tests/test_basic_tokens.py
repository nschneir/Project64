import shutil
import subprocess

import pytest

from c64lib.basic_tokens import (
    merge_tokens,
    petscii_len,
    program_bytes,
    text_bytes,
    tokenize_line,
)


def kinds(text):
    return [(t.kind, t.text) for t in tokenize_line(text)]


def test_fusion_splits_identifiers_like_the_rom():
    # Measured against petcat: `total=5` stores as TO TAL = 5.
    assert kinds("total=5") == [
        ("KEYWORD", "to"), ("IDENT", "tal"), ("OP", "="), ("NUMBER", "5")]


def test_fusion_finds_or_inside_score():
    assert kinds("score=1")[:3] == [
        ("IDENT", "sc"), ("KEYWORD", "or"), ("IDENT", "e")]


def test_plain_identifier_is_not_split():
    assert kinds("count=1") == [
        ("IDENT", "count"), ("OP", "="), ("NUMBER", "1")]


def test_crunched_for_loop_tokenizes_normally():
    assert kinds("fori=1to10:printi:next") == [
        ("KEYWORD", "for"), ("IDENT", "i"), ("OP", "="), ("NUMBER", "1"),
        ("KEYWORD", "to"), ("NUMBER", "10"), ("OP", ":"),
        ("KEYWORD", "print"), ("IDENT", "i"), ("OP", ":"), ("KEYWORD", "next")]


def test_longest_keyword_wins_over_prefix():
    assert kinds("gosub100")[0] == ("KEYWORD", "gosub")     # not GO + SUB
    assert kinds("print#1")[0] == ("KEYWORD", "print#")     # not PRINT + #


def test_rem_makes_the_rest_opaque():
    assert kinds('rem total: print "x"') == [
        ("KEYWORD", "rem"), ("REM", ' total: print "x"')]


def test_data_items_are_opaque_until_an_unquoted_colon():
    assert kinds('data total,"a:b",1e4:print"x"') == [
        ("KEYWORD", "data"), ("DATA", ' total,"a:b",1e4'), ("OP", ":"),
        ("KEYWORD", "print"), ("STRING", '"x"')]


def test_string_swallows_keywords_and_escapes():
    toks = tokenize_line('print "{clr}total"')
    assert [t.kind for t in toks] == ["KEYWORD", "STRING"]
    assert toks[1].size == 1 + len("total") + 2       # {clr} is one PETSCII char


def test_unterminated_string_is_tokenized_to_end_of_line():
    toks = tokenize_line('print "oops')
    assert toks[1].kind == "STRING" and toks[1].text == '"oops'


def test_numbers_absorb_exponents_and_leading_dot():
    assert kinds("a=1e4") == [
        ("IDENT", "a"), ("OP", "="), ("NUMBER", "1e4")]
    assert kinds("a=.5")[2] == ("NUMBER", ".5")


def test_question_mark_is_print():
    assert kinds('?"hi"')[0] == ("KEYWORD", "print")


def test_escape_outside_a_string_is_its_own_token():
    toks = tokenize_line("a={pi}")
    assert toks[2].kind == "ESCAPE" and toks[2].size == 1


def test_fused_flag_marks_glued_keywords_only():
    assert tokenize_line("total=5")[0].fused is True
    assert tokenize_line("10 to 20")[0].fused is False


def test_merge_is_analysis_only():
    merged = merge_tokens(tokenize_line("go to 100"))
    assert [(t.kind, t.text) for t in merged][0] == ("KEYWORD", "goto")
    merged = merge_tokens(tokenize_line("if a<=2 then 10"))
    assert ("OP", "<=") in [(t.kind, t.text) for t in merged]


def test_case_insensitive():
    assert kinds('PRINT "HI"')[0] == ("KEYWORD", "print")


def test_petscii_len_counts_escapes_as_one():
    assert petscii_len("{clr}ab{$a0}") == 4


def test_text_bytes_drops_the_leading_separator_space():
    # Measured: `10   print"a"` stores 4 text bytes.
    text = '   print"a"'
    assert text_bytes(text, tokenize_line(text)) == 4


def test_text_bytes_keeps_inner_spaces():
    text = " for i=1 to 10"
    assert text_bytes(text, tokenize_line(text)) == 10


def test_program_bytes_adds_line_overhead_and_terminator():
    # 3 lines of 4, 10 and 1 text bytes -> 5 overhead each, +2 trailing zeros.
    assert program_bytes([4, 10, 1]) == (4 + 5) + (10 + 5) + (1 + 5) + 2


@pytest.mark.skipif(shutil.which("petcat") is None, reason="petcat not installed")
def test_byte_model_matches_petcat_exactly(tmp_path):
    """The size model is only useful if it is exact — check it against the
    real tokenizer over every construct the lint has to survive."""
    src = tmp_path / "p.bas"
    src.write_text(
        '10   print"a"\n'
        '20 rem hi {clr} there\n'
        '30 data total,"a:b",1e4:print"x"\n'
        '40 go to 10\n'
        '50 ?"{clr}{$a0}"\n'
        '60 print"oops\n'
        '70 a=1<=2\n'
        '80 fori=1to10:printi:next\n'
    )
    prg = tmp_path / "p.prg"
    subprocess.run(["petcat", "-w2", "-o", str(prg), "--", str(src)], check=True)
    sizes = []
    for line in src.read_text().splitlines():
        rest = line[len(line) - len(line.lstrip("0123456789 ")):]
        sizes.append(text_bytes(rest, tokenize_line(rest)))
    assert program_bytes(sizes) == len(prg.read_bytes()) - 2   # minus load address
