from .models import Classification, EntityDoc
from .text_utils import normalize_doc_text


QUALITY_ORDER = {"A": 3, "B": 2, "C": 1}


def classify_entity_change(
    old: EntityDoc | None,
    new: EntityDoc | None,
    nearby_code_changed: bool,
) -> Classification | None:
    if new is None:
        if old is None or not normalize_doc_text(old.javadoc):
            return None
        if old.entity_type == "method":
            change_type = "method_deletion"
        elif old.entity_type == "field":
            change_type = "field_deletion"
        else:
            change_type = "class_deletion"
        return Classification(change_type, "C", "JAVADOC_DELETION", _method_change_label(old, new, True))
    if old is None:
        if normalize_doc_text(new.javadoc):
            return Classification(_addition_type(new), "B", "JAVADOC_ADDITION", _method_change_label(old, new, True))
        return None
    if not _javadoc_changed(old.javadoc, new.javadoc):
        return None
    if _only_see_changed(old.javadoc, new.javadoc):
        return None
    javadoc_change_type = "JAVADOC_MODIFICATION"
    method_change_type = _method_change_label(old, new, nearby_code_changed)
    if old.entity_type != new.entity_type:
        return Classification("class_api_change", "A", javadoc_change_type, method_change_type)
    if old.name != new.name:
        return Classification(
            "method_rename" if new.entity_type == "method" else "class_api_change",
            "A",
            javadoc_change_type,
            method_change_type,
        )
    if old.parameters != new.parameters:
        return Classification("parameter_change", "A", javadoc_change_type, method_change_type)
    if old.return_type != new.return_type:
        return Classification("return_type_change", "A", javadoc_change_type, method_change_type)
    if old.throws != new.throws:
        return Classification("exception_change", "A", javadoc_change_type, method_change_type)
    if nearby_code_changed:
        return Classification("nearby_code_and_javadoc_change", "C", javadoc_change_type, method_change_type)
    return None


def quality_meets_threshold(quality: str, min_quality: str) -> bool:
    return QUALITY_ORDER[quality] >= QUALITY_ORDER[min_quality]


def _addition_type(entity: EntityDoc) -> str:
    if entity.entity_type == "class":
        return "class_addition"
    if entity.entity_type == "field":
        return "field_addition"
    return "method_addition"


def _method_change_label(old: EntityDoc | None, new: EntityDoc | None, code_changed: bool) -> str:
    entity = new or old
    if entity is None or entity.entity_type != "method":
        return "METHOD_UNCHANGED"
    if old is None and new is not None:
        return "METHOD_ADDITION"
    if old is not None and new is None:
        return "METHOD_DELETION"
    if code_changed:
        return "METHOD_MODIFICATION"
    return "METHOD_UNCHANGED"


def _javadoc_changed(old_doc: str, new_doc: str) -> bool:
    return normalize_doc_text(old_doc) != normalize_doc_text(new_doc)


def _only_see_changed(old_doc: str, new_doc: str) -> bool:
    old_lines = set(_significant_doc_lines(old_doc, include_see=False))
    new_lines = set(_significant_doc_lines(new_doc, include_see=False))
    old_see = set(_see_lines(old_doc))
    new_see = set(_see_lines(new_doc))
    return old_lines == new_lines and old_see != new_see


def _significant_doc_lines(text: str, include_see: bool) -> list[str]:
    lines: list[str] = []
    for line in normalize_doc_text(text).splitlines():
        if not include_see and line.startswith("@see"):
            continue
        lines.append(line)
    return lines


def _see_lines(text: str) -> list[str]:
    return [line for line in normalize_doc_text(text).splitlines() if line.startswith("@see")]
