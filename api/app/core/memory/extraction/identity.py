"""用户本人身份解析。

记忆抽取先把自然语言中的 self 指代归一到一个稳定的内部实体，
再进入普通实体去重和 Neo4j 写入。这里保留一个保守的规则层：
明确自我声明可以自动处理，带有同事/角色等外部主体限定的名称不自动绑定。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.memory.graph_models import EntityNode

SELF_SURFACE_NAMES = frozenset({"我", "用户", "本人", "自己", "我本人"})
_GENERIC_SELF_NAMES = SELF_SURFACE_NAMES | {"user", "self"}
_NAME_CHARS = r"[A-Za-z\u4e00-\u9fff][A-Za-z0-9_\-·\u4e00-\u9fff]{0,31}"
_INTERROGATIVE_NAME_RE = re.compile(
    r"^(?:什么(?:名字|姓名|称呼)?|啥(?:名字|姓名|称呼)?|谁|"
    r"哪个(?:名字|姓名|人)?|哪位|哪一个)(?:吗|呢|啊|呀)?$",
    flags=re.IGNORECASE,
)
_SELF_IDENTITY_QUESTION_PATTERNS = (
    re.compile(
        r"(?:我|本人|用户)(?:叫|是)\s*(?:什么(?:名字)?|啥(?:名字)?|谁|哪个|哪位)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:我|本人|用户)(?:的)?(?:名字|姓名|称呼)\s*(?:是|叫)?\s*"
        r"(?:什么|啥|哪个|哪位)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        r"(?:记得|知道|告诉).{0,12}(?:我|本人|用户)(?:的)?"
        r"(?:名字|姓名|称呼|叫什么|是谁)",
        flags=re.IGNORECASE,
    ),
)


@dataclass(frozen=True)
class IdentitySignals:
    """从原文中提取出的低风险身份声明。"""

    current_names: tuple[str, ...] = ()
    alias_names: tuple[str, ...] = ()
    invalid_names: tuple[str, ...] = ()

    @property
    def explicit_self(self) -> bool:
        return bool(self.current_names or self.alias_names or self.invalid_names)

    @property
    def all_names(self) -> frozenset[str]:
        return frozenset((*self.current_names, *self.alias_names))


def _clean_name(value: str) -> str:
    value = (value or "").strip()
    value = re.split(
        r"[，。！？；;、,\.\n]|(?:并且|然后|但是|现在|以后|希望|想要)", value, 1
    )[0]
    value = re.sub(r"^(?:叫作|叫做|称为|是|为)\s*", "", value).strip()
    if _is_interrogative_name(value):
        return ""
    return value[:32]


def _is_interrogative_name(value: str) -> bool:
    """判断候选是否只是姓名疑问词，而不是可落库的身份名称。"""
    return bool(_INTERROGATIVE_NAME_RE.fullmatch((value or "").strip()))


def _names_after(pattern: str, text: str) -> list[str]:
    names: list[str] = []
    for raw in re.findall(pattern, text, flags=re.IGNORECASE):
        name = _clean_name(raw)
        if name:
            names.append(name)
    return names


def extract_identity_signals(text: str) -> IdentitySignals:
    """提取明确的自称、别名、改名和否定声明。

    这是安全门槛而不是完整 NER。复杂或上下文不足的表达交给后续审查，
    不在这里猜测真实身份。
    """
    text = (text or "").strip()
    if not text:
        return IdentitySignals()

    invalid = _names_after(
        rf"(?:我|本人)(?:不叫|不是|名字不是|不再叫)\s*({_NAME_CHARS})", text
    )
    historical = _names_after(
        rf"(?:我|本人)(?:以前|曾经|原来)(?:叫|称为|是)\s*({_NAME_CHARS})", text
    )
    current = _names_after(
        rf"(?:我|本人)(?:(?:现在|如今|以后)\s*)?(?:叫|名字叫|名字是|姓名是|称为|自称(?:为|是)?)\s*({_NAME_CHARS})",
        text,
    )
    current.extend(
        _names_after(
            rf"(?:现在|如今|以后)(?:希望|想要)?(?:叫|称为|是)\s*({_NAME_CHARS})",
            text,
        )
    )
    aliases = _names_after(
        rf"(?:大家|朋友|别人|平时|同事)\s*(?:都)?叫我\s*({_NAME_CHARS})", text
    )
    aliases.extend(_names_after(rf"叫我\s*({_NAME_CHARS})", text))
    aliases.extend(_names_after(rf"({_NAME_CHARS})就是我", text))

    invalid_set = {name.casefold() for name in invalid}
    current = [name for name in current if name.casefold() not in invalid_set]
    aliases = [name for name in aliases if name.casefold() not in invalid_set]

    def unique(names: list[str]) -> tuple[str, ...]:
        seen: set[str] = set()
        out: list[str] = []
        for name in names:
            key = name.casefold()
            if key not in seen and name:
                seen.add(key)
                out.append(name)
        return tuple(out)

    return IdentitySignals(
        current_names=unique(current),
        alias_names=unique([*historical, *aliases]),
        invalid_names=unique(invalid),
    )


def is_self_identity_question(text: str) -> bool:
    """判断文本是否仅在询问用户身份，而没有提供新的姓名声明。"""
    text = (text or "").strip()
    if not text or extract_identity_signals(text).current_names:
        return False
    text = re.sub(
        r"^(?:(?:请问|请告诉我|告诉我|麻烦告诉我)|"
        r"(?:你|您)(?:还)?(?:知道|记得)|(?:你|您)?(?:能|可以|能否)告诉我)"
        r"[，,:：\s]*",
        "",
        text,
    )
    clauses = [item.strip() for item in re.split(r"[，,。；;！？!?]", text) if item.strip()]
    if len(clauses) != 1:
        return False
    return any(pattern.search(clauses[0]) for pattern in _SELF_IDENTITY_QUESTION_PATTERNS)


def self_identity_key(user_id: str) -> str:
    """返回每个用户唯一且不随展示名称变化的 self 键。"""
    return f"self:{user_id}"


def _is_external_name_context(text: str, name: str) -> bool:
    if not name or not text:
        return False
    return bool(
        re.search(
            rf"(?:我的|我认识的|小说中的|书中的|电影中的|角色|同事|朋友|同学|"
            rf"妹妹|哥哥|姐姐|弟弟|爸爸|妈妈|父亲|母亲|老师|领导)\s*{re.escape(name)}",
            text,
        )
    )


def should_resolve_to_self(
    *,
    text: str,
    entity: EntityNode,
    signals: IdentitySignals,
    known_names: set[str],
) -> bool:
    """判断实体是否可以安全绑定到当前用户本人。"""
    name = (entity.name or "").strip()
    if not name:
        return False
    if name.casefold() in {item.casefold() for item in signals.invalid_names}:
        return False
    if name in SELF_SURFACE_NAMES:
        return True
    if name in signals.all_names:
        return not _is_external_name_context(text, name)
    if name.casefold() in {item.casefold() for item in known_names}:
        return not _is_external_name_context(text, name)
    return False


async def normalize_entity_pool(
    *,
    repo,
    user_id: str,
    text: str,
    entities: list[EntityNode],
) -> tuple[list[EntityNode], dict[str, str]]:
    """将当前批次中明确指向用户本人的实体合并到 self 节点。

    返回规范化实体和旧 id → self id 的重定向表；调用方需要同时重定向
    MENTIONS、RELATION 和 INVOLVES 的待写入边。
    """
    signals = extract_identity_signals(text)
    existing = await repo.get_self_entity(user_id, self_identity_key(user_id))
    # 兼容尚未迁移的图：用户第一次明确声明姓名时，优先复用同名的生命体
    # 节点，避免在旧的“林舟/林夕”节点旁再创建一个新的 self。
    if existing is None:
        get_by_name = getattr(repo, "get_entity_by_name", None)
        for candidate_name in reversed(signals.current_names):
            if get_by_name is None:
                break
            candidate = await get_by_name(user_id, candidate_name)
            if candidate and candidate.get("type") == "生命体":
                existing = candidate
                break
    existing_alias_list = list(existing.get("aliases") or []) if existing else []
    existing_aliases = set(existing_alias_list)
    existing_name = (existing.get("name") or "") if existing else ""
    known_names = {
        name for name in existing_aliases if not _is_interrogative_name(name)
    }
    if existing_name and not _is_interrogative_name(existing_name):
        known_names.add(existing_name)
    known_names |= set(SELF_SURFACE_NAMES)

    has_self_candidate = any(
        should_resolve_to_self(
            text=text, entity=entity, signals=signals, known_names=known_names
        )
        for entity in entities
    )
    if not has_self_candidate and not signals.explicit_self:
        return entities, {}

    existing_id = existing.get("id") if existing else None
    self_id = existing_id or self_identity_key(user_id)
    current_name = next(reversed(signals.current_names), None)
    invalid_names = {name.casefold() for name in signals.invalid_names}
    if not current_name or current_name.casefold() in {
        item.casefold() for item in _GENERIC_SELF_NAMES
    }:
        if existing_name and not _is_interrogative_name(existing_name):
            current_name = existing_name
        else:
            recoverable_aliases = [
                name
                for name in existing_alias_list
                if name
                and name.casefold()
                not in {item.casefold() for item in _GENERIC_SELF_NAMES}
                and not _is_interrogative_name(name)
            ]
            current_name = (
                recoverable_aliases[0] if len(recoverable_aliases) == 1 else "用户"
            )
    if current_name.casefold() in invalid_names or _is_interrogative_name(current_name):
        current_name = "用户"

    aliases = set(existing_aliases)
    aliases.update(SELF_SURFACE_NAMES)
    aliases.update(signals.alias_names)
    aliases.update(signals.current_names[:-1])
    if (
        existing_name
        and existing_name.casefold() != current_name.casefold()
        and not _is_interrogative_name(existing_name)
    ):
        aliases.add(existing_name)
    aliases = {
        name
        for name in aliases
        if name
        and name.casefold() != current_name.casefold()
        and name.casefold() not in invalid_names
        and not _is_interrogative_name(name)
    }

    self_entity = EntityNode(
        id=self_id,
        user_id=user_id,
        name=current_name,
        type="生命体",
        description=(existing.get("description") or "") if existing else "用户本人",
        aliases=sorted(aliases),
        identity_key=self_identity_key(user_id),
        is_self=True,
        importance=float(existing.get("importance", 0.5) or 0.5) if existing else 0.5,
        confidence=float(existing.get("confidence", 0.8) or 0.8) if existing else 0.8,
    )

    redirect: dict[str, str] = {}
    normalized: list[EntityNode] = [self_entity]
    for entity in entities:
        if should_resolve_to_self(
            text=text, entity=entity, signals=signals, known_names=known_names
        ):
            redirect[entity.id] = self_id
            self_entity.description = max(
                self_entity.description, entity.description or "", key=len
            )
            self_entity.importance = max(self_entity.importance, entity.importance)
            self_entity.confidence = max(self_entity.confidence, entity.confidence)
        else:
            normalized.append(entity)

    return normalized, redirect


__all__ = [
    "IdentitySignals",
    "extract_identity_signals",
    "is_self_identity_question",
    "normalize_entity_pool",
    "self_identity_key",
    "should_resolve_to_self",
]
