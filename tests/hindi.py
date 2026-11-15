#!/usr/bin/env python3
"""Hindi and mixed Hindi-English regression tests.

Same harness as regress.py: every script runs as a subprocess through the
.claude/skills symlinks, from this folder, with no bytecode written. The
fixtures in hi/ are fictional. English behaviour is covered by regress.py,
validate.py and golden.py; the tests here also check that English output
gains no new fields.

  python3 hindi.py            # all tests
  python3 hindi.py L1 L8      # only ids starting with L1 or L8
"""
import importlib.util, json, os, re, shutil, subprocess, sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from regress import ENV, HERE, SK, caption, chk, detect, humanize, run  # noqa: E402

TESTS = []
HI = os.path.join(HERE, "hi")
SCRIPTS = ["ig-reel/hookscore.py", "ig-reel/beats.py", "ig-human/detect.py",
           "ig-human/humanize.py", "ig-caption/caption.py", "ig-viral/swipe.py"]
BEGIN, END = "# --- Devanagari support ---", "# --- end of Devanagari support ---"


def test(tid, desc):
    def deco(fn):
        TESTS.append((tid, desc, fn))
        return fn
    return deco


def fixture(name):
    return open(os.path.join(HI, name), encoding="utf-8").read()


def hook(text):
    _, out, _ = run("ig-reel/hookscore.py", "--hook", text, "--json")
    return json.loads(out)


def beats(text, *extra):
    _, out, _ = run("ig-reel/beats.py", "-", "--json", *extra, stdin=text)
    return json.loads(out)


def module(script):
    spec = importlib.util.spec_from_file_location(os.path.basename(script)[:-3] + "_t",
                                                  os.path.join(SK, script))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def block(script):
    src = open(os.path.join(SK, script), encoding="utf-8").read()
    return src[src.index(BEGIN):src.index(END)]


# ======================================================================
# Shared tokenizer
# ======================================================================
@test("L1", "the Devanagari block is identical in all six scripts")
def _():
    first = block(SCRIPTS[0])
    for s in SCRIPTS[1:]:
        assert block(s) == first, f"{s} differs from {SCRIPTS[0]}"


@test("L2", "a Hindi word is one word: the mixed test line counts 7, not 3")
def _():
    d = hook("Plot का token देने से पहले रुकिए।")
    assert d["checks"]["LENGTH"]["detail"].startswith("7 words"), d["checks"]["LENGTH"]
    m = module("ig-human/detect.py")
    assert m.words("रुकिए पहले") == ["रुकिए", "पहले"]          # \w alone splits रुकिए into र, क, ए


@test("L3", "language detection: en, hi and mixed; links, hashtags and handles not counted")
def _():
    m = module("ig-reel/hookscore.py")
    cases = {"Proposals used to take me five hours.": "en",
             "मेरी पहली दुकान का किराया बारह हज़ार था।": "hi",
             "Plot का token देने से पहले रुकिए।": "mixed",
             "घर खरीदने से पहले ये पढ़िए #homebuying #realestate @someone https://example.com/x": "hi",
             "aap kaise ho": "en"}                         # Hindi in Latin letters: a known limit
    for text, want in cases.items():
        assert m.lang_of(text) == want, (text, m.lang_of(text))


@test("L4", "nukta and candrabindu spellings compare equal (ज़रूरी = जरूरी, पाँच = पांच)")
def _():
    m = module("ig-reel/hookscore.py")
    assert m.deva_fold("ज़रूरी") == m.deva_fold("जरूरी")
    assert m.deva_fold("पाँच") == m.deva_fold("पांच")
    assert m.deva_fold("plain English, café") == "plain English, café"   # untouched
    a = hook("मैंने पाँच लाख रुपये गँवाए।")["checks"]["SPECIFICITY"]["score"]
    b = hook("मैंने पांच लाख रुपये गंवाए।")["checks"]["SPECIFICITY"]["score"]
    assert a == b > 15, (a, b)


@test("L5", "English output gains no new fields: no lang or calibration key in any tool")
def _():
    en = "Proposals used to take me five hours. Now it is twenty minutes. Comment TEMPLATE."
    assert "lang" not in hook(en) and "calibration" not in hook(en)
    assert "lang" not in detect(en) and "lang" not in caption(en) and "lang" not in beats(en)
    _, out, _ = run("ig-viral/swipe.py", "captured.tsv", "--json")
    assert not any("lang" in r for r in json.loads(out)["reels"])


# ======================================================================
# hookscore.py
# ======================================================================
@test("L6", "hookscore: Hindi stakes, numbers and an end-of-line imperative are scored")
def _():
    d = hook("Plot का token देने से पहले रुकिए।")
    assert d["checks"]["STAKES"]["score"] == 100.0, d["checks"]["STAKES"]
    assert d["checks"]["ADDRESS"]["score"] == 90.0, d["checks"]["ADDRESS"]   # verb comes last in Hindi
    d = hook("आपकी सैलरी से हर महीने पाँच हज़ार रुपये कहाँ जाते हैं?")
    assert d["checks"]["ADDRESS"]["detail"] == "speaks to the viewer", d["checks"]["ADDRESS"]
    assert d["checks"]["SPECIFICITY"]["score"] >= 75, d["checks"]["SPECIFICITY"]
    assert hook("घर के लिए लोन लिया")["checks"]["ADDRESS"]["score"] != 90.0   # लिए is not a command


@test("L7", "hookscore: Hindi greeting and video preamble are dealbreakers, opener penalised")
def _():
    d = hook("नमस्ते दोस्तों, आज के इस वीडियो में हम बात करेंगे बजट की।")
    assert any(f.startswith("Greeting") for f in d["flags"]), d["flags"]
    assert any(f.startswith("Video preamble") for f in d["flags"]), d["flags"]
    assert "weak opener" in d["checks"]["FRONTLOAD"]["detail"], d["checks"]["FRONTLOAD"]
    assert d["verdict"] == "WEAK", d
    # a word that merely starts like a weak opener is not one: तोड़ is not तो
    assert "weak opener" not in hook("तोड़ दिया मैंने अपना पुराना नियम।")["checks"]["FRONTLOAD"]["detail"]


@test("L8", "hookscore: Hindi scores carry the uncalibrated label, in JSON and in text")
def _():
    d = hook("मैंने एक गलती की और दो लाख रुपये डूब गए।")
    assert d["lang"] == "hi" and d["calibration"].startswith("uncalibrated"), d
    _, out, _ = run("ig-reel/hookscore.py", "--hook", "मैंने एक गलती की और दो लाख रुपये डूब गए।")
    assert "Language: hi. Score is uncalibrated" in out, out
    _, out, _ = run("ig-reel/hookscore.py", os.path.join("hi", "hooks.txt"))
    assert "[hi]" in out and "[mixed]" in out and "uncalibrated" in out, out


# ======================================================================
# beats.py
# ======================================================================
@test("L9", "beats: a 100-word Hindi script times at 40s (150 wpm); --wpm still wins")
def _():
    a = beats(fixture("script.txt"))
    assert (a["total_words"], a["wpm"], a["lang"]) == (100, 150, "hi"), (a["total_words"], a["wpm"])
    assert abs(a["total_seconds"] - 40.0) < 0.01, a["total_seconds"]
    assert beats(fixture("script.txt"), "--wpm", "165")["wpm"] == 165.0
    assert beats("Proposals used to take me five hours.")["wpm"] == 165     # English default


@test("L10", "beats: । splits a long Hindi paragraph, spoken numbers are concrete, loops seen")
def _():
    para = " ".join(["मैंने तीस दिन तक हर खर्च एक छोटी सी कॉपी में लिखा।"] * 4)
    a = beats(para)
    assert len(a["beats"]) > 1, a["beats"]
    assert a["beats"][0]["concrete"] >= 1, a["beats"][0]
    a = beats(fixture("script.txt"))
    assert any(n.startswith("Loops:") for n in a["notes"]), a["notes"]       # बारह हज़ार returns
    assert not any("है" in n or "का\"" in n for n in a["notes"] if n.startswith("Loops:"))


@test("L11", "beats: copied on its own, the fallback lists and the Hindi block still work")
def _():
    solo = os.path.join(HERE, "solo_beats")
    os.makedirs(solo, exist_ok=True)
    for f in os.listdir(solo):
        os.remove(os.path.join(solo, f))
    shutil.copy(os.path.join(SK, "ig-reel/beats.py"), solo)
    p = subprocess.run([sys.executable, os.path.join(solo, "beats.py"), os.path.join(HI, "script.txt"),
                        "--json"], capture_output=True, text=True, env=ENV, cwd=HERE)
    assert p.returncode == 0, p.stderr[-300:]
    a = json.loads(p.stdout)
    assert (a["total_words"], a["wpm"]) == (100, 150), a["total_words"]


# ======================================================================
# caption.py
# ======================================================================
@test("L12", "caption: 'Comment में PAPERS लिखिए' is one typeable keyword ask (was no ask)")
def _():
    d = caption(fixture("caption_mixed.txt"))
    assert d["asks"] == ["comment a keyword"], d["asks"]
    assert chk(d, "ONE ASK")["status"] == "PASS", chk(d, "ONE ASK")
    k = chk(d, "KEYWORD ASK")
    assert k["status"] == "PASS" and k["detail"].startswith("PAPERS "), k
    assert d["lang"] == "mixed", d.get("lang")
    for line in ("PAPERS कमेंट करें और मैं भेज दूँगा।", "कमेंट में \"PAPERS\" लिखिए"):
        assert chk(caption(line), "KEYWORD ASK")["status"] == "PASS", line


@test("L13", "caption: a Devanagari or lower-case keyword is loose; 'Comment में बताइए' is a question")
def _():
    for line in ("Comment में पेपर लिखिए", "comment में papers लिखिए", "कमेंट में 'पूरी लिस्ट' लिखिए"):
        d = caption(line)
        assert chk(d, "KEYWORD ASK")["status"] == "WARN", (line, d["checks"])
        assert "comment a phrase" in d["asks"], (line, d["asks"])
    d = caption("Comment में बताइए आप क्या करते।")
    assert d["asks"] == ["answer a question"], d["asks"]
    assert not any(c["check"] == "KEYWORD ASK" for c in d["checks"]), d["checks"]


@test("L14", "caption: Hindi greeting fails the first line; Hindi asks counted, 'भेज दूँगा' is not")
def _():
    d = caption(fixture("caption_greeting.txt"))
    assert chk(d, "FIRST LINE")["status"] == "FAIL", chk(d, "FIRST LINE")
    assert d["asks"] == ["save this", "share this"], d["asks"]
    assert chk(d, "ONE ASK")["status"] == "WARN"
    assert "share this" not in caption("मैं आपको checklist भेज दूँगा।")["asks"]
    assert caption("DM कीजिए")["asks"] == ["DM me"]


@test("L15", "caption: Hindi hashtags are tags; Hindi number words make the hook concrete")
def _():
    d = caption("ये बात लंबी है और कहानी भी लंबी है, पर सुनिए।\n\n#रायपुर #घर #homebuying")
    assert d["hashtags"] == ["#रायपुर", "#घर", "#homebuying"], d["hashtags"]
    assert chk(d, "TAG PLACEMENT")["status"] == "WARN"          # short caption, tags are visible
    assert chk(caption("पाँच लाख की गलती से बचिए।"), "HOOK IS CONCRETE")["status"] == "PASS"
    assert chk(caption("एक गलती से बचिए।"), "HOOK IS CONCRETE")["status"] == "WARN"


# ======================================================================
# detect.py
# ======================================================================
@test("L16", "detect: Hindi words and । sentences are measured, with the uncalibrated label")
def _():
    d = detect(fixture("human_hi.txt"))
    assert d["checks_judged"] == 5 and d["complete"], d["checks"]
    assert "8 sentences" in d["checks"]["BURSTINESS"]["detail"], d["checks"]["BURSTINESS"]
    assert d["lang"] == "hi" and d["calibration"].startswith("uncalibrated"), d
    assert d["checks"]["VOICE"]["detail"].startswith("contractions not measured (hi)"), d["checks"]["VOICE"]
    piped = fixture("human_hi.txt").replace("।", " |")               # keyboards without ।
    assert detect(piped)["checks"]["BURSTINESS"] == d["checks"]["BURSTINESS"]


@test("L17", "detect: Hindi stock phrases count as slop; the stock draft scores below the human one")
def _():
    bad, good = detect(fixture("draft_hi.txt")), detect(fixture("human_hi.txt"))
    assert bad["checks"]["SLOP DENSITY"]["score"] < 50 < good["checks"]["SLOP DENSITY"]["score"], (
        bad["checks"]["SLOP DENSITY"], good["checks"]["SLOP DENSITY"])
    assert bad["human_score"] < good["human_score"], (bad["human_score"], good["human_score"])
    assert bad["verdict"] != "PASS", bad
    # commas between the words do not hide a phrase, the same rule as English
    assert detect("लाइक, शेयर और सब्सक्राइब ज़रूर करें।")["checks"]["SLOP DENSITY"]["score"] < 100


@test("L18", "detect: a joiner inside a Devanagari word is not an invisible-character tell")
def _():
    hindi = "क्\u200cष और क्\u200dष दोनों सही हैं।"
    assert detect(hindi)["checks"]["FINGERPRINT"]["detail"].startswith("0 invisible"), detect(hindi)
    assert detect("zero\u200bwidth here.")["checks"]["FINGERPRINT"]["detail"].startswith("1 invisible")


# ======================================================================
# humanize.py
# ======================================================================
@test("L19", "humanize: a joiner between Devanagari letters survives, English joiners still go")
def _():
    raw = fixture("joiners.txt")
    out = humanize(raw)["text"]
    hindi_line = raw.splitlines()[0]
    assert out.splitlines()[0] == hindi_line, (out.splitlines()[0], hindi_line)   # byte-identical
    assert "\u200b" not in out and "join\u200cer" not in out and "joiner" in out, repr(out)
    assert humanize("👨\u200d👩\u200d👧 trip")["text"] == "👨👩👧 trip\n"           # as before


@test("L20", "humanize: Hindi stock phrases are reported as tells and never rewritten")
def _():
    raw = fixture("draft_hi.txt")
    d = humanize(raw)
    assert d["text"] == raw, "Hindi text was rewritten"
    names = [s["name"] for s in d["report"]["structures"]]
    assert "Hindi stock phrase: आज के इस डिजिटल युग में" in names, names
    assert d["report"]["lexical"] == [], d["report"]["lexical"]


@test("L21", "humanize: a Hindi line is kept after an English deletion elsewhere in the draft")
def _():
    out = humanize(fixture("mixed_delete.txt"))["text"]
    # deleting "Follow for more!" used to drop the whole Hindi line as 'no text left'
    assert out == "Proposals take five hours. Here is the fix.\nबजट हर महीने बनाइए।\n", repr(out)


# ======================================================================
# swipe.py and hooks.json
# ======================================================================
@test("L22", "swipe: Hindi hooks are named by match_hi, counted in words, tagged with lang")
def _():
    _, out, _ = run("ig-viral/swipe.py", os.path.join("hi", "swipe.tsv"), "--json")
    reels = json.loads(out)["reels"]
    row = lambda start: next(r for r in reels if r["hook"].startswith(start))
    nobody = row("कोई आपको")
    assert (nobody["formula_id"], nobody["lang"], nobody["words"]) == (3, "hi", 11), nobody
    assert row("Plot का token")["formula_id"] == 2, row("Plot का token")
    assert row("आज मैं अपनी")["formula"] == "unclassified", row("आज मैं अपनी")
    assert "lang" not in row("steal this") and row("steal this")["formula_id"] == 9


@test("L23", "hooks.json: every match_hi compiles, and each formula's Hindi example lands on it")
def _():
    sw = module("ig-viral/swipe.py")
    formulas = sw.load_formulas(os.path.join(SK, "ig-reel/hooks.json"))
    assert sum(1 for f in formulas if f[3]) == 25, "expected 25 formulas with match_hi"
    examples = {
        1: "एक गलत agreement से मुझे 4 लाख का नुकसान हुआ।", 3: "कोई आपको ये नहीं बताता कि टैक्स कैसे बचता है।",
        5: "पहले रजिस्ट्री में 3 दिन लगते थे, अब 2 घंटे।", 7: "लोग जो सबसे बड़ी गलती करते हैं।",
        10: "अगर आप पहली बार घर खरीद रहे हैं, ये 40 सेकंड देखिए।", 16: "Loan लेने से पहले कौन से कागज़ चाहिए?",
        19: "Token देने से पहले ये एक बात जान लीजिए।", 20: "आपको बड़े budget की ज़रूरत नहीं है।",
        23: "10 में से 7 खरीदार ये सवाल नहीं पूछते।", 26: "घर का loan लेने का सबसे आसान तरीका।",
    }
    for fid, text in examples.items():
        assert sw.classify(text, formulas)[0] == fid, (fid, text, sw.classify(text, formulas))
    for plain in ("मैं कल बाज़ार गया था।", "आज मौसम अच्छा है।"):
        assert sw.classify(plain, formulas) == (None, "unclassified"), plain


@test("L24", "Hindi vocabulary is Devanagari only, so it can never match English text")
def _():
    hs = module("ig-reel/hookscore.py")
    latin = re.compile(r"[A-Za-z]")
    for name in ("HI_SPOKEN_NUMBERS", "HI_MONEY_WORDS", "HI_YOU", "HI_ME", "HI_STAKES", "HI_IMPERATIVES"):
        bad = [w for w in getattr(hs, name) if latin.search(w)]
        assert not bad, (name, bad)
    lex = json.load(open(os.path.join(SK, "ig-human/slop.json"), encoding="utf-8"))
    assert lex["hi"] and all(not latin.search(e["find"]) and e["fix"] for e in lex["hi"]), lex["hi"][:2]


@test("L25", "no invisible characters in any skill source file")
def _():
    import unicodedata
    for s in SCRIPTS + ["ig-reel/hooks.json", "ig-human/slop.json"]:
        src = open(os.path.join(SK, s), encoding="utf-8").read()
        bad = [hex(ord(c)) for c in src if unicodedata.category(c) == "Cf"]
        assert not bad, (s, bad[:5])


if __name__ == "__main__":
    only = sys.argv[1:]
    passed = failed = 0
    for tid, desc, fn in TESTS:
        if only and not any(tid.startswith(o) for o in only):
            continue
        try:
            fn()
            passed += 1
            print(f"PASS  {tid:<4} {desc}")
        except Exception as e:
            failed += 1
            msg = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
            print(f"FAIL  {tid:<4} {desc}\n            -> {msg[:300]}")
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
