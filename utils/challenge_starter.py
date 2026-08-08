import re

from database import get_session, Challenge, ChallengeTestCase, ChallengeStarterCode as ChallengeStarterCodeModel

_INT_RE = re.compile(r"-?\d+")

# Languages that need a starter code skeleton (require boilerplate such as a
# main/class wrapper) — the seeder guarantees they have one. Existing C++ starter
# codes are preserved exactly as they are and are never modified by this module.
STARTER_LANGUAGES = ["Java", "C#", "Go"]

# Scripting languages that need no boilerplate — the solver writes the logic
# directly, so no starter code is stored or pre-filled for them.
NO_STARTER_LANGUAGES = ["Python", "JavaScript"]

# Starter code templates keyed by input mode:
#   "numeric" -> reads every integer from stdin in order
#   "string"  -> reads every line from stdin
# The solver writes their algorithm in the marked section.
STARTER_TEMPLATES = {
    "numeric": {
        "Java": (
            'import java.util.*;\n'
            '\n'
            'public class Main {\n'
            '    public static void main(String[] args) {\n'
            '        Scanner sc = new Scanner(System.in);\n'
            '        List<Integer> data = new ArrayList<>();\n'
            '        while (sc.hasNextInt()) {\n'
            '            data.add(sc.nextInt());\n'
            '        }\n'
            '        // data contains every integer from stdin in order\n'
            '        // write your solution here\n'
            '    }\n'
            '}\n'
        ),
        "C#": (
            'using System;\n'
            'using System.Collections.Generic;\n'
            'using System.Linq;\n'
            '\n'
            'class Program {\n'
            '    static void Main() {\n'
            '        List<int> data = Console.In.ReadToEnd()\n'
            '            .Split(new char[] { \' \', \'\\n\', \'\\r\', \'\\t\' }, StringSplitOptions.RemoveEmptyEntries)\n'
            '            .Select(int.Parse)\n'
            '            .ToList();\n'
            '        // data contains every integer from stdin in order\n'
            '        // write your solution here\n'
            '    }\n'
            '}\n'
        ),
        "Go": (
            'package main\n'
            '\n'
            'import (\n'
            '\t"bufio"\n'
            '\t"os"\n'
            '\t"strconv"\n'
            ')\n'
            '\n'
            'func main() {\n'
            '\tscanner := bufio.NewScanner(os.Stdin)\n'
            '\tscanner.Split(bufio.ScanWords)\n'
            '\tvar data []int\n'
            '\tfor scanner.Scan() {\n'
            '\t\tif n, err := strconv.Atoi(scanner.Text()); err == nil {\n'
            '\t\t\tdata = append(data, n)\n'
            '\t\t}\n'
            '\t}\n'
            '\t// data contains every integer from stdin in order\n'
            '\t// write your solution here\n'
            '}\n'
        ),
    },
    "string": {
        "Java": (
            'import java.util.*;\n'
            '\n'
            'public class Main {\n'
            '    public static void main(String[] args) {\n'
            '        Scanner sc = new Scanner(System.in);\n'
            '        List<String> lines = new ArrayList<>();\n'
            '        while (sc.hasNextLine()) {\n'
            '            lines.add(sc.nextLine());\n'
            '        }\n'
            '        // lines contains every line from stdin\n'
            '        // write your solution here\n'
            '    }\n'
            '}\n'
        ),
        "C#": (
            'using System;\n'
            'using System.Collections.Generic;\n'
            '\n'
            'class Program {\n'
            '    static void Main() {\n'
            '        List<string> lines = new List<string>();\n'
            '        string line;\n'
            '        while ((line = Console.ReadLine()) != null) {\n'
            '            lines.Add(line);\n'
            '        }\n'
            '        // lines contains every line from stdin\n'
            '        // write your solution here\n'
            '    }\n'
            '}\n'
        ),
        "Go": (
            'package main\n'
            '\n'
            'import (\n'
            '\t"bufio"\n'
            '\t"os"\n'
            ')\n'
            '\n'
            'func main() {\n'
            '\tscanner := bufio.NewScanner(os.Stdin)\n'
            '\tvar lines []string\n'
            '\tfor scanner.Scan() {\n'
            '\t\tlines = append(lines, scanner.Text())\n'
            '\t}\n'
            '\t// lines contains every line from stdin\n'
            '\t// write your solution here\n'
            '}\n'
        ),
    },
}


def _detect_modes(sess) -> dict:
    """Map challenge_id -> input mode ('numeric' | 'string') based on test cases."""
    modes = {}
    rows = sess.query(ChallengeTestCase.challenge_id, ChallengeTestCase.input).all()
    for challenge_id, inp in rows:
        cur = modes.get(challenge_id, "numeric")
        if cur == "string":
            continue
        if any(not _INT_RE.fullmatch(tok) for tok in (inp or "").split()):
            modes[challenge_id] = "string"
        else:
            modes[challenge_id] = "numeric"
    return modes


def seed_all_starter_codes() -> dict:
    """Generate per-language starter code for every challenge that is missing one.

    C++ rows are never touched. Existing rows for other starter languages are
    kept (so dashboard-edited starter codes are preserved). Any stored starter
    for a no-starter scripting language is removed so nothing gets pre-filled.
    Idempotent. Returns a dict of {language: rows_inserted}.
    """
    sess = get_session()
    inserted = {lang: 0 for lang in STARTER_LANGUAGES}
    removed = {lang: 0 for lang in NO_STARTER_LANGUAGES}
    try:
        if NO_STARTER_LANGUAGES:
            rows = (
                sess.query(ChallengeStarterCodeModel)
                .filter(ChallengeStarterCodeModel.language.in_(NO_STARTER_LANGUAGES))
                .all()
            )
            for row in rows:
                sess.delete(row)
                removed[row.language] += 1
        challenges = sess.query(Challenge).all()
        existing = {
            (row.challenge_id, row.language)
            for row in sess.query(ChallengeStarterCodeModel)
            .filter(ChallengeStarterCodeModel.language.in_(STARTER_LANGUAGES))
            .all()
        }
        modes = _detect_modes(sess)
        for ch in challenges:
            mode = modes.get(ch.id, "numeric")
            for lang in STARTER_LANGUAGES:
                if (ch.id, lang) in existing:
                    continue
                sess.add(ChallengeStarterCodeModel(
                    challenge_id=ch.id,
                    language=lang,
                    code=STARTER_TEMPLATES[mode][lang],
                ))
                inserted[lang] += 1
        sess.commit()
    finally:
        sess.close()
    print(f"[challenge_starter] seeded {inserted} / removed {removed}")
    return inserted
