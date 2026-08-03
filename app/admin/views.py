from sqladmin import ModelView

from app.models.conversation import Conversation
from app.models.user_state import UserState
from app.models.pending_message import PendingMessage
from app.models.config import AppConfig
from app.models.brain_turn import BrainTurn
from app.models.knowledge import Knowledge
from app.models.playbook import Playbook as PlaybookModel


class ConversationAdmin(ModelView, model=Conversation):
    name = "Conversation"
    name_plural = "Conversations"
    icon = "fa-solid fa-comments"
    category = "Data"

    column_list = [
        Conversation.id,
        Conversation.instagram_user_id,
        Conversation.role,
        Conversation.lead_score,
        Conversation.ai_model,
        Conversation.token_cost,
        Conversation.created_at,
    ]
    column_details_list = [
        Conversation.id,
        Conversation.instagram_user_id,
        Conversation.role,
        Conversation.content,
        Conversation.lead_score,
        Conversation.contact_tags,
        Conversation.token_cost,
        Conversation.prompt_tokens,
        Conversation.completion_tokens,
        Conversation.ai_model,
        Conversation.created_at,
    ]
    column_searchable_list = [Conversation.instagram_user_id, Conversation.role]
    column_sortable_list = [
        Conversation.id,
        Conversation.instagram_user_id,
        Conversation.created_at,
        Conversation.lead_score,
    ]
    column_default_sort = ("created_at", True)
    page_size = 50

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True


class UserStateAdmin(ModelView, model=UserState):
    name = "User State"
    name_plural = "User States"
    icon = "fa-solid fa-user"
    category = "Data"

    column_list = [
        UserState.instagram_user_id,
        UserState.is_ai_paused,
        UserState.paused_at,
        UserState.pause_reason,
    ]
    column_searchable_list = [UserState.instagram_user_id]
    column_sortable_list = [
        UserState.instagram_user_id,
        UserState.is_ai_paused,
        UserState.paused_at,
    ]

    can_create = False
    can_edit = True
    can_delete = True
    can_view_details = True

    form_columns = [
        UserState.is_ai_paused,
        UserState.paused_at,
        UserState.pause_reason,
    ]


class PendingMessageAdmin(ModelView, model=PendingMessage):
    name = "Pending Message"
    name_plural = "Pending Messages"
    icon = "fa-solid fa-envelope-open"
    category = "Data"

    column_list = [
        PendingMessage.id,
        PendingMessage.instagram_user_id,
        PendingMessage.manychat_contact_id,
        PendingMessage.received_at,
        PendingMessage.locked_at,
        PendingMessage.processed_at,
    ]
    column_details_list = [
        PendingMessage.id,
        PendingMessage.instagram_user_id,
        PendingMessage.manychat_contact_id,
        PendingMessage.content,
        PendingMessage.received_at,
        PendingMessage.locked_at,
        PendingMessage.processed_at,
    ]
    column_searchable_list = [PendingMessage.instagram_user_id, PendingMessage.manychat_contact_id]
    column_sortable_list = [
        PendingMessage.id,
        PendingMessage.received_at,
        PendingMessage.processed_at,
    ]
    column_default_sort = ("received_at", True)

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True


class BrainTurnAdmin(ModelView, model=BrainTurn):
    """Read-only turn traces. `/admin/shadow` is the review surface; this is for
    filtering and drilling into the raw JSON."""
    name = "Brain Turn"
    name_plural = "Brain Turns"
    icon = "fa-solid fa-diagram-project"
    category = "Ops"

    column_list = [BrainTurn.created_at, BrainTurn.instagram_user_id, BrainTurn.shadow,
                   BrainTurn.intent, BrainTurn.mode, BrainTurn.uncertainty_score,
                   BrainTurn.pause, BrainTurn.token_cost]
    column_details_list = [
        BrainTurn.id, BrainTurn.created_at, BrainTurn.instagram_user_id,
        BrainTurn.brain_version, BrainTurn.shadow, BrainTurn.lead_message,
        BrainTurn.intent, BrainTurn.intent_certainty, BrainTurn.stage, BrainTurn.mode,
        BrainTurn.reason, BrainTurn.action, BrainTurn.question_asked,
        BrainTurn.reply, BrainTurn.live_reply, BrainTurn.violations,
        BrainTurn.uncertainty_score, BrainTurn.pause, BrainTurn.pause_reason,
        BrainTurn.qualified, BrainTurn.trace, BrainTurn.usage, BrainTurn.token_cost,
    ]
    column_searchable_list = [BrainTurn.instagram_user_id, BrainTurn.intent,
                              BrainTurn.mode, BrainTurn.reply]
    column_sortable_list = [BrainTurn.created_at, BrainTurn.mode, BrainTurn.intent,
                            BrainTurn.uncertainty_score, BrainTurn.token_cost]
    column_default_sort = [(BrainTurn.created_at, True)]

    can_create = False
    can_edit = False
    can_delete = True
    can_view_details = True
    page_size = 50


class KnowledgeAdmin(ModelView, model=Knowledge):
    """Sonia's approved substance. Adding a row here is how she teaches the bot
    something new: the writer may not state a fertility or positioning claim
    that is not retrieved from this table, so an empty table means a bot that
    answers nothing rather than one that invents."""
    name = "Knowledge"
    name_plural = "Knowledge"
    icon = "fa-solid fa-book"
    category = "Config"

    column_list = [Knowledge.kind, Knowledge.topic, Knowledge.language,
                   Knowledge.active, Knowledge.updated_at]
    column_details_list = [Knowledge.id, Knowledge.kind, Knowledge.topic,
                           Knowledge.content, Knowledge.triggers, Knowledge.language,
                           Knowledge.source, Knowledge.active, Knowledge.updated_at]
    column_searchable_list = [Knowledge.topic, Knowledge.content]
    column_sortable_list = [Knowledge.kind, Knowledge.topic, Knowledge.active,
                            Knowledge.updated_at]
    column_default_sort = [(Knowledge.kind, False), (Knowledge.topic, False)]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    form_excluded_columns = [Knowledge.updated_at]
    form_widget_args = {
        "content": {"rows": 6},
        # One regex or keyword per line, matched against the lead's message.
        "triggers": {"rows": 6, "style": "font-family: monospace; font-size: 0.85rem;"},
    }


class AppConfigAdmin(ModelView, model=AppConfig):
    name = "App Config"
    name_plural = "App Configs"
    icon = "fa-solid fa-gear"
    category = "Config"

    column_list = [AppConfig.key, AppConfig.updated_at]
    column_details_list = [AppConfig.key, AppConfig.value, AppConfig.updated_at]
    column_searchable_list = [AppConfig.key]
    column_sortable_list = [AppConfig.key, AppConfig.updated_at]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    form_include_pk = True
    form_excluded_columns = [AppConfig.updated_at]
    form_widget_args = {
        "value": {"rows": 10, "style": "font-family: monospace; font-size: 0.85rem;"},
    }


class PlaybookAdmin(ModelView, model=PlaybookModel):
    """The Conversation Playbook Library, Part 4 of the Operating Manual.

    Sonia's own words: "The biggest improvements going forward will come from
    building the Conversation Playbook Library with real, edited conversations."
    This view is that workflow. She reviews a conversation, edits the reply, and
    pastes it into `examples`; the next matching turn learns from it.

    Anything sourced `DRAFT - needs Sonia` was written without prior art and is
    waiting to be replaced. Sort by `source` to find them.
    """
    name = "Playbook"
    name_plural = "Playbooks"
    icon = "fa-solid fa-comments"
    category = "Config"

    column_list = [PlaybookModel.slug, PlaybookModel.mode, PlaybookModel.title,
                   PlaybookModel.source, PlaybookModel.active, PlaybookModel.updated_at]
    column_details_list = [
        PlaybookModel.id, PlaybookModel.slug, PlaybookModel.title, PlaybookModel.mode,
        PlaybookModel.intents, PlaybookModel.stages, PlaybookModel.triggers,
        PlaybookModel.language, PlaybookModel.situation, PlaybookModel.goal,
        PlaybookModel.emotional_outcome, PlaybookModel.communication_priorities,
        PlaybookModel.mistakes_to_avoid, PlaybookModel.examples,
        PlaybookModel.conversation_state, PlaybookModel.success_criteria,
        PlaybookModel.information_that_matters, PlaybookModel.decision_outcome,
        PlaybookModel.why_this_works, PlaybookModel.source, PlaybookModel.active,
        PlaybookModel.updated_at,
    ]
    column_searchable_list = [PlaybookModel.slug, PlaybookModel.title,
                              PlaybookModel.situation]
    column_sortable_list = [PlaybookModel.mode, PlaybookModel.slug,
                            PlaybookModel.source, PlaybookModel.active]
    column_default_sort = [(PlaybookModel.mode, False), (PlaybookModel.slug, False)]

    can_create = True
    can_edit = True
    can_delete = True
    can_view_details = True

    form_excluded_columns = [PlaybookModel.updated_at]
    _lines = {"rows": 4, "style": "font-family: monospace; font-size: 0.85rem;"}
    form_widget_args = {
        # One value per line for the list-shaped columns.
        "intents": _lines,
        "stages": _lines,
        "triggers": {"rows": 6, "style": "font-family: monospace; font-size: 0.85rem;"},
        "communication_priorities": _lines,
        "mistakes_to_avoid": _lines,
        "situation": {"rows": 3},
        "goal": {"rows": 2},
        "examples": {"rows": 18, "style": "font-family: monospace; font-size: 0.8rem;"},
    }
