import re

from .models import EntityDoc


JAVADOC_PATTERN = re.compile(r"/\*\*.*?\*/", re.DOTALL)
CLASS_PATTERN = re.compile(r"\b(class|interface|enum|record)\s+([A-Za-z_$][\w$]*)")
CONTROL_KEYWORDS = {"if", "for", "while", "switch", "catch", "return", "throw", "new"}
MODIFIERS = {
    "public",
    "protected",
    "private",
    "static",
    "final",
    "abstract",
    "synchronized",
    "native",
    "strictfp",
    "default",
    "transient",
    "volatile",
}


def parse_entities(source: str) -> list[EntityDoc]:
    entities: list[EntityDoc] = []
    for match in JAVADOC_PATTERN.finditer(source):
        declaration = _read_declaration_after(source, match.end())
        if not declaration:
            continue
        entity = _parse_declaration(
            declaration=declaration,
            javadoc=match.group(0),
            start_line=_line_number(source, match.start()),
            end_line=_line_number(source, match.end()),
        )
        if entity is not None:
            entities.append(entity)
    return entities


def _read_declaration_after(source: str, offset: int) -> str:
    declaration_lines: list[str] = []
    for line in source[offset:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("//"):
            continue
        declaration_lines.append(stripped)
        joined = " ".join(declaration_lines)
        if "{" in stripped or ";" in stripped:
            return joined.split("{", 1)[0].split(";", 1)[0].strip()
    return ""


def _parse_declaration(
    declaration: str,
    javadoc: str,
    start_line: int,
    end_line: int,
) -> EntityDoc | None:
    class_match = CLASS_PATTERN.search(declaration)
    if class_match:
        return EntityDoc(
            entity_type="class",
            name=class_match.group(2),
            signature=declaration,
            javadoc=javadoc,
            start_line=start_line,
            end_line=end_line,
        )

    if "(" not in declaration or ")" not in declaration:
        return None
    return _parse_method(declaration, javadoc, start_line, end_line)


def _parse_method(
    declaration: str,
    javadoc: str,
    start_line: int,
    end_line: int,
) -> EntityDoc | None:
    equals_index = declaration.find("=")
    paren_index = declaration.find("(")
    if equals_index != -1 and equals_index < paren_index:
        return None
    before_params, rest = declaration.split("(", 1)
    params_text, after_params = rest.split(")", 1)
    tokens = _clean_type_tokens(before_params.split())
    if not tokens:
        return None
    name = tokens[-1]
    if name in CONTROL_KEYWORDS:
        return None
    return_type = ""
    if len(tokens) >= 2:
        return_type = tokens[-2]
    parameters = _split_parameters(params_text)
    throws = _parse_throws(after_params)
    return EntityDoc(
        entity_type="method",
        name=name,
        signature=declaration,
        javadoc=javadoc,
        start_line=start_line,
        end_line=end_line,
        return_type=return_type,
        parameters=parameters,
        throws=throws,
    )


def _clean_type_tokens(tokens: list[str]) -> list[str]:
    cleaned = [token for token in tokens if token not in MODIFIERS and not token.startswith("@")]
    if len(cleaned) == 1:
        return cleaned
    return cleaned


def _split_parameters(params_text: str) -> list[str]:
    params_text = params_text.strip()
    if not params_text:
        return []
    return [part.strip() for part in params_text.split(",") if part.strip()]


def _parse_throws(after_params: str) -> list[str]:
    throws_match = re.search(r"\bthrows\s+(.+)$", after_params.strip())
    if not throws_match:
        return []
    throws_text = throws_match.group(1).strip()
    return [part.strip() for part in throws_text.split(",") if part.strip()]


def _line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1
