import re
from collections import Counter

from .models import Classification, EntityDoc
from .text_utils import (
    CONTRACT_TERMS,
    is_substantive_javadoc_change,
    javadoc_similarity,
    normalize_javadoc_for_semantic_compare,
)


JAVA_KEYWORDS = {
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "continue", "default", "do", "double", "else", "enum", "extends",
    "false", "final", "finally", "float", "for", "if", "implements", "import",
    "instanceof", "int", "interface", "long", "native", "new", "null", "package",
    "private", "protected", "public", "record", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "true", "try", "void", "volatile", "while",
}
CODE_BEHAVIOR_TOKENS = {
    "break", "case", "catch", "continue", "default", "else", "false", "if", "new",
    "null", "return", "switch", "throw", "true", "try", "while",
}
LINK_STOP_WORDS = {
    "a", "an", "and", "arg", "argument", "class", "code", "data", "input",
    "method", "object", "output", "param", "parameter", "result", "return",
    "returns", "the", "this", "value", "values", "string", "char", "character",
    "sequence", "array", "type", "name",
}
CONTRACT_GROUPS = (
    {"null", "nullable", "nonnull", "requirenonnull"},
    {"throw", "throws", "exception", "exceptions", "fail", "fails", "failure"},
    {"timeout", "time", "duration", "instant", "epoch", "millisecond", "milliseconds", "second", "seconds"},
    {"empty", "blank"},
    {"valid", "invalid", "validate", "validation"},
    {"minimum", "maximum", "min", "max", "negative", "positive", "overflow"},
    {"deprecated", "deprecation", "obsolete"},
)
JAVA_TOKEN_PATTERN = re.compile(
    r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_$][\w$]*|'
    r'\d+(?:\.\d+)?|==|!=|<=|>=|&&|\|\||\+\+|--|->|[{}()[\];,.?:+\-*/%<>=!]'
)


def classify_entity_change(
    old: EntityDoc | None,
    new: EntityDoc | None,
    nearby_code_changed: bool,
    code_before: str = "",
    code_after: str = "",
) -> Classification | None:
    if old is None or new is None:
        return None
    if old.entity_type not in {"method", "class"} or new.entity_type not in {"method", "class"}:
        return None
    if not nearby_code_changed:
        return None
    if not old.javadoc.strip() or not new.javadoc.strip():
        return None
    if not is_substantive_javadoc_change(old.javadoc, new.javadoc):
        return None
    code_before = code_before or old.signature
    code_after = code_after or new.signature
    if not is_substantial_code_change(code_before, code_after, old, new):
        return None
    if not is_logically_connected_change(code_before, code_after, old, new):
        return None
    javadoc_change_type = "JAVADOC_MODIFICATION"
    method_change_type = "METHOD_MODIFICATION"
    if old.entity_type != new.entity_type:
        return Classification("class_api_change", javadoc_change_type, method_change_type)
    if old.name != new.name:
        return Classification(
            "method_rename" if new.entity_type == "method" else "class_api_change",
            javadoc_change_type,
            method_change_type,
        )
    if old.parameters != new.parameters:
        return Classification("parameter_change", javadoc_change_type, method_change_type)
    if old.return_type != new.return_type:
        return Classification("return_type_change", javadoc_change_type, method_change_type)
    if old.throws != new.throws:
        return Classification("exception_change", javadoc_change_type, method_change_type)
    return Classification("code_and_javadoc_change", javadoc_change_type, method_change_type)


def is_substantial_code_change(
    code_before: str,
    code_after: str,
    old: EntityDoc | None = None,
    new: EntityDoc | None = None,
) -> bool:
    old_tokens = _java_tokens(code_before)
    new_tokens = _java_tokens(code_after)
    if not old_tokens or not new_tokens or old_tokens == new_tokens:
        return False
    if Counter(old_tokens) == Counter(new_tokens):
        return False
    if _identifier_shape(old_tokens) == _identifier_shape(new_tokens):
        return False

    removed, added = _changed_tokens(old_tokens, new_tokens)
    changed = removed + added
    if old is not None and new is not None:
        if _parameter_types(old.parameters) != _parameter_types(new.parameters):
            return True
        if old.return_type != new.return_type or old.throws != new.throws:
            return True
    if set(changed) & CODE_BEHAVIOR_TOKENS:
        return True
    if any(token.startswith(("\"", "'")) for token in changed):
        return True
    return len(changed) >= 4


def is_logically_connected_change(
    code_before: str,
    code_after: str,
    old: EntityDoc,
    new: EntityDoc,
) -> bool:
    code_removed, code_added = _changed_terms(code_before, code_after)
    doc_removed, doc_added = _changed_doc_terms(old.javadoc, new.javadoc)
    code_terms = (code_removed | code_added) - LINK_STOP_WORDS
    doc_terms = (doc_removed | doc_added) - LINK_STOP_WORDS
    direct_overlap = code_terms & doc_terms
    contract_overlap = _shared_contract_group(code_terms, doc_terms)
    api_link = _api_contract_link(old, new, doc_terms)
    strong_link = bool(direct_overlap or contract_overlap or api_link)
    if not strong_link:
        return False
    similarity = javadoc_similarity(old.javadoc, new.javadoc)
    if old.entity_type == "class" and similarity >= 0.85:
        if len(direct_overlap) < 2 and not contract_overlap:
            return False
    if similarity >= 0.9:
        return bool(
            direct_overlap & CONTRACT_TERMS
            or contract_overlap
            or api_link
        )
    return True


def _java_tokens(code: str) -> list[str]:
    code = re.sub(r"/\*.*?\*/|//[^\n]*", " ", code, flags=re.DOTALL)
    return [token.lower() for token in JAVA_TOKEN_PATTERN.findall(code)]


def _identifier_shape(tokens: list[str]) -> list[str]:
    mapping: dict[str, str] = {}
    shaped: list[str] = []
    for token in tokens:
        if re.fullmatch(r"[a-z_$][\w$]*", token) and token not in JAVA_KEYWORDS:
            mapping.setdefault(token, f"id{len(mapping)}")
            shaped.append(mapping[token])
        else:
            shaped.append(token)
    return shaped


def _changed_tokens(old_tokens: list[str], new_tokens: list[str]) -> tuple[list[str], list[str]]:
    return (
        list((Counter(old_tokens) - Counter(new_tokens)).elements()),
        list((Counter(new_tokens) - Counter(old_tokens)).elements()),
    )


def _changed_terms(old_text: str, new_text: str) -> tuple[set[str], set[str]]:
    old_terms = Counter(_code_terms(old_text))
    new_terms = Counter(_code_terms(new_text))
    return set(old_terms - new_terms), set(new_terms - old_terms)


def _code_terms(code: str) -> list[str]:
    terms: list[str] = []
    for token in _java_tokens(code):
        if token in JAVA_KEYWORDS or re.fullmatch(r"\d+(?:\.\d+)?", token):
            terms.append(token)
        elif re.fullmatch(r"[a-z_$][\w$]*", token):
            terms.extend(_split_identifier(token))
        elif token.startswith(("\"", "'")):
            terms.extend(re.findall(r"[a-z]+", token.lower()))
    return terms


def _changed_doc_terms(old_doc: str, new_doc: str) -> tuple[set[str], set[str]]:
    old_terms = Counter(normalize_javadoc_for_semantic_compare(old_doc).split())
    new_terms = Counter(normalize_javadoc_for_semantic_compare(new_doc).split())
    return set(old_terms - new_terms), set(new_terms - old_terms)


def _split_identifier(identifier: str) -> list[str]:
    spaced = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", identifier.replace("_", " "))
    return [part.lower() for part in spaced.split() if len(part) > 1]


def _shared_contract_group(code_terms: set[str], doc_terms: set[str]) -> bool:
    return any(code_terms & group and doc_terms & group for group in CONTRACT_GROUPS)


def _api_contract_link(old: EntityDoc, new: EntityDoc, doc_terms: set[str]) -> bool:
    if _parameter_types(old.parameters) != _parameter_types(new.parameters):
        parameter_terms = set()
        for parameter in old.parameters + new.parameters:
            parameter_terms.update(_split_identifier(parameter))
        if parameter_terms & doc_terms:
            return True
    if old.throws != new.throws and ({"throw", "throws", "exception"} & doc_terms):
        return True
    if old.return_type != new.return_type and ({"return", "returns"} & doc_terms):
        return True
    return False


def _parameter_types(parameters: list[str]) -> list[str]:
    types: list[str] = []
    for parameter in parameters:
        tokens = [token for token in parameter.split() if token not in {"final"} and not token.startswith("@")]
        types.append(" ".join(tokens[:-1]) if len(tokens) > 1 else " ".join(tokens))
    return types


