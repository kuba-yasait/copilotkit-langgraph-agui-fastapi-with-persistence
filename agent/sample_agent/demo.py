"""
This serves the "sample_agent" agent. This is an example of self-hosting an agent
through our FastAPI integration. However, you can also host in LangGraph platform.
"""

import os
import warnings
from contextlib import asynccontextmanager
from dotenv import load_dotenv
load_dotenv() # pylint: disable=wrong-import-position

# Wycisz warningi Pydantic
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from fastapi import FastAPI, Request
import uvicorn
from copilotkit import LangGraphAGUIAgent
from sample_agent.agent import workflow
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
import time

# Apply monkey patch to fix ag-ui-langgraph automatic regeneration bug
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from monkey_patch_ag_ui_langgraph import apply_monkey_patch
apply_monkey_patch()
print("=== Monkey patch applied to ag-ui-langgraph ===", flush=True)

# Global variable to hold the checkpointer and graph
checkpointer_cm = None
graph = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup the async checkpointer."""
    global checkpointer_cm, graph
    
    print("=== Initializing AsyncSqliteSaver ===", flush=True)
    checkpointer_cm = AsyncSqliteSaver.from_conn_string("checkpoints.db")
    async_checkpointer = await checkpointer_cm.__aenter__()
    print("=== Checkpointer initialized ===", flush=True)
    
    graph = workflow.compile(checkpointer=async_checkpointer)
    print("=== Graph compiled with persistent checkpointer ===", flush=True)
    
    yield
    
    # Cleanup
    if checkpointer_cm is not None:
        print("=== Shutting down checkpointer ===", flush=True)
        await checkpointer_cm.__aexit__(None, None, None)

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = time.time()
    
    # Log request
    print(f"--> {request.method} {request.url.path}", flush=True)
    
    # Process request
    response = await call_next(request)
    
    # Log response with more detail for errors
    duration = time.time() - start_time
    if response.status_code >= 400:
        print(f"<-- {request.method} {request.url.path} [{response.status_code}] {duration:.2f}s [ERROR]", flush=True)
    else:
        print(f"<-- {request.method} {request.url.path} [{response.status_code}] {duration:.2f}s", flush=True)
    
    return response

# Lazy graph wrapper that proxies all attribute access to the actual graph
class GraphProxy:
    """Proxy object that defers all attribute/method access to the global graph."""
    
    def __getattr__(self, name):
        """Proxy all attribute access to the compiled graph."""
        if graph is None:
            raise RuntimeError("Graph not initialized. This should not happen after lifespan startup.")
        return getattr(graph, name)
    
    def __call__(self, *args, **kwargs):
        """Proxy calls to the graph."""
        if graph is None:
            raise RuntimeError("Graph not initialized. This should not happen after lifespan startup.")
        return graph(*args, **kwargs)

# Create a proxy instance that will forward all access to the graph once it's initialized
graph_proxy = GraphProxy()

add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="sample_agent",
        description="An example agent to use as a starting point for your own agent.",
        graph=graph_proxy
    ),
    path="/"
)

# Custom endpoint for state loading (workaround for AG-UI bug)
# See PERSISTENCE_WORKAROUND.md for details
from fastapi import HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any

class LoadStateRequest(BaseModel):
    threadId: str

class LoadStateResponse(BaseModel):
    threadId: str
    threadExists: bool
    messages: List[Dict[str, Any]]
    state: Dict[str, Any]

@app.post("/load_state", response_model=LoadStateResponse)
async def load_state(request: LoadStateRequest):
    """
    Custom endpoint to load conversation state from checkpointer.
    
    This is a workaround for CopilotKit AG-UI not properly querying
    the agent for state on loadAgentState operations.
    """
    print(f"[LoadState] Loading state for thread: {request.threadId}", flush=True)
    
    if graph is None:
        raise HTTPException(status_code=500, detail="Graph not initialized")
    
    try:
        # Query the graph for the current state
        config = {"configurable": {"thread_id": request.threadId}}
        state = await graph.aget_state(config)
        
        # Extract messages from state
        messages = []
        if state and state.values and "messages" in state.values:
            for msg in state.values["messages"]:
                # Convert LangChain message format to simple dict
                message_dict = {
                    "id": getattr(msg, "id", f"msg-{len(messages)}"),
                    "role": "user" if msg.type == "human" else "assistant" if msg.type == "ai" else "system",
                    "content": msg.content,
                }
                messages.append(message_dict)
        
        thread_exists = len(messages) > 0
        
        print(f"[LoadState] Found {len(messages)} messages for thread {request.threadId}", flush=True)
        
        return LoadStateResponse(
            threadId=request.threadId,
            threadExists=thread_exists,
            messages=messages,
            state=state.values if state and state.values else {}
        )
    
    except Exception as e:
        print(f"[LoadState] Error loading state: {e}", flush=True)
        # Return empty state on error (thread doesn't exist)
        return LoadStateResponse(
            threadId=request.threadId,
            threadExists=False,
            messages=[],
            state={}
        )

def main():
    """Run the uvicorn server."""
    port = int(os.getenv("PORT", "8123"))
    print(f"Starting agent on port {port}...", flush=True)
    uvicorn.run(
        "sample_agent.demo:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        access_log=False,
        log_level="error",
    )
