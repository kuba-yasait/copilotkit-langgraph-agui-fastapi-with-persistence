/**
 * Agent State Loader Utility
 * 
 * Workaround for CopilotKit AG-UI state persistence bug.
 * See PERSISTENCE_WORKAROUND.md for details.
 * 
 * This utility fetches conversation state directly from the FastAPI agent
 * to restore chat history after page refresh.
 */

// Types for AG-UI protocol messages
interface AGUIMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  createdAt?: number;
  [key: string]: any;
}

interface AgentState {
  messages: AGUIMessage[];
  state: Record<string, any>;
}

interface LoadStateResponse {
  threadId: string;
  threadExists: boolean;
  messages: string; // JSON stringified
  state: string; // JSON stringified
}

/**
 * Detects if the request is a loadAgentState GraphQL query
 */
export function isLoadAgentStateQuery(body: any): boolean {
  return (
    body &&
    typeof body === 'object' &&
    body.operationName === 'loadAgentState'
  );
}

/**
 * Extracts threadId from GraphQL loadAgentState query
 */
export function extractThreadId(body: any): string | null {
  try {
    return body?.variables?.data?.threadId || null;
  } catch {
    return null;
  }
}

/**
 * Extracts agentName from GraphQL loadAgentState query
 */
export function extractAgentName(body: any): string | null {
  try {
    return body?.variables?.data?.agentName || null;
  } catch {
    return null;
  }
}

/**
 * Loads agent state from FastAPI backend using custom /load_state endpoint
 */
export async function loadStateFromAgent(
  agentUrl: string,
  threadId: string,
  timeoutMs: number = 5000
): Promise<AgentState> {
  console.log(`[StateLoader] Fetching state for thread: ${threadId}`);
  
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
    
    // Use custom /load_state endpoint (Option A2)
    // This avoids the AG-UI bug with KeyError: 'schema_keys'
    const loadStateUrl = agentUrl.replace(/\/$/, '') + '/load_state';
    const requestBody = {
      threadId,
    };
    
    console.log(`[StateLoader] Calling ${loadStateUrl}`);
    console.log(`[StateLoader] Request body:`, JSON.stringify(requestBody, null, 2));
    
    const response = await fetch(loadStateUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody),
      signal: controller.signal,
    });
    
    clearTimeout(timeoutId);
    
    if (!response.ok) {
      const errorText = await response.text();
      console.error(`[StateLoader] Agent responded with ${response.status}`);
      console.error(`[StateLoader] Error details:`, errorText);
      return { messages: [], state: {} };
    }
    
    // Parse JSON response from custom endpoint
    const data = await response.json();
    console.log(`[StateLoader] Received response:`, data);
    console.log(`[StateLoader] Extracted ${data.messages.length} messages`);
    
    return {
      messages: data.messages || [],
      state: data.state || {},
    };
    
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.error(`[StateLoader] Timeout fetching state for ${threadId}`);
    } else {
      console.error(`[StateLoader] Error fetching state:`, error);
    }
    
    // Return empty state on error
    return { messages: [], state: {} };
  }
}

/**
 * Creates a GraphQL response for loadAgentState
 */
export function createLoadStateResponse(
  threadId: string,
  agentState: AgentState
): LoadStateResponse {
  const threadExists = agentState.messages.length > 0;
  
  return {
    threadId,
    threadExists,
    messages: JSON.stringify(agentState.messages),
    state: JSON.stringify(agentState.state),
  };
}

