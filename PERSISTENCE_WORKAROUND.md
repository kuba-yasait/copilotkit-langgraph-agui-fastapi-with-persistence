# AG-UI State Persistence Workaround

## Problem Summary

CopilotKit Runtime with the AG-UI protocol fails to restore conversation history after page refresh, despite the LangGraph checkpointer correctly persisting data to the database.

**Status:** Known bug tracked in [CopilotKit Issue #2402](https://github.com/CopilotKit/CopilotKit/issues/2402)

---

## Detailed Problem Description

### Failing Use Case

1. **Initial State**: Empty checkpointer database
2. **First Load**: UI generates threadId `a1b2c3d4-e5f6-7890-1234-56789abcdef0`
3. **Load State Query**: 
   - UI → Runtime: `loadAgentState(threadId: "a1b2c3d4-...")`
   - Runtime → UI: `{ threadExists: false, messages: [] }`
   - ❌ **Runtime does NOT query the FastAPI agent**

4. **User Sends Message**: 
   - UI → Runtime → FastAPI: Message sent successfully
   - FastAPI: LangGraph processes message, saves to checkpointer
   - Database: Now contains full conversation history ✅

5. **Agent Responds**: 
   - User sees response in UI ✅
   - Database persists both user message and agent response ✅

6. **Page Refresh**: 
   - UI reloads, keeps same threadId
   - UI → Runtime: `loadAgentState(threadId: "a1b2c3d4-...")`
   - Runtime → UI: `{ threadExists: false, messages: [] }` ❌
   - **Runtime STILL doesn't query FastAPI**
   - Result: Empty chat UI despite history in database

7. **User Sends Another Message**:
   - Runtime has no history in its state
   - FastAPI queries checkpointer and finds history
   - State mismatch causes: `ValueError: Message ID not found in history`

### Root Cause

The `LangGraphHttpAgent` in CopilotKit Runtime doesn't implement proper state loading from the agent's checkpointer. When `loadAgentState` is called:

**Expected Behavior:**
```
UI → Runtime: loadAgentState(threadId)
Runtime → FastAPI: GET/POST request to check state
FastAPI → Checkpointer: Query for threadId
Checkpointer → FastAPI: Return messages + state
FastAPI → Runtime: State data
Runtime → UI: { threadExists: true, messages: [...] }
```

**Actual Behavior:**
```
UI → Runtime: loadAgentState(threadId)
Runtime: "I don't know this thread, so it doesn't exist"
Runtime → UI: { threadExists: false, messages: [] }
```

---

## Proposed Solutions

### Option A1: Runtime Proxy with Main Endpoint ❌ (Attempted, Failed)
Intercept `loadAgentState` in Runtime and call the main FastAPI endpoint (POST /) with threadId to fetch state.

**Why it failed:**
- ❌ AG-UI endpoint returns Server-Sent Events (SSE) format, not plain JSON
- ❌ Endpoint requires full run context with `schema_keys` - causes `KeyError: 'schema_keys'`
- ❌ Endpoint triggers full agent flow instead of simple state query
- ❌ Not designed for "read-only" state loading

**Initial attempt showed:**
```
[agent] KeyError: 'schema_keys'
[ui] Failed to parse AG-UI event: "data: {"ty"... is not valid JSON
```

**Conclusion:** Main AG-UI endpoint cannot be used for state-only queries.

### Option A2: Custom State Endpoint in FastAPI ✅ (Implemented)
Add dedicated `/load_state` endpoint in FastAPI that directly queries the checkpointer, then intercept `loadAgentState` in Runtime.

**Pros:**
- ✅ Works reliably - directly queries checkpointer via `graph.aget_state()`
- ✅ Returns simple JSON (not SSE streaming)
- ✅ No full agent execution - just state lookup
- ✅ Clean separation of concerns
- ✅ Optimized for state loading only

**Cons:**
- Requires FastAPI code changes (1 endpoint added)
- Additional endpoint to maintain
- Still a workaround

**Status:** ✅ **Successfully Implemented and Tested**

### Option A3: Extend LangGraphHttpAgent Class 🔄 (Alternative - Not Implemented)
Create custom class extending `LangGraphHttpAgent` to override state loading behavior.

**Pros:**
- More "proper" integration with CopilotKit
- Potentially reusable for other agents
- Cleaner architecture

**Cons:**
- Requires deeper knowledge of CopilotKit internals
- May break with CopilotKit updates
- More complex to implement and maintain

**Status:** Available as alternative if middleware approach proves insufficient.

### Option B: Migrate to Old API ❌ (Rejected)
Switch back to deprecated `CopilotKitSDK` + `LangGraphAgent` API.

**Pros:**
- Known to work with persistence

**Cons:**
- Uses deprecated API
- Loses AG-UI features (generative UI, etc.)
- Not a forward-compatible solution

### Option C: Wait for Upstream Fix ❌ (Rejected)
Wait for CopilotKit to fix the bug in AG-UI implementation.

**Pros:**
- Proper fix from maintainers
- No workarounds needed

**Cons:**
- Unknown timeline
- Blocks current development
- Issue has been open since Sep 2024

---

## Implementation: Option A2 - Custom State Endpoint

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ UI (Browser)                                                 │
│  ↓ loadAgentState(threadId)                                 │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────────┐
│ Next.js API Route (src/app/api/copilotkit/route.ts)        │
│  1. Detect loadAgentState query                             │
│  2. Call FastAPI: POST /load_state with threadId            │
│  3. Receive JSON response with messages + state             │
│  4. Inject into GraphQL response                            │
└────────────────────┬───────────────────────────────────────┘
                     ↓
┌────────────────────────────────────────────────────────────┐
│ FastAPI Custom Endpoint (agent/sample_agent/demo.py)        │
│  - Dedicated /load_state endpoint                           │
│  - Calls graph.aget_state(threadId) directly               │
│  - Returns plain JSON (not SSE streaming)                   │
│  - Converts LangChain messages to simple dicts              │
└─────────────────────────────────────────────────────────────┘
```

### Key Files

1. **`PERSISTENCE_WORKAROUND.md`** (this file)
   - Documentation of the problem and solution

2. **`src/lib/agent-state-loader.ts`** (new)
   - Utility functions to load state from FastAPI custom endpoint
   - GraphQL query detection
   - JSON response parsing

3. **`src/app/api/copilotkit/route.ts`** (modified)
   - Middleware to intercept `loadAgentState`
   - Calls custom endpoint for state fetching
   - Injection logic for GraphQL response

4. **`agent/sample_agent/demo.py`** (modified)
   - Added `/load_state` FastAPI endpoint
   - Direct checkpointer access via `graph.aget_state()`
   - Returns structured JSON response

### How It Works

1. **Request Interception** (Next.js):
   ```typescript
   // Check if request is loadAgentState
   const body = await req.json();
   if (body.operationName === 'loadAgentState') {
     const threadId = body.variables?.data?.threadId;
     
     // Fetch from custom endpoint
     const state = await loadStateFromAgent(agentUrl, threadId);
     
     // Return enriched response
     return NextResponse.json({
       data: {
         loadAgentState: {
           threadId,
           threadExists: state.messages.length > 0,
           messages: JSON.stringify(state.messages),
           state: JSON.stringify(state.state)
         }
       }
     });
   }
   ```

2. **State Loading** (TypeScript):
   ```typescript
   async function loadStateFromAgent(agentUrl: string, threadId: string) {
     const response = await fetch(`${agentUrl}/load_state`, {
       method: 'POST',
       headers: { 'Content-Type': 'application/json' },
       body: JSON.stringify({ threadId })
     });
     
     const data = await response.json();
     return {
       messages: data.messages || [],
       state: data.state || {},
     };
   }
   ```

3. **Custom Endpoint** (Python/FastAPI):
   ```python
   @app.post("/load_state")
   async def load_state(request: LoadStateRequest):
       config = {"configurable": {"thread_id": request.threadId}}
       state = await graph.aget_state(config)
       
       messages = []
       if state and state.values and "messages" in state.values:
           for msg in state.values["messages"]:
               messages.append({
                   "id": getattr(msg, "id", f"msg-{len(messages)}"),
                   "role": "user" if msg.type == "human" else "assistant",
                   "content": msg.content,
               })
       
       return LoadStateResponse(
           threadId=request.threadId,
           threadExists=len(messages) > 0,
           messages=messages,
           state=state.values if state else {}
       )
   ```

### Testing

Manual test steps:
1. Start app: `npm run dev`
2. Send message: "Hello, what's the weather in Paris?"
3. Verify response appears
4. Check database: `agent/checkpoints.db` should have entries
5. **Refresh page** (F5)
6. Verify: Chat history should load ✅
7. Send another message: "And in London?"
8. Verify: Agent has context from previous messages ✅

---

## Future Migration Path

Once [CopilotKit Issue #2402](https://github.com/CopilotKit/CopilotKit/issues/2402) is fixed:

1. **Remove workaround**:
   - Delete `src/lib/agent-state-loader.ts`
   - Restore `src/app/api/copilotkit/route.ts` to original
   
2. **Update dependencies**:
   ```bash
   npm update @copilotkit/runtime @ag-ui/langgraph
   cd agent && poetry update copilotkit ag-ui-langgraph
   ```

3. **Test without workaround**:
   - Verify persistence works natively
   - Remove this documentation file

---

## Related Links

- [CopilotKit Issue #2402](https://github.com/CopilotKit/CopilotKit/issues/2402) - Original bug report
- [AG-UI Protocol Documentation](https://docs.copilotkit.ai/ag-ui-protocol)
- [LangGraph Checkpointing](https://langchain-ai.github.io/langgraph/how-tos/persistence/)

---

**Last Updated:** 2025-01-22  
**Status:** Workaround Active  
**Author:** CopilotKit User Community

