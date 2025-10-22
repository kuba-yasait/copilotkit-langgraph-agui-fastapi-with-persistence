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
    
    # Log response
    duration = time.time() - start_time
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
