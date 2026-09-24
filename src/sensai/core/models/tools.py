from dataclasses import dataclass, field
from typing import Mapping, Any, Self
from types import MappingProxyType
import re

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")

@dataclass(frozen=True, slots=True)
class ToolCall:
    name: str
    arguments: Mapping[str, Any] = field(default_factory=dict, hash=False)
    id: str | None = None # not always give

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("ToolCall.name must not be empty")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: Mapping[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}}, hash=False
    ) # description JSON des champs atte,dus
    requires_confirmation: bool = False # human in the loop actions sensibles

    def __post_init__(self) -> None:
        if not _NAME_RE.match(self.name):
            raise ValueError(f"ToolSpec.name {self.name!r} must match [A-Za-z0-9_-]+")
        object.__setattr__(self, "parameters", MappingProxyType(dict(self.parameters)))


@dataclass(frozen=True, slots=True)
class ToolResult:
    name: str
    content: str
    is_error: bool = False  # l'erreur est renvoyée au modèle, pas levée

    @classmethod # créer une instance de ToolResult représentant une erreur
    def error(cls, name: str, message: str) -> Self:
        return cls(name, message, is_error=True)

# A FAIRE MAIS PAS ICI, AVANT d'UTILISER LES TOOLS IL FAUT VÉRIFIER QU'ILS EXISTENT ET SONT AUTORISÉS
# pour tool spec et tool call
# en attendant création d'un filtre minimal avec vérification du nom par regex
