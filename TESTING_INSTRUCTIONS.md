# Testing Instructions for State Persistence Workaround

## Prerequisites

Ensure the development environment is ready:

```bash
# Terminal 1: Start the full stack
npm run dev

# This will start both:
# - UI (Next.js) on http://localhost:3000
# - Agent (FastAPI) on http://localhost:8123
```

## Test Scenario 1: First Conversation

### Steps:

1. **Open the application**
   - Navigate to http://localhost:3000
   - Open browser DevTools (F12) and go to Console tab

2. **Send first message**
   - Type in chat: "Hello, what's the weather in Paris?"
   - Press Enter

3. **Verify first message works**
   - ✅ Check: Agent responds with weather information
   - ✅ Check: Console shows no errors
   - ✅ Check: FastAPI terminal shows POST request to `/`

4. **Check database**
   ```bash
   # In a new terminal
   cd agent
   sqlite3 checkpoints.db "SELECT COUNT(*) FROM checkpoints;"
   ```
   - ✅ Check: Should return a number > 0

## Test Scenario 2: Page Refresh (Main Test)

### Steps:

1. **Refresh the page**
   - Press F5 or Ctrl+R
   - Watch the Console tab

2. **Expected behavior:**
   - ✅ Console should show:
     ```
     [CopilotKit] Request: loadAgentState
     [CopilotKit] 🔄 Intercepting loadAgentState for thread: a1b2c3d4-...
     [CopilotKit] 📡 Fetching state from agent at http://localhost:8123
     [StateLoader] Fetching state for thread: a1b2c3d4-...
     [StateLoader] Received XXX bytes from agent
     [StateLoader] Extracted N messages
     [CopilotKit] ✅ Loaded state: N messages, threadExists: true
     ```

3. **Verify chat history restored**
   - ✅ Check: Previous messages appear in chat UI
   - ✅ Check: Both user message and agent response visible
   - ✅ Check: Correct order and content

## Test Scenario 3: Conversation Continuation

### Steps:

1. **Send follow-up message**
   - Type: "And what about London?"
   - Press Enter

2. **Expected behavior:**
   - ✅ Agent should reference Paris from previous context
   - ✅ Agent responds with London weather
   - ✅ No errors in console
   - ✅ No "Message ID not found in history" error

3. **Verify persistence**
   - Refresh page again (F5)
   - ✅ All 3 messages should load (Paris question, answer, London question, answer)

## Test Scenario 4: New Conversation

### Steps:

1. **Start fresh conversation**
   - Clear browser cache or use Incognito window
   - Open http://localhost:3000

2. **Expected behavior:**
   - ✅ Empty chat (no history)
   - ✅ Console shows:
     ```
     [CopilotKit] Request: loadAgentState
     [CopilotKit] ✅ Loaded state: 0 messages, threadExists: false
     ```

3. **Send new message**
   - Type: "Tell me about Tokyo"
   - ✅ Should work normally

## Test Scenario 5: Error Handling

### Steps:

1. **Stop the agent**
   ```bash
   # Stop the agent (Ctrl+C in agent terminal)
   ```

2. **Refresh the page**
   - Expected: Console shows error but UI doesn't crash
   - ✅ Check: UI shows empty chat gracefully
   - ✅ Check: Console shows:
     ```
     [StateLoader] Error fetching state: ...
     [CopilotKit] ✅ Loaded state: 0 messages, threadExists: false
     ```

3. **Restart agent and try again**
   ```bash
   npm run dev:agent
   ```
   - ✅ Should work normally again

## Debugging

### Check Network Requests

In DevTools Network tab:
1. Filter by "copilotkit"
2. Look for POST requests
3. Click on request → Preview tab
4. Verify GraphQL responses

### Check Database Contents

```bash
cd agent
sqlite3 checkpoints.db

# View all threads
SELECT DISTINCT thread_id FROM checkpoints;

# View checkpoints for specific thread
SELECT checkpoint_id, thread_id FROM checkpoints WHERE thread_id = 'YOUR_THREAD_ID';

# Count checkpoints
SELECT COUNT(*) FROM checkpoints;
```

### Check FastAPI Logs

FastAPI terminal should show:
```
=== Initializing AsyncSqliteSaver ===
=== Checkpointer initialized ===
=== Graph compiled with persistent checkpointer ===
--> POST /
<-- POST / [200] 0.XX s
```

### Common Issues

**Issue:** "Module not found: Can't resolve '@/lib/agent-state-loader'"
- **Solution:** Restart Next.js dev server

**Issue:** State not loading after refresh
- **Check:** Browser console for errors
- **Check:** FastAPI is running
- **Check:** Database file exists: `agent/checkpoints.db`

**Issue:** "Message ID not found in history"
- **Cause:** State loader not working properly
- **Check:** Console logs for intercepted loadAgentState
- **Check:** ThreadId consistency

## Success Criteria

All of these should pass:

- ✅ First message works
- ✅ Database saves conversation
- ✅ Page refresh loads history
- ✅ Follow-up messages have context
- ✅ Multiple refreshes maintain history
- ✅ Error handling works gracefully
- ✅ Console logs show proper flow

## Report Issues

If tests fail:
1. Copy console logs
2. Copy FastAPI terminal output
3. Check `PERSISTENCE_WORKAROUND.md` for known issues
4. Report in GitHub issue or to development team

