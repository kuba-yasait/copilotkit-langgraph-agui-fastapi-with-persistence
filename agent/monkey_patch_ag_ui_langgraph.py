"""
Monkey patch to fix the regeneration logic in ag-ui-langgraph

This patch disables the automatic regeneration that caused the "Message ID not found in history" error,
keeps only the explicit regeneration when requested, and allows LangGraph to manage natural recovery through checkpoints.

Source: https://gist.github.com/jgabriellima/80b5cdd2b022f5f5cd1e3fcfc018b003
"""
import logging
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from ag_ui.core import RunAgentInput

logger = logging.getLogger(__name__)

# Store original methods for reference
_original_prepare_stream = None
_original_prepare_regenerate_stream = None

def monkey_patch_ag_ui_langgraph():
    """
    Apply monkey patch directly to the ag-ui-langgraph library
    """
    global _original_prepare_stream, _original_prepare_regenerate_stream
    
    try:
        from ag_ui_langgraph.agent import LangGraphAgent
        
        # Store original methods
        _original_prepare_stream = LangGraphAgent.prepare_stream
        _original_prepare_regenerate_stream = LangGraphAgent.prepare_regenerate_stream
        
        # Apply our patches
        LangGraphAgent.prepare_stream = patched_prepare_stream
        LangGraphAgent.prepare_regenerate_stream = patched_prepare_regenerate_stream
        
        logger.info("Monkey patch applied to ag-ui-langgraph")
        
    except ImportError as e:
        logger.error(f"Monkey patch failed: Could not import ag_ui_langgraph.agent: {e}")
        raise

async def patched_prepare_stream(self, input: RunAgentInput, agent_state, config: RunnableConfig):
    """
    Fixed version of prepare_stream that does not force automatic regeneration
    """
    logger.info(f"PATCHED prepare_stream called for thread {input.thread_id}")
    
    state_input = input.state or {}
    messages = input.messages or []
    forwarded_props = input.forwarded_props or {}
    thread_id = input.thread_id
    
    state_input["messages"] = agent_state.values.get("messages", [])
    self.active_run["current_graph_state"] = agent_state.values.copy()
    
    # Import the utility function
    from ag_ui_langgraph.utils import agui_messages_to_langchain
    langchain_messages = agui_messages_to_langchain(messages)
    
    state = self.langgraph_default_merge_state(state_input, langchain_messages, input)
    self.active_run["current_graph_state"].update(state)
    config["configurable"]["thread_id"] = thread_id
    
    interrupts = agent_state.tasks[0].interrupts if agent_state.tasks and len(agent_state.tasks) > 0 else []
    has_active_interrupts = len(interrupts) > 0
    resume_input = forwarded_props.get('command', {}).get('resume', None)
    
    self.active_run["schema_keys"] = self.get_schema_keys(config)
    
    # FIX: Only regenerate if explicitly requested
    is_explicit_regeneration = (
        forwarded_props and 
        forwarded_props.get('command', {}).get('resume') is not None
    )
    
    logger.info(f"PATCH: is_explicit_regeneration = {is_explicit_regeneration}")
    logger.info(f"PATCH: agent_state messages count = {len(agent_state.values.get('messages', []))}")
    logger.info(f"PATCH: input messages count = {len(langchain_messages)}")
    
    if is_explicit_regeneration:
        logger.info(f"PATCH: Processing explicit regeneration for thread {thread_id}")
        from langchain_core.messages import SystemMessage
        non_system_messages = [msg for msg in langchain_messages if not isinstance(msg, SystemMessage)]
        if len(agent_state.values.get("messages", [])) > len(non_system_messages):
            last_user_message = None
            for i in range(len(langchain_messages) - 1, -1, -1):
                if isinstance(langchain_messages[i], HumanMessage):
                    last_user_message = langchain_messages[i]
                    break
            
            if last_user_message:
                logger.info(f"PATCH: Starting regenerate_stream for message {last_user_message.id}")
                return await patched_prepare_regenerate_stream(
                    self=self,
                    input=input,
                    message_checkpoint=last_user_message,
                    config=config
                )
    else:
        logger.info(f"PATCH: Using normal flow for thread {thread_id} (no automatic regeneration)")
    
    events_to_dispatch = []
    if has_active_interrupts and not resume_input:
        from ag_ui.core import EventType, RunStartedEvent, RunFinishedEvent, CustomEvent
        from ag_ui_langgraph.types import LangGraphEventTypes
        from ag_ui_langgraph.utils import json_safe_stringify
        
        events_to_dispatch.append(
            RunStartedEvent(type=EventType.RUN_STARTED, thread_id=thread_id, run_id=self.active_run["id"])
        )
        
        for interrupt in interrupts:
            events_to_dispatch.append(
                CustomEvent(
                    type=EventType.CUSTOM,
                    name=LangGraphEventTypes.OnInterrupt.value,
                    value=json_safe_stringify(interrupt.value) if not isinstance(interrupt.value, str) else interrupt.value,
                    raw_event=interrupt,
                )
            )
        
        events_to_dispatch.append(
            RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=thread_id, run_id=self.active_run["id"])
        )
        return {
            "stream": None,
            "state": None,
            "config": None,
            "events_to_dispatch": events_to_dispatch,
        }
    
    if self.active_run["mode"] == "continue":
        await self.graph.aupdate_state(config, state, as_node=self.active_run.get("node_name"))
    
    if resume_input:
        from langgraph.types import Command
        stream_input = Command(resume=resume_input)
    else:
        from ag_ui_langgraph.utils import get_stream_payload_input
        payload_input = get_stream_payload_input(
            mode=self.active_run["mode"],
            state=state,
            schema_keys=self.active_run["schema_keys"],
        )
        stream_input = {**forwarded_props, **payload_input} if payload_input else None
    
    subgraphs_stream_enabled = input.forwarded_props.get('stream_subgraphs') if input.forwarded_props else False
    
    kwargs = self.get_stream_kwargs(
        input=stream_input,
        config=config,
        subgraphs=bool(subgraphs_stream_enabled),
        version="v2",
    )
    
    stream = self.graph.astream_events(**kwargs)
    
    return {
        "stream": stream,
        "state": state,
        "config": config
    }

async def patched_prepare_regenerate_stream(self, input: RunAgentInput, message_checkpoint: HumanMessage, config: RunnableConfig):
    """
    Fixed version of prepare_regenerate_stream with better error handling
    """
    tools = input.tools or []
    thread_id = input.thread_id
    
    logger.info(f"PATCHED prepare_regenerate_stream called for thread {thread_id}, message {message_checkpoint.id}")
    
    try:
        time_travel_checkpoint = await self.get_checkpoint_before_message(message_checkpoint.id, thread_id)
        if time_travel_checkpoint is None:
            logger.warning(f"PATCH: No checkpoint found for message {message_checkpoint.id}, falling back to normal flow")
            return None
    except ValueError as e:
        if "Message ID not found in history" in str(e):
            logger.warning(f"PATCH: Message {message_checkpoint.id} not found in history, falling back to normal flow")
            return None
        else:
            logger.error(f"PATCH: Unexpected error in prepare_regenerate_stream: {e}")
            raise
    
    logger.info(f"PATCH: Found checkpoint for message {message_checkpoint.id}, proceeding with regeneration")
    
    fork = await self.graph.aupdate_state(
        time_travel_checkpoint.config,
        time_travel_checkpoint.values,
        as_node=time_travel_checkpoint.next[0] if time_travel_checkpoint.next else "__start__"
    )
    
    stream_input = self.langgraph_default_merge_state(time_travel_checkpoint.values, [message_checkpoint], input)
    subgraphs_stream_enabled = input.forwarded_props.get('stream_subgraphs') if input.forwarded_props else False
    
    kwargs = self.get_stream_kwargs(
        input=stream_input,
        fork=fork,
        subgraphs=bool(subgraphs_stream_enabled),
        version="v2",
    )
    stream = self.graph.astream_events(**kwargs)
    
    return {
        "stream": stream,
        "state": time_travel_checkpoint.values,
        "config": config
    }

def apply_monkey_patch():
    """
    Apply the monkey patch directly to the library
    """
    monkey_patch_ag_ui_langgraph()

