"""
This serves the "sample_agent" agent. This is an example of self-hosting an agent
through our FastAPI integration. However, you can also host in LangGraph platform.
"""

import os
import sys
import warnings
from dotenv import load_dotenv
load_dotenv() # pylint: disable=wrong-import-position

# Wycisz warningi Pydantic
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")

from fastapi import FastAPI, Request
import uvicorn
from copilotkit import LangGraphAGUIAgent
from sample_agent.agent import graph
from ag_ui_langgraph import add_langgraph_fastapi_endpoint
import time

app = FastAPI()

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

add_langgraph_fastapi_endpoint(
    app=app,
    agent=LangGraphAGUIAgent(
        name="sample_agent",
        description="An example agent to use as a starting point for your own agent.",
        graph=graph
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
