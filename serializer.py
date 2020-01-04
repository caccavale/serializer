from collections import ChainMap
from dataclasses import dataclass
from typing import Any
from typing import Dict
from typing import Union

# TODO: abstract compatibility guard `getattr(field_type, "__origin__", None)` away.


def serializer(schema):
    """ Public class factory for creating serializers with distinct schema. """
    return type(f"_Serializable[{schema}]", (_Serializable,), {'_schema': schema})


def _fields_to_json(j):
    """ Recursively transform j into something which is JSON.dumps-able. """
    if type(j) in (str, int, bool):
        return j

    if type(j) in (list, tuple):
        return [_fields_to_json(element) for element in j]

    if type(j) is dict:
        assert all(isinstance(k, str) for k in j)
        return {k: _fields_to_json(v) for k, v in j.items()}

    return j.to_json()


def _to_json_with_match(schema, obj):
    """ Recursively transform obj into JSON-able according to a schema. """
    if isinstance(schema, (list, tuple)):
        return [_to_json_with_match(sub_schema, obj) for sub_schema in schema]

    # If a schema has a string in it,
    if isinstance(schema, str):
        # And that string has an annotation on the serializer obj.
        # Then return the JSON-able representation of obj.`string`
        if schema in getattr(obj, "__annotations__", {}):
            return _fields_to_json(getattr(obj, schema))
        return schema  # Non-field strings are literals

    if isinstance(schema, (int, bool)):
        return schema

    raise TypeError(f"_to_json_with_match called with some jank: {schema}")


def _field_from_json(j, field_type):
    """ Recursively convert j from JSON-able type to Type[field_type]. """
    if field_type in (str, int, bool):
        return j

    # Hack for compatibility with 3.6 and 3.8
    if str(getattr(field_type, "__origin__", None)).split('.')[-1] == "Literal":
        args = getattr(field_type, "__values__", None) or getattr(field_type, "__args__", None)
        if j in args:
            return j
        raise TypeError(f"_field_from_json {j} did not match: {field_type}")

    if getattr(field_type, "__origin__", None) is Union:
        for union_type in field_type.__args__:
            try:
                return _field_from_json(j, union_type)
            except:
                pass
        raise TypeError(f"_field_from_json {j} did not match any union type: {field_type}")

    if getattr(field_type, "__origin__", None) is list:
        return [_field_from_json(sub_j, field_type.__args__[0]) for sub_j in j]

    if getattr(field_type, "__origin__", None) is tuple:
        assert len(j) == len(field_type.__args__)
        return (_field_from_json(sub_j, sub_field_type) for
                sub_j, sub_field_type in zip(j, field_type.__args__))

    if getattr(field_type, "__origin__", None) is dict:
        assert False
        # assert all(isinstance(k, str) for k in j)
        # return {k: _fields_to_json(v) for k, v in j.items()}

    return field_type.from_json(j)


def _from_json_with_match(j, schema, fields) -> Dict[str, Any]:
    """ Recursively convert j according to schema, binding any fields. """
    if isinstance(schema, (list, tuple)):
        return dict(ChainMap(*[_from_json_with_match(sub_j, sub_schema, fields) for sub_j, sub_schema in zip(j, schema)]))

    if isinstance(schema, str):
        if schema in fields:
            return {schema: _field_from_json(j, fields[schema])}
        if schema == j:
            return {}
        raise TypeError(
            f"_from_json_with_match string literal did not match: {schema} != {j}")

    if isinstance(schema, (int, bool)):
        return {}

    raise TypeError(f"_from_json_with_match called with some jank: {schema}")


class _SerializableMeta(type):
    """
    A meta-class for dynamically applying dataclass to _Serializable.
    This helps create a default constructor for field binding.
    """
    def __new__(meta, name, bases, dct):
        return dataclass(super().__new__(meta, name, bases, dct))


class _Serializable(metaclass=_SerializableMeta):
    @classmethod
    def from_json(cls, j):
        return cls(**_from_json_with_match(j, cls._schema, getattr(cls, "__annotations__", {})))

    def to_json(self):
        return _to_json_with_match(self._schema, self)
