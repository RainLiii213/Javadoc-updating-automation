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
        declaration_info = _read_declaration_after(source, match.end())
        if declaration_info is None:
            continue
        declaration, declaration_start_offset, declaration_end_offset = declaration_info
        if not declaration:
            continue
        entity = _parse_declaration(
            declaration=declaration,
            javadoc=match.group(0),
            start_line=_line_number(source, match.start()),
            end_line=_line_number(source, match.end()),
            code_start_line=_line_number(source, declaration_start_offset),
            code_end_line=_entity_end_line(source, declaration_start_offset, declaration_end_offset),
        )
        if entity is not None:
            entities.append(entity)
    return entities


def _read_declaration_after(source: str, offset: int) -> tuple[str, int, int] | None:
    declaration_lines: list[str] = []
    search_offset = offset
    declaration_start_offset = -1
    for line in source[offset:].splitlines(keepends=True):
        stripped = line.strip()
        if not stripped:
            search_offset += len(line)
            continue
        if stripped.startswith("//"):
            search_offset += len(line)
            continue
        if declaration_start_offset == -1:
            declaration_start_offset = search_offset + line.index(stripped)
        declaration_lines.append(stripped)
        joined = " ".join(declaration_lines)
        if "{" in stripped or ";" in stripped:
            declaration_end_offset = search_offset + len(line)
            return (
                joined.split("{", 1)[0].split(";", 1)[0].strip(),
                declaration_start_offset,
                declaration_end_offset,
            )
        search_offset += len(line)
    return None


def _parse_declaration(
    declaration: str,
    javadoc: str,
    start_line: int,
    end_line: int,
    code_start_line: int,
    code_end_line: int,
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
            code_start_line=code_start_line,
            code_end_line=code_end_line,
        )

    if "(" not in declaration or ")" not in declaration:
        return _parse_field(declaration, javadoc, start_line, end_line, code_start_line, code_end_line)
    return _parse_method(declaration, javadoc, start_line, end_line, code_start_line, code_end_line)


def _parse_method(
    declaration: str,
    javadoc: str,
    start_line: int,
    end_line: int,
    code_start_line: int,
    code_end_line: int,
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
        code_start_line=code_start_line,
        code_end_line=code_end_line,
    )


def _parse_field(
    declaration: str,
    javadoc: str,
    start_line: int,
    end_line: int,
    code_start_line: int,
    code_end_line: int,
) -> EntityDoc | None:
    declaration = declaration.split("=", 1)[0].strip()
    tokens = _clean_type_tokens(declaration.split())
    if len(tokens) < 2:
        return None
    name = tokens[-1].rstrip("[]")
    if not re.match(r"^[A-Za-z_$][\w$]*$", name):
        return None
    return EntityDoc(
        entity_type="field",
        name=name,
        signature=declaration,
        javadoc=javadoc,
        start_line=start_line,
        end_line=end_line,
        return_type=tokens[-2],
        code_start_line=code_start_line,
        code_end_line=code_end_line,
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


def _entity_end_line(source: str, declaration_start_offset: int, declaration_end_offset: int) -> int:
    declaration_text = source[declaration_start_offset:declaration_end_offset]
    if ";" in declaration_text and "{" not in declaration_text:
        return _line_number(source, max(declaration_start_offset, declaration_end_offset - 1))

    open_index = source.find("{", declaration_start_offset)
    if open_index == -1:
        return _line_number(source, max(declaration_start_offset, declaration_end_offset - 1))

    depth = 0
    for index in range(open_index, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return _line_number(source, index)
    return _line_number(source, declaration_end_offset)
