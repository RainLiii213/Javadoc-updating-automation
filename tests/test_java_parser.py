from javadoc_miner.java_parser import parse_entities


def test_parse_method_javadoc_with_signature_parts():
    source = """
package org.example;

public class Person {
    /**
     * Returns the full name.
     *
     * @param fallback fallback value
     * @return full name
     * @throws IllegalStateException when missing
     */
    public String getFullName(String fallback) throws IllegalStateException {
        return fallback;
    }
}
"""

    entities = parse_entities(source)
    method = next(entity for entity in entities if entity.name == "getFullName")

    assert method.entity_type == "method"
    assert method.return_type == "String"
    assert method.parameters == ["String fallback"]
    assert method.throws == ["IllegalStateException"]
    assert "@param fallback" in method.javadoc


def test_parse_class_javadoc():
    source = """
/**
 * Person value object.
 */
public final class Person {
}
"""

    entities = parse_entities(source)

    assert entities[0].entity_type == "class"
    assert entities[0].name == "Person"


def test_parse_constructor_as_method_entity():
    source = """
public class Person {
    /**
     * Creates a person.
     */
    public Person(String name) {
    }
}
"""

    entities = parse_entities(source)

    assert entities[0].entity_type == "method"
    assert entities[0].name == "Person"
    assert entities[0].return_type == ""


def test_parse_field_javadoc_with_constructor_initializer():
    source = """
public class Fraction {
    /**
     * {@link Fraction} representation of 0.
     */
    public static final Fraction ZERO = new Fraction(0, 1);
}
"""

    entities = parse_entities(source)

    assert entities[0].entity_type == "field"
    assert entities[0].name == "ZERO"
    assert entities[0].return_type == "Fraction"
    assert entities[0].code_end_line == entities[0].code_start_line
