from dataclasses import dataclass, field
from typing import Mapping, Any
from types import MappingProxyType
from typing import TypeAlias, Literal
from .tools import ToolCall
from __future__ import annotations # pour que Message.system, Message.user, etc. retournent des instances de Message

# plusieurs interlocuteurs possibles, mais que parmis cette liste
# system pour les messages du debut, context, persona ...
# user bah classique
# assistant pour les réponses du modèle
# tool c'est le resultats des appels tools
Role: TypeAlias = Literal["system", "user", "assistant", "tool"]


# le message c'est néccéssaire pour le stockage des données
# une convversation est une liste de messages
# on créer un mesage avec ("user", "salut")
@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = () # exemple ToolCall("calculator", {"expression": "2+2"})
    tool_name: str | None = None  # que pour role = tool, a voir si on decide de créer une liste possible
    thinking_description: str = "" # pour ne pas perdre la ou le modèle en est dans sa réflexion entre des appels tools

    def __post_init__(self) -> None:
        if self.role == "tool" and not self.tool_name:
            raise ValueError("tool_name must be provided for role 'tool'")
        if self.tool_calls and self.role != "assistant":
            raise ValueError("only assistant messages can carry tool_calls")
        if self.thinking_description and self.role != "assistant":
            raise ValueError("only assistant messages can have a thinking_description")
        # if self.role == "tool" and self.tool_name not_in_list
        #     raise ValueError("tool_name must be a valid tool for role 'tool'")
        # ATTENTION, A NE PAS FAIRE ICI MAIS DANS LE CORE


    # Ces méthodes permettent de faire Message.system("voici un personna")

    @classmethod
    def system(cls, content: str) -> Message:
        return cls("system", content)

    @classmethod
    def user(cls, content: str) -> Message:
        return cls("user", content)

    @classmethod
    def assistant(cls, content: str = "", tool_calls: tuple[ToolCall, ...] = ()) -> Message:
        return cls("assistant", content, tool_calls)

    @classmethod
    def tool(cls, content: str, tool_name: str) -> Message:
        return cls("tool", content, tool_name=tool_name)


@dataclass(frozen=True, slots=True, kw_only=True)
class ChatOptions: # les nones signifient que la valeur par défaut du modèle sera utilisée
    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    num_ctx: int | None = None
    max_tokens: int | None = None
    response_schema: Mapping[str, Any] | None = field(default=None, hash=False) # à définir
    think: bool | None = None

    def __post_init__(self) -> None:
        if self.response_schema is not None:
            object.__setattr__(self, "response_schema", MappingProxyType(dict(self.response_schema)))

@dataclass(frozen=True, slots=True)
class Usage:
    completion_tokens: int
    prompt_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# ATTENTION : différence entre ToolCall et ToolCallRequest, la persitence
# au moment ou le modele fait un appel à un outil, c'est une instance de ToolCallRequest qui est créée
# mais une fois l'appel effectué, c'est une instance de ToolCall qui est persistée 
# et stocké dans l'historique des appels mais dans un message assitance
@dataclass(frozen=True, slots=True)
class ToolCallRequest:
    call: ToolCall