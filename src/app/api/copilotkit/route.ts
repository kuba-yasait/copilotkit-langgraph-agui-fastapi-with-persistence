import {
  CopilotRuntime,
  ExperimentalEmptyAdapter,
  copilotRuntimeNextJSAppRouterEndpoint,
} from "@copilotkit/runtime";

import { LangGraphHttpAgent } from "@ag-ui/langgraph"
import { NextRequest, NextResponse } from "next/server";
import {
  isLoadAgentStateQuery,
  extractThreadId,
  extractAgentName,
  loadStateFromAgent,
  createLoadStateResponse,
} from "@/lib/agent-state-loader";
 
// 1. You can use any service adapter here for multi-agent support. We use
//    the empty adapter since we're only using one agent.
const serviceAdapter = new ExperimentalEmptyAdapter();

// Agent configuration
const AGENT_URL = process.env.AGENT_URL || "http://localhost:8123";
const AGENTS_CONFIG = {
  "sample_agent": AGENT_URL,
};
 
// 2. Create the CopilotRuntime instance and utilize the LangGraph AG-UI
//    integration to setup the connection.
const runtime = new CopilotRuntime({
  agents: {
    "sample_agent": new LangGraphHttpAgent({
      url: AGENT_URL,
    }),
  }
});
 
// 3. Build a Next.js API route that handles the CopilotKit runtime requests.
export const POST = async (req: NextRequest) => {
  // WORKAROUND: Intercept loadAgentState queries to fetch state from agent
  // See PERSISTENCE_WORKAROUND.md for details
  try {
    const body = await req.json();
    
    console.log(`[CopilotKit] Request: ${body.operationName || 'unknown'}`);
    
    if (isLoadAgentStateQuery(body)) {
      const threadId = extractThreadId(body);
      const agentName = extractAgentName(body);
      
      console.log(`[CopilotKit] 🔄 Intercepting loadAgentState for thread: ${threadId}, agent: ${agentName}`);
      
      if (!threadId || !agentName) {
        console.warn(`[CopilotKit] ⚠️ Missing threadId or agentName`);
        return NextResponse.json({
          data: {
            loadAgentState: {
              threadId: threadId || '',
              threadExists: false,
              messages: '[]',
              state: '{}',
              __typename: 'LoadAgentStateResponse',
            }
          }
        });
      }
      
      // Get the agent URL for this agent
      const agentUrl = AGENTS_CONFIG[agentName as keyof typeof AGENTS_CONFIG];
      
      if (!agentUrl) {
        console.error(`[CopilotKit] ❌ Unknown agent: ${agentName}`);
        return NextResponse.json({
          data: {
            loadAgentState: {
              threadId,
              threadExists: false,
              messages: '[]',
              state: '{}',
              __typename: 'LoadAgentStateResponse',
            }
          }
        });
      }
      
      // Fetch state from the agent
      console.log(`[CopilotKit] 📡 Fetching state from agent at ${agentUrl}`);
      const agentState = await loadStateFromAgent(agentUrl, threadId);
      
      const response = createLoadStateResponse(threadId, agentState);
      
      console.log(`[CopilotKit] ✅ Loaded state: ${agentState.messages.length} messages, threadExists: ${response.threadExists}`);
      
      return NextResponse.json({
        data: {
          loadAgentState: {
            ...response,
            __typename: 'LoadAgentStateResponse',
          }
        }
      });
    }
    
    // For all other requests, pass through to the runtime
    // Note: We need to reconstruct the request with the already-read body
    const reconstructedReq = new NextRequest(req.url, {
      method: req.method,
      headers: req.headers,
      body: JSON.stringify(body),
    });
    
    const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
      runtime, 
      serviceAdapter,
      endpoint: "/api/copilotkit",
    });
   
    return handleRequest(reconstructedReq);
    
  } catch (error) {
    console.error('[CopilotKit] ❌ Error in request handler:', error);
    
    // Fallback to normal handling
    const { handleRequest } = copilotRuntimeNextJSAppRouterEndpoint({
      runtime, 
      serviceAdapter,
      endpoint: "/api/copilotkit",
    });
   
    return handleRequest(req);
  }
};