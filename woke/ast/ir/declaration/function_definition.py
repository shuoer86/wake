from __future__ import annotations

import re
from typing import TYPE_CHECKING, List, Optional, Tuple, Union

from ..meta.modifier_invocation import ModifierInvocation
from ..meta.override_specifier import OverrideSpecifier
from ..reference_resolver import CallbackParams
from ..statement.block import Block
from .abc import DeclarationAbc

if TYPE_CHECKING:
    from .contract_definition import ContractDefinition
    from .variable_declaration import VariableDeclaration
    from ..meta.source_unit import SourceUnit

from woke.ast.enums import FunctionKind, StateMutability, Visibility
from woke.ast.ir.abc import IrAbc
from woke.ast.ir.meta.parameter_list import ParameterList
from woke.ast.ir.meta.structured_documentation import StructuredDocumentation
from woke.ast.ir.utils import IrInitTuple, lazy_property
from woke.ast.nodes import AstNodeId, SolcFunctionDefinition


class FunctionDefinition(DeclarationAbc):
    _ast_node: SolcFunctionDefinition
    _parent: Union[ContractDefinition, SourceUnit]
    _child_functions: List[Union[FunctionDefinition, VariableDeclaration]]

    __implemented: bool
    __kind: FunctionKind
    __modifiers: List[ModifierInvocation]
    __parameters: ParameterList
    __return_parameters: ParameterList
    # __scope
    __state_mutability: StateMutability
    __virtual: bool
    __visibility: Visibility
    __base_functions: Optional[List[AstNodeId]]
    __documentation: Optional[StructuredDocumentation]
    __function_selector: Optional[str]
    __body: Optional[Block]
    __overrides: Optional[OverrideSpecifier]

    def __init__(
        self, init: IrInitTuple, function: SolcFunctionDefinition, parent: IrAbc
    ):
        super().__init__(init, function, parent)
        self._child_functions = []

        self.__implemented = function.implemented
        self.__kind = function.kind
        self.__modifiers = [
            ModifierInvocation(init, modifier, self) for modifier in function.modifiers
        ]
        self.__parameters = ParameterList(init, function.parameters, self)
        self.__return_parameters = ParameterList(init, function.return_parameters, self)
        # self.__scope = function.scope
        self.__state_mutability = function.state_mutability
        self.__virtual = function.virtual
        self.__visibility = function.visibility
        self.__base_functions = (
            list(function.base_functions) if function.base_functions else None
        )
        self.__documentation = (
            StructuredDocumentation(init, function.documentation, self)
            if function.documentation
            else None
        )
        self.__function_selector = function.function_selector
        self.__body = Block(init, function.body, self) if function.body else None
        self.__overrides = (
            OverrideSpecifier(init, function.overrides, self)
            if function.overrides
            else None
        )
        self._reference_resolver.register_post_process_callback(self.__post_process)

    def __post_process(self, callback_params: CallbackParams):
        if self.base_functions is not None:
            for base_function in self.base_functions:
                base_function._child_functions.append(self)

    def _parse_name_location(self) -> Tuple[int, int]:
        IDENTIFIER = r"[a-zA-Z$_][a-zA-Z0-9$_]*"
        FUNCTION_RE = re.compile(
            r"^\s*function\s+(?P<name>{identifier})".format(
                identifier=IDENTIFIER
            ).encode("utf-8")
        )

        byte_start = self._ast_node.src.byte_offset
        match = FUNCTION_RE.match(self._source)
        assert match
        return byte_start + match.start("name"), byte_start + match.end("name")

    @property
    def parent(self) -> Union[ContractDefinition, SourceUnit]:
        return self._parent

    @lazy_property
    def canonical_name(self) -> str:
        from .contract_definition import ContractDefinition

        if isinstance(self._parent, ContractDefinition):
            return f"{self._parent.canonical_name}.{self._name}"
        return self.name

    @property
    def implemented(self) -> bool:
        return self.__implemented

    @property
    def kind(self) -> FunctionKind:
        return self.__kind

    @property
    def modifiers(self) -> Tuple[ModifierInvocation]:
        return tuple(self.__modifiers)

    @property
    def parameters(self) -> ParameterList:
        return self.__parameters

    @property
    def return_parameters(self) -> ParameterList:
        return self.__return_parameters

    @property
    def state_mutability(self) -> StateMutability:
        return self.__state_mutability

    @property
    def virtual(self) -> bool:
        return self.__virtual

    @property
    def visibility(self) -> Visibility:
        return self.__visibility

    @property
    def base_functions(self) -> Optional[Tuple[FunctionDefinition]]:
        if self.__base_functions is None:
            return None
        base_functions = []
        for base_function_id in self.__base_functions:
            base_function = self._reference_resolver.resolve_node(
                base_function_id, self._cu_hash
            )
            assert isinstance(base_function, FunctionDefinition)
            base_functions.append(base_function)
        return tuple(base_functions)

    @property
    def child_functions(self) -> Tuple[Union[FunctionDefinition, VariableDeclaration]]:
        return tuple(self._child_functions)

    @property
    def documentation(self) -> Optional[StructuredDocumentation]:
        return self.__documentation

    @property
    def function_selector(self) -> Optional[str]:
        return self.__function_selector

    @property
    def body(self) -> Optional[Block]:
        return self.__body

    @property
    def overrides(self) -> Optional[OverrideSpecifier]:
        return self.__overrides
